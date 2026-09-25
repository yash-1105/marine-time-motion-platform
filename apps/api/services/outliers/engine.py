"""Deterministic FRD-v2 outlier engine (section 4.4.6).

Rules live in ``config/outlier_rules.yaml``. Missing inputs are never replaced
with proxies. Percentiles use linear interpolation and persisted results carry
their rule, threshold, source records, journey leg and explanation. Every read
and write is scoped through the authenticated tenant's vessel calls.
"""

from __future__ import annotations

import math
import statistics
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.models.analytics import LeadTimeDefinition, LeadTimeResult, OutlierRecord
from apps.api.models.audit import AuditEvent
from apps.api.models.canonical import EventOccurrence, ServiceAssignment, ServiceExecution, ServiceRequest, VesselCall
from apps.api.models.config import EventDefinition
from apps.api.models.journey import CanonicalObservation
from apps.api.models.quality import QualityIssue, QualityRule


@lru_cache(maxsize=1)
def load_outlier_rule_registry() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[4] / "config" / "outlier_rules.yaml"
    with path.open(encoding="utf-8") as source:
        return yaml.safe_load(source) or {}


def linear_percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class OutlierEngine:
    CATEGORIES = frozenset(
        {
            "Time-based Outlier",
            "Sequence Outlier",
            "Resource Utilization Outlier",
            "Data Quality Outlier",
            "Operational Performance Outlier",
        }
    )

    def __init__(self, db: Session, tenant_id: str = "default-tenant"):
        self.db = db
        self.tenant_id = tenant_id
        self.registry = load_outlier_rule_registry()

    def _tenant_calls(self) -> dict[uuid.UUID, VesselCall]:
        query = select(VesselCall).where(VesselCall.is_merged.is_(False))
        if self.tenant_id != "*":
            query = query.where(VesselCall.tenant_id == self.tenant_id)
        return {call.id: call for call in self.db.execute(query).scalars().all()}

    @staticmethod
    def _record(
        *,
        call: VesselCall,
        rule_id: str,
        category: str,
        metric: str,
        observed: float | None,
        threshold: float | None,
        issue: str,
        threshold_label: str,
        reason: str,
        leg: str | None,
        sources: list[str],
        severity: str = "HIGH",
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "vessel_call_id": call.id,
            "vcn": call.vcn or "UNKNOWN",
            "outlier_type": category,
            "rule_id": rule_id,
            "metric_name": metric,
            "observed_value": round(observed, 6) if observed is not None else None,
            "benchmark_or_p90": round(threshold, 6) if threshold is not None else None,
            "divergence": round(observed - threshold, 6) if observed is not None and threshold is not None else None,
            "issue_text": issue,
            "threshold_label": threshold_label,
            "reason": reason,
            "movement_leg": leg,
            "source_record_ids": sources,
            "severity": severity,
            "evidence": evidence or {},
        }

    def _lead_time_rows(self, name: str, calls: dict[uuid.UUID, VesselCall]) -> list[dict[str, Any]]:
        if not calls:
            return []
        rows = (
            self.db.execute(
                select(LeadTimeResult)
                .join(LeadTimeDefinition, LeadTimeResult.definition_id == LeadTimeDefinition.id)
                .where(
                    LeadTimeDefinition.name == name,
                    LeadTimeResult.vessel_call_id.in_(calls),
                    LeadTimeResult.status == "AVAILABLE",
                    LeadTimeResult.duration_hours.isnot(None),
                )
            )
            .scalars()
            .all()
        )
        return [
            {"call": calls[row.vessel_call_id], "value": row.duration_hours, "sources": row.source_record_ids or []}
            for row in rows
        ]

    def _events(
        self, calls: dict[uuid.UUID, VesselCall], names: set[str]
    ) -> dict[tuple[uuid.UUID, str], EventOccurrence]:
        if not calls or not names:
            return {}
        definitions = {
            item.id: item.name
            for item in self.db.execute(select(EventDefinition).where(EventDefinition.name.in_(names))).scalars().all()
        }
        if not definitions:
            return {}
        occurrences = (
            self.db.execute(
                select(EventOccurrence)
                .where(
                    EventOccurrence.vessel_call_id.in_(calls),
                    EventOccurrence.event_definition_id.in_(definitions),
                    EventOccurrence.is_quarantined.is_(False),
                    EventOccurrence.is_superseded.is_(False),
                )
                .order_by(EventOccurrence.occurrence_index, EventOccurrence.utc_value)
            )
            .scalars()
            .all()
        )
        by_id = {item.id: item for item in occurrences}
        selected = {
            (item.vessel_call_id, item.event_definition_id): item.selected_event_occurrence_id
            for item in self.db.execute(
                select(CanonicalObservation).where(
                    CanonicalObservation.vessel_call_id.in_(calls),
                    CanonicalObservation.event_definition_id.in_(definitions),
                )
            )
            .scalars()
            .all()
            if item.selected_event_occurrence_id
        }
        resolved: dict[tuple[uuid.UUID, str], EventOccurrence] = {}
        for occurrence in occurrences:
            key = (occurrence.vessel_call_id, definitions[occurrence.event_definition_id])
            selected_id = selected.get((occurrence.vessel_call_id, occurrence.event_definition_id))
            if selected_id in by_id:
                resolved[key] = by_id[selected_id]
            elif key not in resolved:
                resolved[key] = occurrence
        return resolved

    def _event_pair_rows(
        self, calls: dict[uuid.UUID, VesselCall], start_name: str, end_name: str
    ) -> list[dict[str, Any]]:
        events = self._events(calls, {start_name, end_name})
        result = []
        for call in calls.values():
            start, end = events.get((call.id, start_name)), events.get((call.id, end_name))
            if start and end:
                result.append(
                    {
                        "call": call,
                        "value": (end.utc_value - start.utc_value).total_seconds() / 3600,
                        "sources": [str(start.id), str(end.id)],
                    }
                )
        return result

    def _high_rule(
        self,
        rows: list[dict[str, Any]],
        *,
        q: float,
        rule_id: str,
        category: str,
        metric: str,
        issue: str,
        leg: str | None,
    ) -> list[dict[str, Any]]:
        eligible = [row for row in rows if row["value"] >= 0]
        threshold = linear_percentile((row["value"] for row in eligible), q)
        if threshold is None:
            return []
        label = f"P{int(q * 100)} (linear): {threshold:.2f}h"
        return [
            self._record(
                call=row["call"],
                rule_id=rule_id,
                category=category,
                metric=metric,
                observed=row["value"],
                threshold=threshold,
                issue=issue,
                threshold_label=label,
                reason=f"Observed {row['value']:.2f}h exceeds the governed P{int(q * 100)} threshold of {threshold:.2f}h.",
                leg=leg,
                sources=row["sources"],
                severity="CRITICAL" if threshold > 0 and row["value"] > threshold * 1.5 else "HIGH",
                evidence={
                    "percentile_method": "linear_interpolation",
                    "quantile": q,
                    "eligible_population": len(eligible),
                },
            )
            for row in eligible
            if row["value"] > threshold
        ]

    def _three_sd_rule(
        self, rows: list[dict[str, Any]], *, rule_id: str, category: str, metric: str, issue: str, leg: str | None
    ) -> list[dict[str, Any]]:
        values = [row["value"] for row in rows]
        if len(values) < 2:
            return []
        mean, sample_sd = statistics.mean(values), statistics.stdev(values)
        threshold = mean + 3 * sample_sd
        return [
            self._record(
                call=row["call"],
                rule_id=rule_id,
                category=category,
                metric=metric,
                observed=row["value"],
                threshold=threshold,
                issue=issue,
                threshold_label=f"Mean + 3 sample SD: {threshold:.2f}h",
                reason=f"Observed {row['value']:.2f}h exceeds mean {mean:.2f}h plus three sample SD ({sample_sd:.2f}h).",
                leg=leg,
                sources=row["sources"],
                severity="HIGH",
                evidence={
                    "mean_hours": mean,
                    "sample_standard_deviation_hours": sample_sd,
                    "eligible_population": len(values),
                },
            )
            for row in rows
            if row["value"] > threshold
        ]

    def _pilot_rows(self, calls: dict[uuid.UUID, VesselCall]) -> list[dict[str, Any]]:
        if not calls:
            return []
        rows = self.db.execute(
            select(ServiceRequest, ServiceAssignment, ServiceExecution)
            .join(ServiceAssignment, ServiceAssignment.service_request_id == ServiceRequest.id)
            .join(ServiceExecution, ServiceExecution.service_assignment_id == ServiceAssignment.id)
            .where(
                ServiceRequest.vessel_call_id.in_(calls),
                ServiceRequest.service_type.ilike("%pilot%"),
                ServiceAssignment.scheduled_time.isnot(None),
                ServiceExecution.served_time.isnot(None),
            )
        ).all()
        leg_map = {"ARRIVAL": "ARRIVAL_INWARD", "SAILING": "SAILING_OUTWARD", "SHIFTING": "SHIFTING"}
        return [
            {
                "call": calls[request.vessel_call_id],
                "value": (execution.served_time - assignment.scheduled_time).total_seconds() / 3600,
                "sources": [str(request.id), str(assignment.id), str(execution.id)],
                "leg": leg_map.get((request.movement_type or "").upper(), "UNCLASSIFIED"),
            }
            for request, assignment, execution in rows
        ]

    def _quality_outliers(self, calls: dict[uuid.UUID, VesselCall]) -> list[dict[str, Any]]:
        if not calls:
            return []
        rows = self.db.execute(
            select(QualityIssue, QualityRule)
            .join(QualityRule, QualityIssue.rule_id == QualityRule.id)
            .where(QualityIssue.vessel_call_id.in_(calls), QualityIssue.issue_status != "RESOLVED")
        ).all()
        result = []
        for issue, rule in rows:
            external = rule.rule_id.upper()
            if "SEQUENCE" in external or "CHRONO" in external or external in {"DQ-004", "DQ-006"}:
                category, rule_id, text = "Sequence Outlier", "OUT-V2-031", "Invalid chronological sequence detected."
            elif "MISSING" in external or "DUPLICATE" in external:
                category, rule_id, text = (
                    "Data Quality Outlier",
                    "OUT-V2-032",
                    "A critical timestamp is missing or duplicated.",
                )
            else:
                continue
            result.append(
                self._record(
                    call=calls[issue.vessel_call_id],
                    rule_id=rule_id,
                    category=category,
                    metric=rule.scope.replace("_", " ").title(),
                    observed=None,
                    threshold=None,
                    issue=text,
                    threshold_label=rule.pass_fail_expression,
                    reason=rule.remediation_guidance or rule.pass_fail_expression,
                    leg=None,
                    sources=[issue.record_reference],
                    severity=rule.severity,
                    evidence={"quality_rule_id": external, "quality_issue_id": str(issue.id)},
                )
            )
        return result

    def detect_all_outliers(self, persist: bool = True) -> list[dict[str, Any]]:
        calls = self._tenant_calls()
        outliers: list[dict[str, Any]] = []
        outliers += self._high_rule(
            self._lead_time_rows("Turnaround", calls),
            q=0.90,
            rule_id="OUT-V2-001",
            category="Time-based Outlier",
            metric="Vessel Turnaround",
            issue="Vessel turnaround time exceeds the P90 threshold.",
            leg=None,
        )

        pilot_rows = self._pilot_rows(calls)
        outliers += self._three_sd_rule(
            pilot_rows,
            rule_id="OUT-V2-002",
            category="Time-based Outlier",
            metric="Pilot Boarding Execution Delay",
            issue="Pilot boarding delay exceeds the historical average by three standard deviations.",
            leg=None,
        )
        p30 = linear_percentile((row["value"] for row in pilot_rows), 0.30)
        if p30 is not None:
            outliers += [
                self._record(
                    call=row["call"],
                    rule_id="OUT-V2-007",
                    category="Time-based Outlier",
                    metric="Pilot Boarding Execution Delay",
                    observed=row["value"],
                    threshold=p30,
                    issue="Pilot boarding occurred significantly earlier than scheduled.",
                    threshold_label=f"P30 (linear): {p30:.2f}h",
                    reason=f"Execution delay {row['value']:.2f}h is below P30 ({p30:.2f}h); its negative sign remains early service.",
                    leg=row["leg"],
                    sources=row["sources"],
                    severity="MEDIUM",
                    evidence={
                        "percentile_method": "linear_interpolation",
                        "quantile": 0.30,
                        "semantics": "negative values are early service",
                    },
                )
                for row in pilot_rows
                if row["value"] < p30
            ]

        outliers += self._high_rule(
            self._lead_time_rows("Anchorage Wait", calls),
            q=0.95,
            rule_id="OUT-V2-006",
            category="Time-based Outlier",
            metric="Anchorage Waiting",
            issue="Anchorage waiting time exceeds the P95 threshold.",
            leg="ARRIVAL_INWARD",
        )
        outliers += self._three_sd_rule(
            self._lead_time_rows("First Line to All Fast", calls),
            rule_id="OUT-V2-010",
            category="Time-based Outlier",
            metric="Mooring Completion",
            issue="Mooring completion exceeds the historical upper control limit.",
            leg="ARRIVAL_INWARD",
        )
        outliers += self._high_rule(
            self._lead_time_rows("Unberthing Duration", calls),
            q=0.90,
            rule_id="OUT-V2-015",
            category="Time-based Outlier",
            metric="Unmooring Duration",
            issue="Unmooring duration exceeds the P90 threshold.",
            leg="SAILING_OUTWARD",
        )
        outliers += self._high_rule(
            self._lead_time_rows("Breakwater In to All Fast", calls),
            q=0.90,
            rule_id="OUT-V2-025",
            category="Time-based Outlier",
            metric="Breakwater In to All Fast",
            issue="Breakwater-in to all-fast duration exceeds the P90 threshold.",
            leg="ARRIVAL_INWARD",
        )

        pairs = (
            (
                "ALL_FAST_ARRIVAL",
                "CARGO_START",
                "OUT-V2-011",
                "Cargo Start Readiness",
                "Cargo operations started unusually late after all fast.",
                "ARRIVAL_INWARD",
            ),
            (
                "CARGO_END",
                "PILOT_ON_BOARD_SAILING",
                "OUT-V2-012",
                "Cargo Completion to Sailing Readiness",
                "Cargo completion to sailing readiness exceeds the P90 threshold.",
                "SAILING_OUTWARD",
            ),
            (
                "CARGO_END",
                "LAST_LINE_UNTIED_SAILING",
                "OUT-V2-013",
                "Post-cargo Berth Time",
                "The vessel remained at berth unusually long after cargo completion.",
                "SAILING_OUTWARD",
            ),
            (
                "PILOT_ON_BOARD_ARRIVAL",
                "BREAKWATER_IN",
                "OUT-V2-024",
                "Pilot Boarding to Breakwater In",
                "Pilot boarding to breakwater-in duration exceeds the P90 threshold.",
                "ARRIVAL_INWARD",
            ),
            (
                "BREAKWATER_OUT",
                "PORT_LIMIT_OUT",
                "OUT-V2-026",
                "Breakwater Out to Port Limit Out",
                "Breakwater-out to port-limit-out duration exceeds the P90 threshold.",
                "SAILING_OUTWARD",
            ),
            (
                "FIRST_LINE_TIED_ARRIVAL",
                "LAST_LINE_TIED_ARRIVAL",
                "OUT-V2-042",
                "Line Handling (Berthing)",
                "First-line-tied to last-line-tied duration exceeds the P90 threshold.",
                "ARRIVAL_INWARD",
            ),
        )
        for start, end, rule_id, metric, issue, leg in pairs:
            outliers += self._high_rule(
                self._event_pair_rows(calls, start, end),
                q=0.90,
                rule_id=rule_id,
                category="Time-based Outlier",
                metric=metric,
                issue=issue,
                leg=leg,
            )

        arrival = self._events(
            calls, {"PILOT_ON_BOARD_ARRIVAL", "TUG_1_SERVICE_START_ARRIVAL", "TUG_2_SERVICE_START_ARRIVAL"}
        )
        for call in calls.values():
            pilot = arrival.get((call.id, "PILOT_ON_BOARD_ARRIVAL"))
            for name in ("TUG_1_SERVICE_START_ARRIVAL", "TUG_2_SERVICE_START_ARRIVAL"):
                tug = arrival.get((call.id, name))
                if pilot and tug and tug.utc_value < pilot.utc_value:
                    delta = (tug.utc_value - pilot.utc_value).total_seconds() / 3600
                    outliers.append(
                        self._record(
                            call=call,
                            rule_id="OUT-V2-004",
                            category="Sequence Outlier",
                            metric="Arrival Tug Sequence",
                            observed=delta,
                            threshold=0,
                            issue="Tug service started before pilot boarding.",
                            threshold_label="Tug service start ≥ pilot on board",
                            reason="The governed tug service start timestamp precedes pilot boarding.",
                            leg="ARRIVAL_INWARD",
                            sources=[str(tug.id), str(pilot.id)],
                            severity="HIGH",
                            evidence={
                                "tug_service_start": tug.utc_value.isoformat(),
                                "pilot_on_board": pilot.utc_value.isoformat(),
                            },
                        )
                    )

        shift_definition = self.db.execute(
            select(EventDefinition).where(EventDefinition.name == "PILOT_ON_BOARD_SHIFTING")
        ).scalar_one_or_none()
        if shift_definition and calls:
            shifts = (
                self.db.execute(
                    select(EventOccurrence).where(
                        EventOccurrence.vessel_call_id.in_(calls),
                        EventOccurrence.event_definition_id == shift_definition.id,
                        EventOccurrence.is_quarantined.is_(False),
                        EventOccurrence.is_superseded.is_(False),
                    )
                )
                .scalars()
                .all()
            )
            by_call: dict[uuid.UUID, list[EventOccurrence]] = {}
            for occurrence in shifts:
                by_call.setdefault(occurrence.vessel_call_id, []).append(occurrence)
            for call_id, occurrences in by_call.items():
                if len(occurrences) > 1:
                    outliers.append(
                        self._record(
                            call=calls[call_id],
                            rule_id="OUT-V2-028",
                            category="Operational Performance Outlier",
                            metric="Berth Shifts",
                            observed=float(len(occurrences)),
                            threshold=1,
                            issue="Multiple berth shifts were recorded in one vessel call.",
                            threshold_label="More than 1 shifting movement",
                            reason=f"{len(occurrences)} governed shifting movements were found for the vessel call.",
                            leg="SHIFTING",
                            sources=[str(item.id) for item in occurrences],
                            severity="MEDIUM",
                        )
                    )

        sailing_variance = self._event_pair_rows(calls, "ETD", "ATD")
        for row in sailing_variance:
            row["signed_value"], row["value"] = row["value"], abs(row["value"])
        outliers += self._high_rule(
            sailing_variance,
            q=0.90,
            rule_id="OUT-V2-034",
            category="Operational Performance Outlier",
            metric="Planned vs Actual Sailing Variance",
            issue="Planned versus actual sailing variance exceeds the P90 threshold.",
            leg="SAILING_OUTWARD",
        )
        outliers += self._quality_outliers(calls)

        unique: dict[tuple[str, uuid.UUID], dict[str, Any]] = {}
        for outlier in outliers:
            if outlier["outlier_type"] not in self.CATEGORIES:
                raise ValueError(f"Unsupported FRD v2 category: {outlier['outlier_type']}")
            unique[(outlier["rule_id"], outlier["vessel_call_id"])] = outlier
        outliers = list(unique.values())

        if persist:
            existing = {
                (row.rule_id, row.vessel_call_id): (row.is_excluded_from_kpi, row.exclusion_rationale)
                for row in self.db.execute(select(OutlierRecord).where(OutlierRecord.tenant_id == self.tenant_id))
                .scalars()
                .all()
            }
            self.db.query(OutlierRecord).filter(OutlierRecord.tenant_id == self.tenant_id).delete(
                synchronize_session=False
            )
            for item in outliers:
                excluded, rationale = existing.get((item["rule_id"], item["vessel_call_id"]), (False, None))
                self.db.add(
                    OutlierRecord(
                        tenant_id=self.tenant_id,
                        vessel_call_id=item["vessel_call_id"],
                        vcn=item["vcn"],
                        outlier_type=item["outlier_type"],
                        rule_id=item["rule_id"],
                        metric_name=item["metric_name"],
                        observed_value=item["observed_value"],
                        benchmark_or_p90=item["benchmark_or_p90"],
                        divergence=item["divergence"],
                        issue_text=item["issue_text"],
                        threshold_label=item["threshold_label"],
                        reason=item["reason"],
                        movement_leg=item["movement_leg"],
                        source_record_ids=item["source_record_ids"],
                        is_excluded_from_kpi=excluded,
                        exclusion_rationale=rationale,
                        severity=item["severity"],
                        evidence=item["evidence"],
                        detected_at=datetime.now(UTC),
                    )
                )
            self.db.commit()
        return outliers

    def toggle_outlier_exclusion(
        self, outlier_id: uuid.UUID, is_excluded: bool, rationale: str, actor: str = "data_steward"
    ) -> dict[str, Any]:
        rec = self.db.execute(
            select(OutlierRecord).where(OutlierRecord.id == outlier_id, OutlierRecord.tenant_id == self.tenant_id)
        ).scalar_one_or_none()
        if not rec:
            raise ValueError(f"Outlier record {outlier_id} not found")
        old_value = rec.is_excluded_from_kpi
        rec.is_excluded_from_kpi, rec.exclusion_rationale = is_excluded, rationale
        self.db.add(
            AuditEvent(
                actor_id=actor,
                actor_email=actor if "@" in actor else f"{actor}@port.local",
                actor_role="data_steward",
                action="TOGGLE_OUTLIER_EXCLUSION",
                resource_type="outlier_record",
                resource_id=str(rec.id),
                entity_name="analytics.outlier_record",
                entity_id=str(rec.id),
                details={
                    "tenant_id": self.tenant_id,
                    "vcn": rec.vcn,
                    "rule_id": rec.rule_id,
                    "metric_name": rec.metric_name,
                    "previous_excluded": old_value,
                    "new_excluded": is_excluded,
                    "rationale": rationale,
                },
            )
        )
        self.db.commit()
        return {
            "id": str(rec.id),
            "vcn": rec.vcn,
            "metric_name": rec.metric_name,
            "is_excluded_from_kpi": rec.is_excluded_from_kpi,
            "exclusion_rationale": rec.exclusion_rationale,
            "severity": rec.severity,
        }

    def list_outliers(
        self,
        outlier_type: str | None = None,
        severity: str | None = None,
        is_excluded: bool | None = None,
        vcn: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            select(OutlierRecord, VesselCall.vessel_name)
            .join(VesselCall, OutlierRecord.vessel_call_id == VesselCall.id)
            .where(OutlierRecord.tenant_id == self.tenant_id, VesselCall.tenant_id == self.tenant_id)
        )
        if outlier_type:
            query = query.where(OutlierRecord.outlier_type == outlier_type)
        if severity:
            query = query.where(OutlierRecord.severity == severity)
        if is_excluded is not None:
            query = query.where(OutlierRecord.is_excluded_from_kpi == is_excluded)
        if vcn:
            query = query.where(OutlierRecord.vcn == vcn)
        rows = self.db.execute(query.order_by(desc(OutlierRecord.severity), desc(OutlierRecord.divergence))).all()
        return [
            {
                "id": str(row.id),
                "vessel_call_id": str(row.vessel_call_id),
                "vcn": row.vcn,
                "vessel_name": vessel_name,
                "outlier_type": row.outlier_type,
                "rule_id": row.rule_id,
                "metric_name": row.metric_name,
                "observed_value": row.observed_value,
                "benchmark_or_p90": row.benchmark_or_p90,
                "divergence": row.divergence,
                "issue_text": row.issue_text,
                "threshold_label": row.threshold_label,
                "reason": row.reason,
                "movement_leg": row.movement_leg,
                "source_record_ids": row.source_record_ids or [],
                "is_excluded_from_kpi": row.is_excluded_from_kpi,
                "exclusion_rationale": row.exclusion_rationale,
                "severity": row.severity,
                "evidence": row.evidence,
                "detected_at": row.detected_at.isoformat() if row.detected_at else None,
            }
            for row, vessel_name in rows
        ]
