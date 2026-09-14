"""Custom Lead-Time Builder (spec §10.2).

Allows authorised users to select any valid start and end event, handles repeated occurrences
(first, last, nth, all), movement scope, missing events, calculates per-call and aggregated
results, and optionally saves the definition to the catalogue.
"""

from datetime import UTC, datetime
from typing import Any

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.analytics import LeadTimeDefinition
from apps.api.models.canonical import EventOccurrence, VesselCall
from apps.api.models.config import EventDefinition


class CustomLeadTimeBuilder:
    """Service for ad-hoc and user-saved custom event-to-event lead-time calculations."""

    def __init__(self, db: Session, tenant_id: str = "synthetic-tenant"):
        self.db = db
        self.tenant_id = tenant_id

    def build(
        self,
        start_event: str,
        end_event: str,
        occurrence_selection: str = "first",  # first | last | nth | all
        occurrence_n: int = 1,
        movement_scope: str | None = None,
        cohort_filters: dict[str, Any] | None = None,
        vessel_call_ids: list[str] | None = None,
        exclude_quarantined: bool = True,
        save_as_name: str | None = None,
        description: str | None = None,
        created_by_user: str | None = None,
    ) -> dict[str, Any]:
        """Calculates lead-time results between any two valid canonical events for a cohort of vessel calls."""
        # 1. Resolve event definitions
        start_def = self.db.execute(
            select(EventDefinition).where(EventDefinition.name == start_event)
        ).scalar_one_or_none()
        end_def = self.db.execute(
            select(EventDefinition).where(EventDefinition.name == end_event)
        ).scalar_one_or_none()

        if not start_def:
            raise ValueError(f"Unknown start event: '{start_event}'")
        if not end_def:
            raise ValueError(f"Unknown end event: '{end_event}'")

        # 2. Query target vessel calls (respecting tenant scope unless wildcard '*')
        vc_stmt = select(VesselCall).where(
            VesselCall.is_merged == False,
        )
        if self.tenant_id and self.tenant_id != "*":
            vc_stmt = vc_stmt.where(VesselCall.tenant_id == self.tenant_id)
        if vessel_call_ids:
            vc_stmt = vc_stmt.where(VesselCall.id.in_(vessel_call_ids))

        # Cohort filters
        if cohort_filters:
            vt = cohort_filters.get("vessel_type")
            if vt and vt not in ("*", "ALL"):
                vc_stmt = vc_stmt.where(VesselCall.vessel_type == vt)
            ct = cohort_filters.get("cargo_type")
            if ct and ct not in ("*", "ALL"):
                vc_stmt = vc_stmt.where(VesselCall.cargo_type == ct)
            pid = cohort_filters.get("port_id")
            if pid and pid not in ("*", "ALL"):
                vc_stmt = vc_stmt.where(VesselCall.port_id == pid)
            tid = cohort_filters.get("terminal_id")
            if tid and tid not in ("*", "ALL"):
                vc_stmt = vc_stmt.where(VesselCall.terminal_id == tid)

        vessel_calls = self.db.execute(vc_stmt).scalars().all()

        # 3. Calculate per-call results
        per_call_results: list[dict[str, Any]] = []
        durations: list[float] = []

        for vc in vessel_calls:
            # Query occurrences
            s_stmt = select(EventOccurrence).where(
                EventOccurrence.vessel_call_id == vc.id,
                EventOccurrence.event_definition_id == start_def.id,
                EventOccurrence.is_superseded == False,
            )
            e_stmt = select(EventOccurrence).where(
                EventOccurrence.vessel_call_id == vc.id,
                EventOccurrence.event_definition_id == end_def.id,
                EventOccurrence.is_superseded == False,
            )
            if exclude_quarantined:
                s_stmt = s_stmt.where(EventOccurrence.is_quarantined == False)
                e_stmt = e_stmt.where(EventOccurrence.is_quarantined == False)
            if movement_scope:
                s_stmt = s_stmt.where(EventOccurrence.movement_scope == movement_scope)
                e_stmt = e_stmt.where(EventOccurrence.movement_scope == movement_scope)

            start_occs = self.db.execute(
                s_stmt.order_by(EventOccurrence.occurrence_index.asc(), EventOccurrence.utc_value.asc())
            ).scalars().all()

            end_occs = self.db.execute(
                e_stmt.order_by(EventOccurrence.occurrence_index.asc(), EventOccurrence.utc_value.asc())
            ).scalars().all()

            if occurrence_selection == "all":
                # Pair occurrences sequentially
                pairs = list(zip(start_occs, end_occs))
                if not pairs:
                    per_call_results.append({
                        "vessel_call_id": str(vc.id),
                        "vcn": vc.vcn,
                        "vessel_name": vc.vessel_name,
                        "status": "UNAVAILABLE",
                        "duration_hours": None,
                        "unavailable_reason": f"No paired occurrences of {start_event} and {end_event}",
                        "source_record_ids": [],
                        "dq_status": "MISSING_DATA",
                    })
                else:
                    for idx, (s_occ, e_occ) in enumerate(pairs, 1):
                        delta = (e_occ.utc_value - s_occ.utc_value).total_seconds() / 3600.0
                        dur_h = round(delta, 6)
                        durations.append(dur_h)
                        per_call_results.append({
                            "vessel_call_id": str(vc.id),
                            "vcn": vc.vcn,
                            "vessel_name": vc.vessel_name,
                            "pair_index": idx,
                            "status": "AVAILABLE",
                            "duration_hours": dur_h,
                            "start_time": s_occ.utc_value.isoformat(),
                            "end_time": e_occ.utc_value.isoformat(),
                            "start_event_occurrence_id": str(s_occ.id),
                            "end_event_occurrence_id": str(e_occ.id),
                            "source_record_ids": [str(s_occ.id), str(e_occ.id)],
                            "dq_status": "CLEAN",
                        })
            else:
                # Single occurrence selection per call
                s_occ: EventOccurrence | None = None
                e_occ: EventOccurrence | None = None

                if occurrence_selection == "first":
                    s_occ = start_occs[0] if start_occs else None
                    e_occ = end_occs[0] if end_occs else None
                elif occurrence_selection == "last":
                    s_occ = start_occs[-1] if start_occs else None
                    e_occ = end_occs[-1] if end_occs else None
                elif occurrence_selection == "nth":
                    s_occ = start_occs[occurrence_n - 1] if len(start_occs) >= occurrence_n else None
                    e_occ = end_occs[occurrence_n - 1] if len(end_occs) >= occurrence_n else None

                if not s_occ or not e_occ:
                    per_call_results.append({
                        "vessel_call_id": str(vc.id),
                        "vcn": vc.vcn,
                        "vessel_name": vc.vessel_name,
                        "status": "UNAVAILABLE",
                        "duration_hours": None,
                        "unavailable_reason": f"Missing {start_event if not s_occ else end_event} (selection: {occurrence_selection})",
                        "source_record_ids": [str(o.id) for o in [s_occ, e_occ] if o],
                        "dq_status": "MISSING_DATA",
                    })
                else:
                    delta = (e_occ.utc_value - s_occ.utc_value).total_seconds() / 3600.0
                    dur_h = round(delta, 6)
                    durations.append(dur_h)
                    per_call_results.append({
                        "vessel_call_id": str(vc.id),
                        "vcn": vc.vcn,
                        "vessel_name": vc.vessel_name,
                        "status": "AVAILABLE",
                        "duration_hours": dur_h,
                        "start_time": s_occ.utc_value.isoformat(),
                        "end_time": e_occ.utc_value.isoformat(),
                        "start_event_occurrence_id": str(s_occ.id),
                        "end_event_occurrence_id": str(e_occ.id),
                        "source_record_ids": [str(s_occ.id), str(e_occ.id)],
                        "dq_status": "CLEAN",
                    })

        # 4. Statistical aggregation via Polars
        aggregate: dict[str, Any] = {
            "observation_count": len(durations),
            "missing_count": len(per_call_results) - len(durations),
            "percentile_method": "linear_interpolation",
        }

        if durations:
            s = pl.Series("durations", durations, dtype=pl.Float64)
            obs_cnt = len(s)
            mean_val = round(float(s.mean()), 6)
            median_val = round(float(s.median()), 6)
            std_val = round(float(s.std()), 6) if obs_cnt > 1 else 0.0

            aggregate.update({
                "mean_hours": mean_val,
                "median_hours": median_val,
                "std_hours": std_val,
                "cv": round(std_val / mean_val, 4) if abs(mean_val) >= 0.001 else None,
                "min_hours": round(float(s.min()), 6),
                "max_hours": round(float(s.max()), 6),
                "p25_hours": round(float(s.quantile(0.25, interpolation="linear")), 6),
                "p75_hours": round(float(s.quantile(0.75, interpolation="linear")), 6),
                "p90_hours": round(float(s.quantile(0.90, interpolation="linear")), 6),
                "p95_hours": round(float(s.quantile(0.95, interpolation="linear")), 6),
                "tail_risk_ratio": round(float(s.quantile(0.90, interpolation="linear")) / median_val, 4) if median_val > 0 else None,
                "small_sample_warning": obs_cnt < 5,
            })
        else:
            aggregate.update({
                "mean_hours": None,
                "median_hours": None,
                "std_hours": None,
                "cv": None,
                "min_hours": None,
                "max_hours": None,
                "p25_hours": None,
                "p75_hours": None,
                "p90_hours": None,
                "p95_hours": None,
                "tail_risk_ratio": None,
                "small_sample_warning": True,
            })

        # 5. Outliers and Distribution
        outliers: list[dict[str, Any]] = []
        distribution: list[dict[str, Any]] = []
        p90 = aggregate.get("p90_hours")

        if durations:
            for r in per_call_results:
                dur = r.get("duration_hours")
                if dur is not None and ((p90 is not None and dur > p90) or dur < 0):
                    outliers.append(r)

            # Build histogram buckets (5 bins)
            min_d = aggregate["min_hours"]
            max_d = aggregate["max_hours"]
            if min_d is not None and max_d is not None and max_d > min_d:
                step = (max_d - min_d) / 5.0
                for b_idx in range(5):
                    b_start = round(min_d + b_idx * step, 2)
                    b_end = round(b_start + step, 2)
                    cnt = sum(1 for d in durations if (b_start <= d < b_end) or (b_idx == 4 and d == b_end))
                    distribution.append({
                        "bin_label": f"{b_start}h – {b_end}h",
                        "start_hours": b_start,
                        "end_hours": b_end,
                        "count": cnt,
                        "pct": round((cnt / len(durations)) * 100, 1),
                    })

        methodology = {
            "eligibility": "All active, non-merged canonical vessel calls with eligible paired event timestamps",
            "exclusions": "Quarantined observations with critical quality issues are excluded by default",
            "missing_events": f"{aggregate['missing_count']} calls lacked required timestamp occurrences",
            "percentile_method": "Linear interpolation (pl.quantile with linear interpolation per spec §10.2)",
            "formula_version": "1.0",
            "sample_size": aggregate["observation_count"],
        }

        # 6. Optionally save definition to catalogue
        saved_def_id = None
        if save_as_name:
            existing_def = self.db.execute(
                select(LeadTimeDefinition).where(LeadTimeDefinition.name == save_as_name)
            ).scalar_one_or_none()
            if not existing_def:
                custom_def = LeadTimeDefinition(
                    name=save_as_name,
                    start_event=start_event,
                    end_event=end_event,
                    description=description or f"Custom lead-time: {start_event} → {end_event}",
                    formula_version="1.0",
                    unit="hours",
                    null_handling="UNAVAILABLE",
                    occurrence_selection=occurrence_selection,
                    availability_status="COMPUTABLE",
                    required_events=[start_event, end_event],
                    custom_builder=True,
                    created_by_user=created_by_user,
                )
                self.db.add(custom_def)
                self.db.commit()
                saved_def_id = str(custom_def.id)
            else:
                saved_def_id = str(existing_def.id)

        return {
            "formula": f"{start_event} → {end_event}",
            "start_event": start_event,
            "end_event": end_event,
            "occurrence_selection": occurrence_selection,
            "formula_version": "1.0",
            "saved_definition_id": saved_def_id,
            "calculated_at": datetime.now(UTC).isoformat(),
            "aggregate": aggregate,
            "distribution": distribution,
            "outliers": outliers,
            "methodology": methodology,
            "results": per_call_results,
            "traceability": {
                "tenant_id": self.tenant_id,
                "exclude_quarantined": exclude_quarantined,
                "movement_scope": movement_scope,
                "percentile_method": "linear_interpolation",
            },
        }
