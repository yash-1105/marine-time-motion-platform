from datetime import datetime

from dateutil import parser
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.canonical import (
    Delay,
    EventOccurrence,
    ServiceAssignment,
    ServiceExecution,
    ServiceRequest,
    VesselCall,
)
from apps.api.models.config import EventDefinition
from apps.api.models.quality import QualityIssue, QualityRule


class DataQualityEngine:
    # These rule definitions are deliberately local, deterministic metadata.  They
    # mirror config/quality_rules.yaml and also make a database seeded before a new
    # rule was added safe to upgrade.  No inference is used in this workflow.
    RULE_SPECS = {
        "DQ-003": ("vessel_call", "HIGH", "ATA is required", "Provide the actual arrival time."),
        "DQ-004": ("vessel_call", "HIGH", "ETA must not be after ATA", "Verify the ETA/ATA source timestamps."),
        "DQ-005": (
            "service_request",
            "HIGH",
            "Pilot request requires a scheduled time",
            "Provide the missing schedule.",
        ),
        "DQ-006": (
            "event_occurrence",
            "CRITICAL",
            "Anchorage arrival must precede arrival pilot boarding",
            "Review the source chronology.",
        ),
        "DQ-007": (
            "delay",
            "MEDIUM",
            "Late service requires a recorded delay reason",
            "Provide a governed delay reason.",
        ),
        "DQ-010": (
            "event_occurrence",
            "HIGH",
            "Conflicting source timestamps exceed the governed tolerance",
            "Resolve the conflicting observations.",
        ),
        "DQ-SERVICE-REQUEST-MISSING": (
            "service_request",
            "HIGH",
            "Requested service time is required",
            "Provide Requested_Time; do not substitute a value.",
        ),
        "DQ-SERVICE-SCHEDULE-MISSING": (
            "service_assignment",
            "HIGH",
            "Scheduled service time is required",
            "Provide Scheduled_Time; do not infer it.",
        ),
        "DQ-SERVICE-SERVED-MISSING": (
            "service_execution",
            "HIGH",
            "Actual/served service time is required",
            "Provide Served_Time; do not infer it.",
        ),
        "DQ-SERVICE-SCHEDULE-BEFORE-REQUEST": (
            "service_assignment",
            "HIGH",
            "Requested Time <= Scheduled Time",
            "Correct the source chronology without swapping timestamps.",
        ),
        "DQ-INVALID-TIMESTAMP": (
            "staging_record",
            "HIGH",
            "Timestamp must be parseable with its declared timezone",
            "Correct the source value; raw evidence remains unchanged.",
        ),
        "DQ-MISSING-MANDATORY-FIELD": (
            "staging_record",
            "HIGH",
            "Mandatory source field is blank",
            "Provide the required source value.",
        ),
        "DQ-DUPLICATE-ROW": (
            "staging_record",
            "MEDIUM",
            "Exact duplicate row in dataset group",
            "Confirm the duplicate or exclude it from analysis.",
        ),
        "DQ-SEQUENCE-VIOLATION": (
            "event_occurrence",
            "CRITICAL",
            "A configured DAG dependency has negative ordered duration",
            "Review the ordered event pair; parallel activities are not evaluated by this rule.",
        ),
        "DQ-SERVICE-DURATION-NEGATIVE": (
            "service_execution",
            "HIGH",
            "Service end must not precede service start",
            "Correct the ordered service timestamps.",
        ),
    }

    def __init__(self, db: Session, ingestion_batch_id: str | None = None):
        self.db = db
        self.ingestion_batch_id = ingestion_batch_id
        # Bootstrap deterministic rule metadata from the governed configuration.
        # The database remains the runtime registry/versioned audit surface.
        self._ensure_configured_rules()
        self.rules = {r.rule_id: r for r in self.db.execute(select(QualityRule)).scalars().all()}
        self._open_issues = {
            (issue.rule_id, issue.record_reference): issue
            for issue in self.db.execute(select(QualityIssue).where(QualityIssue.issue_status != "RESOLVED"))
            .scalars()
            .all()
        }
        # Load event definitions
        self.event_defs = {e.id: e.name for e in self.db.execute(select(EventDefinition)).scalars().all()}

        # Load journey templates for DAG chronology
        import yaml

        try:
            with open("config/journey_templates.yaml") as yf:
                self.journey_templates = yaml.safe_load(yf)
        except Exception:
            self.journey_templates = {}

    def _ensure_configured_rules(self):
        import yaml

        try:
            with open("config/quality_rules.yaml") as rules_file:
                configured_rules = (yaml.safe_load(rules_file) or {}).get("rules", [])
        except OSError:
            configured_rules = []
        existing = set(self.db.execute(select(QualityRule.rule_id)).scalars().all())
        for configured in configured_rules:
            rule_id = configured.get("id")
            if not rule_id or rule_id in existing:
                continue
            self.db.add(
                QualityRule(
                    rule_id=rule_id,
                    scope=configured.get("scope", "staging_record"),
                    severity=configured.get("severity", "HIGH"),
                    pass_fail_expression=configured.get("pass_fail_expression", rule_id),
                    remediation_guidance=configured.get("remediation_guidance"),
                )
            )
        self.db.flush()

    def _create_issue(self, rule_id: str, vc_id: str | None, ref: str, severity: str | None = None):
        # We need to make sure the rule exists
        rule = self.rules.get(rule_id)
        if not rule:
            scope, configured_severity, expression, remediation = self.RULE_SPECS.get(
                rule_id, ("vessel_call", severity or "HIGH", rule_id, "Review the governed source record.")
            )
            rule = QualityRule(
                rule_id=rule_id,
                scope=scope,
                severity=severity or configured_severity,
                pass_fail_expression=expression,
                remediation_guidance=remediation,
            )
            self.db.add(rule)
            self.db.flush()
            self.rules[rule_id] = rule
        issue_severity = severity or rule.severity
        # Re-runs are normal (ingestion, exclusion rebuilds and manual DQ runs).
        # A rule/reference pair must therefore be idempotent rather than generating
        # duplicate work items on every run.
        existing = self._open_issues.get((rule.id, ref))
        if existing:
            return existing
        issue = QualityIssue(rule_id=rule.id, vessel_call_id=vc_id, record_reference=ref, issue_status="OPEN")
        self.db.add(issue)
        self._open_issues[(rule.id, ref)] = issue
        # Apply quarantine if CRITICAL
        if issue_severity == "CRITICAL":
            # For this MVP engine, we find the relevant record and quarantine it
            if ref.startswith("EventOccurrence:"):
                ev_id = ref.split(":")[1]
                ev = self.db.query(EventOccurrence).filter(EventOccurrence.id == ev_id).first()
                if ev:
                    ev.is_quarantined = True
        return issue

    def run_all(self):
        vessel_calls = self.db.execute(select(VesselCall)).scalars().all()
        # Quality checks are deterministic but used to issue several queries for
        # every vessel call (and every service).  Preloading the candidate data
        # keeps exactly the same rules and evidence while avoiding remote-DB N+1
        # latency during ingestion.
        from apps.api.models.ingestion import StagingRecord

        staging_query = select(StagingRecord).where(StagingRecord.canonical_table == "vessel_call")
        if self.ingestion_batch_id:
            staging_query = staging_query.where(StagingRecord.ingestion_batch_id == self.ingestion_batch_id)
        staging_by_vcn = {
            row.parsed_data.get("VCN"): row
            for row in self.db.execute(staging_query).scalars().all()
            if row.parsed_data and row.parsed_data.get("VCN")
        }
        vessel_ids = [vc.id for vc in vessel_calls]
        events_by_call: dict = {}
        services_by_call: dict = {}
        assignments_by_request: dict = {}
        executions_by_assignment: dict = {}
        delays_by_call: dict = {}
        if vessel_ids:
            for event in (
                self.db.execute(select(EventOccurrence).where(EventOccurrence.vessel_call_id.in_(vessel_ids)))
                .scalars()
                .all()
            ):
                events_by_call.setdefault(event.vessel_call_id, []).append(event)
            services = (
                self.db.execute(select(ServiceRequest).where(ServiceRequest.vessel_call_id.in_(vessel_ids)))
                .scalars()
                .all()
            )
            for service in services:
                services_by_call.setdefault(service.vessel_call_id, []).append(service)
            request_ids = [service.id for service in services]
            if request_ids:
                assignments = (
                    self.db.execute(
                        select(ServiceAssignment).where(ServiceAssignment.service_request_id.in_(request_ids))
                    )
                    .scalars()
                    .all()
                )
                assignments_by_request = {assignment.service_request_id: assignment for assignment in assignments}
                assignment_ids = [assignment.id for assignment in assignments]
                if assignment_ids:
                    executions_by_assignment = {
                        execution.service_assignment_id: execution
                        for execution in self.db.execute(
                            select(ServiceExecution).where(ServiceExecution.service_assignment_id.in_(assignment_ids))
                        )
                        .scalars()
                        .all()
                    }
            for delay in self.db.execute(select(Delay).where(Delay.vessel_call_id.in_(vessel_ids))).scalars().all():
                delays_by_call.setdefault(delay.vessel_call_id, []).append(delay)
        context = {
            "staging_by_vcn": staging_by_vcn,
            "events_by_call": events_by_call,
            "services_by_call": services_by_call,
            "assignments_by_request": assignments_by_request,
            "executions_by_assignment": executions_by_assignment,
            "delays_by_call": delays_by_call,
        }
        for vc in vessel_calls:
            try:
                self.evaluate_vessel_call(vc, context=context)
            except Exception as e:
                print(f"Error evaluating {vc.vcn}: {e}")
                import traceback

                traceback.print_exc()
        self.evaluate_staging_records()
        self.db.commit()

    @staticmethod
    def _is_blank(value) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _parse_timestamp(value):
        if DataQualityEngine._is_blank(value):
            return None
        if isinstance(value, datetime):
            return value
        try:
            return parser.parse(str(value))
        except (TypeError, ValueError, OverflowError):
            return False

    def evaluate_staging_records(self):
        """Validate source rows that cannot safely become canonical observations.

        Parsing failures and blank source columns are intentionally reviewed from
        staging: raw records remain immutable and no timestamp is corrected or
        silently discarded.  This runs while the candidate batch is still inactive.
        """
        from apps.api.models.ingestion import StagingRecord

        query = select(StagingRecord)
        if self.ingestion_batch_id:
            query = query.where(StagingRecord.ingestion_batch_id == self.ingestion_batch_id)
        rows = self.db.execute(query).scalars().all()
        required = {
            "vessel_call": ("VCN", "Vessel_Name"),
            "event_occurrence": ("VCN", "Event_Name", "Event_Timestamp"),
            "service_request": ("VCN", "Service_Type"),
        }
        timestamp_fields = {
            "vessel_call": ("ETA", "ATA", "ETD", "ATD"),
            "event_occurrence": ("Event_Timestamp",),
            "service_request": ("Submission_Time", "Requested_Time", "Scheduled_Time", "Served_Time"),
            "delay": ("Scheduled_Time", "Served_Time"),
            "cargo_ops": ("Cargo_Start", "Cargo_End"),
        }
        for row in rows:
            data = row.parsed_data or {}
            ref = f"StagingRecord:{row.id}"
            for field in required.get(row.canonical_table, ()):
                if self._is_blank(data.get(field)):
                    self._create_issue("DQ-MISSING-MANDATORY-FIELD", None, ref, "HIGH")
                    break
            if row.validation_status == "DUPLICATE":
                self._create_issue("DQ-DUPLICATE-ROW", None, ref, "MEDIUM")
            for field in timestamp_fields.get(row.canonical_table, ()):
                parsed = self._parse_timestamp(data.get(field))
                if parsed is False:
                    self._create_issue("DQ-INVALID-TIMESTAMP", None, ref, "HIGH")
                    break

    def evaluate_vessel_call(self, vc: VesselCall, context: dict | None = None):
        # We can also check the staging record for the vessel call to catch missing VesselCalls sheet fields
        from apps.api.models.ingestion import StagingRecord

        if context is None:
            staging = (
                self.db.execute(select(StagingRecord).where(StagingRecord.canonical_table == "vessel_call"))
                .scalars()
                .all()
            )
            vc_staging = next((s for s in staging if s.parsed_data.get("VCN") == vc.vcn), None)
        else:
            vc_staging = context["staging_by_vcn"].get(vc.vcn)

        # DQ-003: ATA blank in VesselCalls sheet
        if vc_staging and (
            not vc_staging.parsed_data.get("ATA") or str(vc_staging.parsed_data.get("ATA")).strip() == ""
        ):
            self._create_issue("DQ-003", vc.id, f"VesselCall:{vc.id}", "HIGH")

        events = (
            context["events_by_call"].get(vc.id, [])
            if context is not None
            else self.db.execute(select(EventOccurrence).where(EventOccurrence.vessel_call_id == vc.id)).scalars().all()
        )
        event_map = {}
        for ev in events:
            name = self.event_defs.get(ev.event_definition_id)
            if name not in event_map:
                event_map[name] = []
            event_map[name].append(ev)

        # DQ-004: ETA after ATA
        # We check staging record ETA/ATA too because Events sheet ETA/ATA might not reflect the injected error
        eta_staging = vc_staging.parsed_data.get("ETA") if vc_staging else None
        ata_staging = vc_staging.parsed_data.get("ATA") if vc_staging else None

        if eta_staging and ata_staging:
            try:
                eta_dt = parser.parse(eta_staging)
                ata_dt = parser.parse(ata_staging)
                if eta_dt > ata_dt:
                    self._create_issue("DQ-004", vc.id, f"VesselCall:{vc.id}", "HIGH")
            except (TypeError, ValueError, OverflowError):
                pass

        # Or if it's in the events
        eta_evs = event_map.get("ETA")
        ata_evs = event_map.get("ATA")
        if eta_evs and ata_evs:
            if eta_evs[0].utc_value and ata_evs[0].utc_value and eta_evs[0].utc_value > ata_evs[0].utc_value:
                self._create_issue("DQ-004", vc.id, f"EventOccurrence:{eta_evs[0].id}", "HIGH")

        # DQ-010: Conflicting ATA values
        if ata_evs and len(ata_evs) > 1:
            # check if they differ by 5 hours
            dur = abs((ata_evs[0].utc_value - ata_evs[1].utc_value).total_seconds()) / 3600
            if dur >= 5:
                self._create_issue("DQ-010", vc.id, f"EventOccurrence:{ata_evs[0].id}", "HIGH")

        # DQ-005: Pilot request present, scheduled absent (check events)
        pilot_req = event_map.get("PILOT_REQUEST_ARRIVAL")
        pilot_sched = event_map.get("PILOT_SCHEDULED_ARRIVAL")
        if pilot_req and not pilot_sched:
            self._create_issue("DQ-005", vc.id, f"EventOccurrence:{pilot_req[0].id}", "HIGH")

        # DQ-006 and Sequence violations via DAG configuration
        # Instead of hardcoding, we parse `sequence_rules` from the journey templates
        templates = self.journey_templates.get("templates", [])
        for tpl in templates:
            seq_rules = tpl.get("dag", {}).get("sequence_rules", [])
            for r in seq_rules:
                from_ev = r.get("from")
                to_ev = r.get("to")

                from_occ = event_map.get(from_ev)
                to_occ = event_map.get(to_ev)

                if from_occ and to_occ:
                    if from_occ[0].utc_value and to_occ[0].utc_value:
                        dur = (to_occ[0].utc_value - from_occ[0].utc_value).total_seconds()
                        if dur < -300:
                            # if it's the specific DQ-006 case from the fixture
                            if from_ev == "ANCHORAGE_ARRIVAL" and to_ev == "PILOT_ON_BOARD_ARRIVAL":
                                self._create_issue("DQ-006", vc.id, f"EventOccurrence:{to_occ[0].id}", "CRITICAL")
                            else:
                                self._create_issue(
                                    "DQ-SEQUENCE-VIOLATION", vc.id, f"EventOccurrence:{to_occ[0].id}", "CRITICAL"
                                )

        # DQ-007: positive execution delay, but reason missing
        services = (
            context["services_by_call"].get(vc.id, [])
            if context is not None
            else self.db.execute(select(ServiceRequest).where(ServiceRequest.vessel_call_id == vc.id)).scalars().all()
        )

        # A schedule before the request is a chronology/data-quality error.  This
        # is categorically different from a negative Served − Scheduled result,
        # which remains valid early service.
        for req in services:
            ass = (
                context["assignments_by_request"].get(req.id)
                if context is not None
                else self.db.execute(
                    select(ServiceAssignment).where(ServiceAssignment.service_request_id == req.id)
                ).scalar_one_or_none()
            )
            if req.requested_time is None:
                self._create_issue("DQ-SERVICE-REQUEST-MISSING", vc.id, f"ServiceRequest:{req.id}", "HIGH")
            if ass is None or ass.scheduled_time is None:
                self._create_issue(
                    "DQ-SERVICE-SCHEDULE-MISSING",
                    vc.id,
                    f"ServiceAssignment:{ass.id}" if ass else f"ServiceRequest:{req.id}",
                    "HIGH",
                )
                continue
            exe = (
                context["executions_by_assignment"].get(ass.id)
                if context is not None
                else self.db.execute(
                    select(ServiceExecution).where(ServiceExecution.service_assignment_id == ass.id)
                ).scalar_one_or_none()
            )
            if exe is None or exe.served_time is None:
                self._create_issue(
                    "DQ-SERVICE-SERVED-MISSING",
                    vc.id,
                    f"ServiceExecution:{exe.id}" if exe else f"ServiceAssignment:{ass.id}",
                    "HIGH",
                )
            if ass and req.requested_time and ass.scheduled_time and ass.scheduled_time < req.requested_time:
                self._create_issue("DQ-SERVICE-SCHEDULE-BEFORE-REQUEST", vc.id, f"ServiceAssignment:{ass.id}", "HIGH")

        # We can just check if there is any positive execution delay without a corresponding delay record
        has_positive_delay = False
        for req in services:
            ass = (
                context["assignments_by_request"].get(req.id)
                if context is not None
                else self.db.execute(
                    select(ServiceAssignment).where(ServiceAssignment.service_request_id == req.id)
                ).scalar_one_or_none()
            )
            if ass:
                exe = (
                    context["executions_by_assignment"].get(ass.id)
                    if context is not None
                    else self.db.execute(
                        select(ServiceExecution).where(ServiceExecution.service_assignment_id == ass.id)
                    ).scalar_one_or_none()
                )
                if exe and ass.scheduled_time and exe.served_time:
                    delay_seconds = (exe.served_time - ass.scheduled_time).total_seconds()
                    if delay_seconds > 0:
                        has_positive_delay = True
                        break

        if has_positive_delay:
            # Check if there's any delay record for this VC in the Delay table
            delays = (
                context["delays_by_call"].get(vc.id, [])
                if context is not None
                else self.db.execute(select(Delay).where(Delay.vessel_call_id == vc.id)).scalars().all()
            )
            if not delays or all(not (delay.delay_reason or "").strip() for delay in delays):
                self._create_issue("DQ-007", vc.id, f"VesselCall:{vc.id}", "MEDIUM")

        # Handle parallel events (tests prove parallel events raise no violations)
        # If Tug Service Start and Pilot On Board overlap, no issue raised here by default.
