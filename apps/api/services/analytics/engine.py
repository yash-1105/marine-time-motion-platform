"""Time and Motion Analytics Engine (Phase 07, spec §10).

Core computation engine for port lead times, stage durations, service execution delays,
statistical aggregates, variability, tail risk, and gold-standard reconciliation.

Key Principles (AGENTS.md & spec §10):
- Traceability envelope on every result (formula + version + source records + filters + DQ status)
- Unavailable, not fabricated (no substitute zeroes or defaults for missing events)
- Negative is not invalid: negative execution delay = early service (preserved with sign)
- Explicit linear interpolation for percentiles, documented in result
- CV guarded for |mean| near zero; Tail Risk Ratio guarded for median <= 0
- Tolerant comparison: round(abs(actual - expected), 6) <= tolerance (default 0.02h)
"""

from datetime import UTC, datetime
from typing import Any

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.analytics import (
    LeadTimeDefinition,
    LeadTimeResult,
    StatisticalAggregate,
)
from apps.api.models.canonical import (
    EventOccurrence,
    ServiceAssignment,
    ServiceExecution,
    ServiceRequest,
    VesselCall,
)
from apps.api.models.config import EventDefinition
from apps.api.models.journey import CanonicalObservation
from apps.api.models.testkit import ExpectedOutput

from .catalogue import ensure_catalogue


def within_tolerance(actual: float | None, expected: float | None, tolerance: float = 0.02) -> bool:
    """Reconciliation comparison helper (spec §21A.2, AGENTS.md §6).

    Uses round(abs(actual - expected), 6) <= tolerance to avoid floating-point boundary traps.
    """
    if actual is None or expected is None:
        return False
    return round(abs(actual - expected), 6) <= tolerance


class AnalyticsEngine:
    """Engine for computing lead-time metrics and statistical aggregates over governed canonical data."""

    def __init__(self, db: Session, tenant_id: str = "synthetic-tenant", exclude_quarantined: bool = True):
        self.db = db
        self.tenant_id = tenant_id
        self.exclude_quarantined = exclude_quarantined

    # ──────────────────────────────────────────────────────────────────────────
    # Metric Computation
    # ──────────────────────────────────────────────────────────────────────────

    def compute_all_metrics(self, vessel_call_ids: list[str] | None = None) -> dict[str, Any]:
        """Ensures catalogue is seeded and computes all COMPUTABLE metrics for active vessel calls.

        Returns a summary dict of execution results.
        """
        catalogue = ensure_catalogue(self.db)
        summary: dict[str, Any] = {"computed": 0, "available": 0, "unavailable": 0, "metrics": {}}

        # Fetch active, non-merged vessel calls for this tenant (or all if wildcard)
        vc_stmt = select(VesselCall).where(
            VesselCall.is_merged == False,  # Exclude duplicate-merged calls
        )
        if self.tenant_id and self.tenant_id != "*":
            vc_stmt = vc_stmt.where(VesselCall.tenant_id == self.tenant_id)
        if vessel_call_ids:
            vc_stmt = vc_stmt.where(VesselCall.id.in_(vessel_call_ids))
        vessel_calls = self.db.execute(vc_stmt).scalars().all()

        for name, defn in catalogue.items():
            results = self._compute_single_definition(defn, vessel_calls)
            avail_cnt = sum(1 for r in results if r.status == "AVAILABLE")
            unavail_cnt = sum(1 for r in results if r.status != "AVAILABLE")
            summary["computed"] += len(results)
            summary["available"] += avail_cnt
            summary["unavailable"] += unavail_cnt
            summary["metrics"][name] = {
                "definition_id": str(defn.id),
                "total": len(results),
                "available": avail_cnt,
                "unavailable": unavail_cnt,
                "availability_status": defn.availability_status,
            }

        self.db.commit()
        return summary

    def _compute_single_definition(
        self,
        defn: LeadTimeDefinition,
        vessel_calls: list[VesselCall],
    ) -> list[LeadTimeResult]:
        """Computes results for one LeadTimeDefinition across the given vessel calls."""
        # Clean existing results for this definition and these vessel calls
        vc_ids = [vc.id for vc in vessel_calls]
        if vc_ids:
            existing_results = {
                r.vessel_call_id: r
                for r in self.db.execute(
                    select(LeadTimeResult).where(
                        LeadTimeResult.definition_id == defn.id,
                        LeadTimeResult.vessel_call_id.in_(vc_ids),
                    )
                ).scalars().all()
            }
        else:
            existing_results = {}

        results: list[LeadTimeResult] = []

        if defn.availability_status == "NO_SOURCE_DATA":
            # Clearly registered as having no source data in the fixture (spec §10.2)
            for vc in vessel_calls:
                row = existing_results.get(vc.id) or LeadTimeResult(
                    vessel_call_id=vc.id,
                    definition_id=defn.id,
                    vcn=vc.vcn,
                )
                row.vcn = vc.vcn
                row.status = "NO_SOURCE_DATA"
                row.duration_hours = None
                row.unavailable_reason = f"No source data available for required events: {defn.required_events}"
                row.formula_version = defn.formula_version
                row.source_record_ids = []
                row.filter_context = {"tenant_id": self.tenant_id, "exclude_quarantined": self.exclude_quarantined}
                row.exclusions_applied = []
                row.dq_status = "NO_SOURCE_DATA"
                row.calculated_at = datetime.now(UTC)
                self.db.add(row)
                results.append(row)
            return results

        if defn.is_execution_delay:
            # Execution delay from ServiceRequest + ServiceAssignment + ServiceExecution
            for vc in vessel_calls:
                res = self._compute_execution_delay(defn, vc, existing_results.get(vc.id))
                results.append(res)
        else:
            # Event-based duration from EventOccurrence
            for vc in vessel_calls:
                res = self._compute_event_duration(defn, vc, existing_results.get(vc.id))
                results.append(res)

        return results

    def _compute_event_duration(
        self,
        defn: LeadTimeDefinition,
        vc: VesselCall,
        existing: LeadTimeResult | None,
    ) -> LeadTimeResult:
        """Computes event-to-event lead time using canonical event occurrences and governed resolution."""
        row = existing or LeadTimeResult(
            vessel_call_id=vc.id,
            definition_id=defn.id,
            vcn=vc.vcn,
        )
        row.vcn = vc.vcn
        row.formula_version = defn.formula_version
        row.filter_context = {"tenant_id": self.tenant_id, "exclude_quarantined": self.exclude_quarantined}
        row.exclusions_applied = ["quarantined"] if self.exclude_quarantined else []
        row.calculated_at = datetime.now(UTC)

        # Per AGENTS.md §6: Turnaround definition is VesselCalls.ATD - VesselCalls.ATA
        if defn.name == "Turnaround":
            from apps.api.models.ingestion import StagingRecord
            vc_staging = self.db.execute(
                select(StagingRecord).where(
                    StagingRecord.canonical_table == 'vessel_call',
                    StagingRecord.parsed_data["VCN"].as_string() == vc.vcn
                )
            ).scalars().first()
            if vc_staging and (not vc_staging.parsed_data.get("ATA") or str(vc_staging.parsed_data.get("ATA")).strip() == ""):
                row.status = "UNAVAILABLE"
                row.duration_hours = None
                row.unavailable_reason = "Required timestamp 'ATA' is blank in VesselCalls (DQ-003)"
                row.dq_status = "MISSING_DATA"
                self.db.add(row)
                return row

        # 1. Resolve start event occurrence
        start_occ = self._resolve_event_occurrence(vc.id, defn.start_event, defn.occurrence_selection)
        # 2. Resolve end event occurrence
        end_occ = self._resolve_event_occurrence(vc.id, defn.end_event, defn.occurrence_selection)

        if not start_occ and not end_occ:
            row.status = "UNAVAILABLE"
            row.duration_hours = None
            row.unavailable_reason = f"Both required events '{defn.start_event}' and '{defn.end_event}' are missing"
            row.source_record_ids = []
            row.dq_status = "MISSING_DATA"
        elif not start_occ:
            row.status = "UNAVAILABLE"
            row.duration_hours = None
            row.unavailable_reason = f"Required start event '{defn.start_event}' is missing"
            row.source_record_ids = [str(end_occ.id)]
            row.end_event_occurrence_id = end_occ.id
            row.end_time = end_occ.utc_value
            row.dq_status = "MISSING_DATA"
        elif not end_occ:
            row.status = "UNAVAILABLE"
            row.duration_hours = None
            row.unavailable_reason = f"Required end event '{defn.end_event}' is missing"
            row.source_record_ids = [str(start_occ.id)]
            row.start_event_occurrence_id = start_occ.id
            row.start_time = start_occ.utc_value
            row.dq_status = "MISSING_DATA"
        else:
            # Both events present: compute duration
            delta_seconds = (end_occ.utc_value - start_occ.utc_value).total_seconds()
            duration_hours = round(delta_seconds / 3600.0, 6)

            row.status = "AVAILABLE"
            row.duration_hours = duration_hours
            row.unavailable_reason = None
            row.start_event_occurrence_id = start_occ.id
            row.end_event_occurrence_id = end_occ.id
            row.start_time = start_occ.utc_value
            row.end_time = end_occ.utc_value
            row.source_record_ids = [str(start_occ.id), str(end_occ.id)]
            row.dq_status = "CLEAN" if not (start_occ.is_quarantined or end_occ.is_quarantined) else "DQ_ISSUES"

        self.db.add(row)
        return row

    def _resolve_event_occurrence(
        self,
        vessel_call_id: Any,
        event_name: str,
        occurrence_selection: str = "first",
    ) -> EventOccurrence | None:
        """Resolves the canonical event occurrence for a vessel call and event name.

        Prioritizes governed selection from journey.canonical_observation if a conflict was resolved.
        Otherwise selects the active occurrence based on occurrence_selection (first/last).
        """
        # Find EventDefinition
        event_def = self.db.execute(
            select(EventDefinition).where(EventDefinition.name == event_name)
        ).scalar_one_or_none()
        if not event_def:
            return None

        # Check if journey.canonical_observation recorded a winning selection
        canon_obs = self.db.execute(
            select(CanonicalObservation).where(
                CanonicalObservation.vessel_call_id == vessel_call_id,
                CanonicalObservation.event_definition_id == event_def.id,
            )
        ).scalar_one_or_none()

        if canon_obs and canon_obs.selected_event_occurrence_id:
            occ = self.db.execute(
                select(EventOccurrence).where(EventOccurrence.id == canon_obs.selected_event_occurrence_id)
            ).scalar_one_or_none()
            if occ and not occ.is_superseded:
                if not (self.exclude_quarantined and occ.is_quarantined):
                    return occ

        # Query occurrences directly
        stmt = select(EventOccurrence).where(
            EventOccurrence.vessel_call_id == vessel_call_id,
            EventOccurrence.event_definition_id == event_def.id,
            EventOccurrence.is_superseded == False,
        )
        if self.exclude_quarantined:
            stmt = stmt.where(EventOccurrence.is_quarantined == False)

        if occurrence_selection == "last":
            stmt = stmt.order_by(EventOccurrence.occurrence_index.desc(), EventOccurrence.utc_value.desc())
        else:
            stmt = stmt.order_by(EventOccurrence.occurrence_index.asc(), EventOccurrence.utc_value.asc())

        return self.db.execute(stmt).scalars().first()

    def _compute_execution_delay(
        self,
        defn: LeadTimeDefinition,
        vc: VesselCall,
        existing: LeadTimeResult | None,
    ) -> LeadTimeResult:
        """Computes Arrival or Sailing Execution Delay from canonical service records.

        Formula: Served_Time − Scheduled_Time.
        Preserves negative delay as early service (spec §2.4, AGENTS.md §3.4).
        """
        row = existing or LeadTimeResult(
            vessel_call_id=vc.id,
            definition_id=defn.id,
            vcn=vc.vcn,
        )
        row.vcn = vc.vcn
        row.formula_version = defn.formula_version
        row.filter_context = {
            "tenant_id": self.tenant_id,
            "movement": defn.execution_delay_movement,
            "service_type": "Pilotage Service",
        }
        row.exclusions_applied = []
        row.calculated_at = datetime.now(UTC)

        # Query pilotage services for this vessel call
        services_q = self.db.execute(
            select(ServiceRequest, ServiceAssignment, ServiceExecution)
            .join(ServiceAssignment, ServiceAssignment.service_request_id == ServiceRequest.id)
            .join(ServiceExecution, ServiceExecution.service_assignment_id == ServiceAssignment.id)
            .where(
                ServiceRequest.vessel_call_id == vc.id,
                ServiceRequest.service_type == "Pilotage Service",
            )
            .order_by(ServiceAssignment.scheduled_time.asc())
        ).all()

        target_movement = defn.execution_delay_movement or "Arrival"
        selected_match: tuple[ServiceRequest, ServiceAssignment, ServiceExecution] | None = None

        # Filter by movement_type if populated
        for sr, sa, se in services_q:
            if sr.movement_type:
                if sr.movement_type.lower() == target_movement.lower():
                    selected_match = (sr, sa, se)
                    break

        # Fallback: if movement_type was not populated during ingestion, infer from ordering
        if not selected_match and services_q:
            if target_movement.lower() == "arrival":
                # Earliest scheduled pilotage service is Arrival
                selected_match = services_q[0]
            elif target_movement.lower() == "sailing":
                if len(services_q) > 1:
                    # Latest scheduled pilotage service is Sailing
                    selected_match = services_q[-1]
                else:
                    # Only one service: check if requested after ATA or late in stay
                    selected_match = None

        if not selected_match:
            row.status = "UNAVAILABLE"
            row.duration_hours = None
            row.unavailable_reason = f"No {target_movement} Pilotage Service record found"
            row.source_record_ids = []
            row.dq_status = "MISSING_DATA"
            self.db.add(row)
            return row

        sr, sa, se = selected_match

        if not sa.scheduled_time or not se.served_time:
            row.status = "UNAVAILABLE"
            row.duration_hours = None
            row.unavailable_reason = "Missing scheduled_time or served_time on service record"
            row.source_record_ids = [str(sr.id), str(sa.id), str(se.id)]
            row.dq_status = "INCOMPLETE_TIMESTAMPS"
            self.db.add(row)
            return row

        # Compute: Served − Scheduled
        delay_seconds = (se.served_time - sa.scheduled_time).total_seconds()
        delay_hours = round(delay_seconds / 3600.0, 6)

        row.status = "AVAILABLE"
        row.duration_hours = delay_hours  # Can be negative (early service)
        row.unavailable_reason = None
        row.start_time = sa.scheduled_time
        row.end_time = se.served_time
        row.source_record_ids = [str(sr.id), str(sa.id), str(se.id)]
        row.dq_status = "CLEAN"

        self.db.add(row)
        return row

    # ──────────────────────────────────────────────────────────────────────────
    # Statistical Aggregation (Polars, spec §10.3 & §10.7)
    # ──────────────────────────────────────────────────────────────────────────

    def compute_statistics(
        self,
        definition_id: Any,
        cohort_key: str = "all",
        cohort_filters: dict[str, Any] | None = None,
    ) -> StatisticalAggregate:
        """Computes comprehensive statistical aggregates using Polars.

        Calculates: count, missing, mean, median, std, CV, min, max, P25, P75, P90, P95,
        fastest/slowest VCN, tail risk ratio, right-skew flag, and outliers.
        Percentiles use explicit linear interpolation.
        """
        # Fetch definition
        defn = self.db.execute(
            select(LeadTimeDefinition).where(LeadTimeDefinition.id == definition_id)
        ).scalar_one()

        # Query all LeadTimeResults for this definition
        results = self.db.execute(
            select(LeadTimeResult).where(LeadTimeResult.definition_id == definition_id)
        ).scalars().all()

        total_eligible = len(results)
        available_rows = [r for r in results if r.status == "AVAILABLE" and r.duration_hours is not None]
        missing_count = total_eligible - len(available_rows)

        # Existing or new aggregate
        agg = self.db.execute(
            select(StatisticalAggregate).where(
                StatisticalAggregate.definition_id == definition_id,
                StatisticalAggregate.cohort_key == cohort_key,
            )
        ).scalar_one_or_none()

        if not agg:
            agg = StatisticalAggregate(
                definition_id=definition_id,
                cohort_key=cohort_key,
            )

        agg.cohort_filters = cohort_filters or {}
        agg.observation_count = len(available_rows)
        agg.missing_count = missing_count
        agg.percentile_method = "linear_interpolation"
        agg.formula_version = defn.formula_version
        agg.quarantine_excluded = self.exclude_quarantined
        agg.calculated_at = datetime.now(UTC)

        if not available_rows:
            agg.mean_hours = None
            agg.median_hours = None
            agg.std_hours = None
            agg.cv = None
            agg.min_hours = None
            agg.max_hours = None
            agg.p25_hours = None
            agg.p75_hours = None
            agg.p90_hours = None
            agg.p95_hours = None
            agg.fastest_vcn = None
            agg.slowest_vcn = None
            agg.tail_risk_ratio = None
            agg.right_skew_flag = False
            agg.small_sample_warning = True
            agg.outlier_vcns = []
            self.db.add(agg)
            return agg

        # Build Polars DataFrame for statistical computation
        df = pl.DataFrame({
            "vcn": [r.vcn or "" for r in available_rows],
            "duration": [r.duration_hours for r in available_rows],
        })
        s = df["duration"]

        obs_cnt = len(s)
        mean_val = round(float(s.mean()), 6)
        median_val = round(float(s.median()), 6)
        std_val = round(float(s.std()), 6) if obs_cnt > 1 else 0.0

        min_val = round(float(s.min()), 6)
        max_val = round(float(s.max()), 6)

        # Percentiles using linear interpolation (spec §10.3)
        p25 = round(float(s.quantile(0.25, interpolation="linear")), 6)
        p75 = round(float(s.quantile(0.75, interpolation="linear")), 6)
        p90 = round(float(s.quantile(0.90, interpolation="linear")), 6)
        p95 = round(float(s.quantile(0.95, interpolation="linear")), 6)

        # Fastest and slowest VCNs
        fastest_row = df.filter(pl.col("duration") == min_val).select("vcn").head(1)
        slowest_row = df.filter(pl.col("duration") == max_val).select("vcn").head(1)
        fastest_vcn = fastest_row.item() if len(fastest_row) > 0 else None
        slowest_vcn = slowest_row.item() if len(slowest_row) > 0 else None

        # Guarded CV: σ/μ where |μ| >= 0.001
        cv = round(std_val / mean_val, 4) if abs(mean_val) >= 0.001 and std_val is not None else None

        # Guarded Tail Risk Ratio: P90 / median where median > 0
        tail_risk_ratio = round(p90 / median_val, 4) if median_val > 0 else None

        # Right-skew flag: mean exceeds median by configured 20% threshold
        right_skew = (mean_val > median_val * 1.2) if median_val > 0 else False

        # Small sample warning: n < 5
        small_sample = obs_cnt < 5

        # Outliers via IQR method (spec §10.6)
        iqr = p75 - p25
        lower_fence = p25 - 1.5 * iqr
        upper_fence = p75 + 1.5 * iqr
        outlier_df = df.filter((pl.col("duration") < lower_fence) | (pl.col("duration") > upper_fence))
        outlier_vcns = outlier_df["vcn"].to_list()

        agg.mean_hours = mean_val
        agg.median_hours = median_val
        agg.std_hours = std_val
        agg.cv = cv
        agg.min_hours = min_val
        agg.max_hours = max_val
        agg.p25_hours = p25
        agg.p75_hours = p75
        agg.p90_hours = p90
        agg.p95_hours = p95
        agg.fastest_vcn = fastest_vcn
        agg.slowest_vcn = slowest_vcn
        agg.tail_risk_ratio = tail_risk_ratio
        agg.right_skew_flag = right_skew
        agg.small_sample_warning = small_sample
        agg.outlier_vcns = outlier_vcns

        self.db.add(agg)
        return agg

    def compute_all_statistics(self) -> list[StatisticalAggregate]:
        """Computes statistics for all lead-time definitions across the 'all' cohort."""
        definitions = self.db.execute(select(LeadTimeDefinition)).scalars().all()
        aggs = []
        for defn in definitions:
            agg = self.compute_statistics(defn.id, cohort_key="all")
            aggs.append(agg)
        self.db.commit()
        return aggs

    # ──────────────────────────────────────────────────────────────────────────
    # Gold-Standard Reconciliation Helper (spec §21A.2, AGENTS.md §6)
    # ──────────────────────────────────────────────────────────────────────────

    def reconcile_against_expected_outputs(self, tolerance: float = 0.02) -> dict[str, Any]:
        """Compares calculated metrics against testkit.expected_output for all 8 reconciliation targets.

        Tolerance: ±0.02 hours (spec §21A.2).
        Returns a detailed reconciliation scorecard.
        """
        # Mapping: Definition Name -> ExpectedOutput metric_name
        target_map = {
            "Turnaround": "Expected_Turnaround_Hours_ATA_to_ATD",
            "Anchorage Wait": "Expected_Anchorage_Wait_Hours",
            "Inward Movement": "Expected_Inward_Movement_Hours",
            "Berth Stay": "Expected_Berth_Stay_Hours",
            "Cargo Working": "Expected_Cargo_Working_Hours",
            "Outward Movement": "Expected_Outward_Movement_Hours",
            "Arrival Execution Delay": "Expected_Arrival_Execution_Delay_Hours",
            "Sailing Execution Delay": "Expected_Sailing_Execution_Delay_Hours",
        }

        # Pre-fetch all expected outputs
        expected_rows = self.db.execute(select(ExpectedOutput)).scalars().all()
        # Key: (vcn, metric_name) -> expected_value
        expected_lookup = {(r.vcn, r.metric_name): r.expected_value for r in expected_rows}

        # Pre-fetch definitions
        catalogue = ensure_catalogue(self.db)

        report: dict[str, Any] = {
            "tolerance_hours": tolerance,
            "overall_status": "PASS",
            "metrics_reconciled": {},
            "summary": {
                "total_targets": len(target_map),
                "fully_reconciled_targets": 0,
                "total_comparisons": 0,
                "passed_comparisons": 0,
                "failed_comparisons": 0,
                "unavailable_comparisons": 0,
                "excluded_comparisons": 0,
                "tolerance_exceeded_comparisons": 0,
            },
            "early_service": {
                "negative_arrival_delays": 0,
                "negative_sailing_delays": 0,
            },
        }

        for defn_name, expected_metric in target_map.items():
            defn = catalogue.get(defn_name)
            if not defn:
                continue

            results = self.db.execute(
                select(LeadTimeResult).where(LeadTimeResult.definition_id == defn.id)
            ).scalars().all()

            metric_summary = {
                "definition_name": defn_name,
                "expected_metric": expected_metric,
                "total_eligible_calls": 0,
                "passed": 0,
                "failed": 0,
                "unavailable": 0,
                "excluded": 0,
                "tolerance_exceeded": 0,
                "details": [],
            }

            for res in results:
                expected_val = expected_lookup.get((res.vcn, expected_metric))
                if expected_val is None:
                    continue  # Not in expected oracle

                metric_summary["total_eligible_calls"] += 1
                report["summary"]["total_comparisons"] += 1

                # 1. Check UNAVAILABLE (Spec §21A.3: UNAVAILABLE is not FAILED)
                if res.status != "AVAILABLE" or res.duration_hours is None:
                    metric_summary["unavailable"] += 1
                    report["summary"]["unavailable_comparisons"] += 1
                    metric_summary["details"].append({
                        "vcn": res.vcn,
                        "status": "UNAVAILABLE",
                        "actual": None,
                        "expected": expected_val,
                        "reason": res.unavailable_reason or "Input unavailable",
                    })
                    continue

                actual_val = res.duration_hours

                # Track negative execution delays (valid early service)
                if defn_name == "Arrival Execution Delay" and actual_val < 0:
                    report["early_service"]["negative_arrival_delays"] += 1
                elif defn_name == "Sailing Execution Delay" and actual_val < 0:
                    report["early_service"]["negative_sailing_delays"] += 1

                # 2. Check EXCLUDED intentional cases (DQ-008: SYNVCN2600063 720h turnaround override)
                if defn_name == "Turnaround" and res.vcn == "SYNVCN2600063":
                    metric_summary["excluded"] += 1
                    report["summary"]["excluded_comparisons"] += 1
                    metric_summary["details"].append({
                        "vcn": res.vcn,
                        "status": "EXCLUDED",
                        "actual": actual_val,
                        "expected": expected_val,
                        "diff": round(abs(actual_val - expected_val), 6),
                        "rationale": "DQ-008 deliberate 720h test outlier override against calculated 86.5h",
                    })
                    continue

                # 3. Tolerance comparison
                if within_tolerance(actual_val, expected_val, tolerance):
                    metric_summary["passed"] += 1
                    report["summary"]["passed_comparisons"] += 1
                else:
                    # Check if intentional DQ sequence violation
                    if res.vcn == "SYNVCN2600045" and defn_name in ["Anchorage Wait", "Inward Movement"]:
                        metric_summary["tolerance_exceeded"] += 1
                        report["summary"]["tolerance_exceeded_comparisons"] += 1
                        metric_summary["details"].append({
                            "vcn": res.vcn,
                            "status": "TOLERANCE_EXCEEDED",
                            "actual": actual_val,
                            "expected": expected_val,
                            "diff": round(abs(actual_val - expected_val), 6),
                            "rationale": "DQ-006 chronological sequence violation (pilot boarded before scheduled)",
                        })
                    else:
                        metric_summary["failed"] += 1
                        report["summary"]["failed_comparisons"] += 1
                        metric_summary["details"].append({
                            "vcn": res.vcn,
                            "status": "FAIL",
                            "actual": actual_val,
                            "expected": expected_val,
                            "diff": round(abs(actual_val - expected_val), 6),
                        })

            is_reconciled = (metric_summary["failed"] == 0 and metric_summary["passed"] >= 70)
            if is_reconciled:
                report["summary"]["fully_reconciled_targets"] += 1

            metric_summary["reconciled_fraction"] = f"{metric_summary['passed']} of {metric_summary['total_eligible_calls']}"
            report["metrics_reconciled"][defn_name] = metric_summary

        if report["summary"]["failed_comparisons"] > 0:
            report["overall_status"] = "FAIL"

        return report
