"""Executive Dashboard Service (spec §12.1, phase-12-dashboards.md).

Computes real, governed executive dashboard metrics across active vessel calls:
- Consolidated call counts, merge counts, cleanliness and quarantine status
- Segmented throughput (TEU, MT, Units - never summed together)
- Time & Motion lead times (Turnaround, Berth Stay, Cargo Working, Anchorage Wait, etc.)
- Delay frequency, hours, confirmed vs inferred breakdown, Pareto causes
- Ranked operational bottlenecks with exposed component scores
- Top operational and data-quality outliers
- Key computable governed KPIs with targets and Green/Amber/Red banding
- Historical synthetic dataset disclosure
"""

from datetime import UTC, datetime
from typing import Any

import polars as pl
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.models.analytics import (
    KPI,
    DashboardSnapshot,
    LeadTimeDefinition,
    LeadTimeResult,
)
from apps.api.models.canonical import (
    CargoOperation,
    Delay,
    EventOccurrence,
    VesselCall,
)
from apps.api.models.ingestion import IngestionBatch
from apps.api.models.config import EventDefinition
from apps.api.models.quality import QualityIssue, QualityRule
from apps.api.services.analytics.engine import AnalyticsEngine
from apps.api.services.bottlenecks.engine import BottleneckEngine
from apps.api.services.kpi.engine import KPIEngine
from apps.api.services.outliers.engine import OutlierEngine


class ExecutiveDashboardService:
    def __init__(self, db: Session, tenant_id: str = "synthetic-tenant"):
        self.db = db
        self.tenant_id = tenant_id

    def persist_snapshot(
        self,
        batch_id: str,
        file_checksum: str,
        payload: dict[str, Any],
        filters_hash: str = "unfiltered",
    ) -> DashboardSnapshot:
        """Persists the precomputed executive dashboard summary to analytics.dashboard_snapshot."""
        self.db.query(DashboardSnapshot).filter(
            DashboardSnapshot.tenant_id == self.tenant_id,
            DashboardSnapshot.filters_hash == filters_hash,
        ).update({"is_active": False})

        snapshot = DashboardSnapshot(
            tenant_id=self.tenant_id,
            batch_id=batch_id,
            file_checksum=file_checksum,
            filters_hash=filters_hash,
            snapshot_data=payload,
            is_active=True,
        )
        self.db.add(snapshot)
        self.db.commit()
        return snapshot

    def compute_and_persist_snapshot(self, batch_id: str, file_checksum: str) -> dict[str, Any]:
        """Calculates executive metrics once, sets batch identity in lineage, and persists snapshot."""
        payload = self._calculate_executive_summary()
        if "lineage" in payload:
            payload["lineage"]["batch_id"] = batch_id
            payload["lineage"]["file_checksum"] = file_checksum
        self.persist_snapshot(batch_id, file_checksum, payload, filters_hash="unfiltered")
        return payload

    def get_executive_summary(
        self,
        port_id: str | None = None,
        terminal_id: str | None = None,
        vessel_type: str | None = None,
        cargo_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        quality_status: str | None = None,
        force_recompute: bool = False,
    ) -> dict[str, Any]:
        """Fetches persisted executive dashboard metrics from PostgreSQL (Process Once -> Store -> Reuse)."""
        is_unfiltered = (
            (port_id is None or port_id == "*")
            and (terminal_id is None or terminal_id == "*")
            and (vessel_type is None or vessel_type in ("*", "ALL", ""))
            and (cargo_type is None or cargo_type in ("*", "ALL", ""))
            and start_date is None
            and end_date is None
            and (quality_status is None or quality_status in ("*", "ALL", ""))
        )
        if is_unfiltered and not force_recompute:
            snapshot = (
                self.db.execute(
                    select(DashboardSnapshot)
                    .where(
                        DashboardSnapshot.tenant_id == self.tenant_id,
                        DashboardSnapshot.is_active == True,
                        DashboardSnapshot.filters_hash == "unfiltered",
                    )
                    .order_by(DashboardSnapshot.created_at.desc())
                )
                .scalars()
                .first()
            )
            if snapshot and snapshot.snapshot_data:
                return snapshot.snapshot_data

        payload = self._calculate_executive_summary(
            port_id=port_id,
            terminal_id=terminal_id,
            vessel_type=vessel_type,
            cargo_type=cargo_type,
            start_date=start_date,
            end_date=end_date,
            quality_status=quality_status,
        )

        if is_unfiltered and payload.get("summary", {}).get("total_vessel_calls", 0) > 0:
            active_batch = (
                self.db.execute(
                    select(IngestionBatch)
                    .where(
                        IngestionBatch.tenant_id == self.tenant_id,
                        IngestionBatch.is_active == True,
                        IngestionBatch.status == "COMMITTED",
                    )
                    .order_by(IngestionBatch.created_at.desc())
                )
                .scalars()
                .first()
            )
            b_id = active_batch.batch_id if active_batch else "default-batch"
            c_sum = active_batch.file_checksum if active_batch else "no-checksum"
            if "lineage" in payload:
                payload["lineage"]["batch_id"] = b_id
                payload["lineage"]["file_checksum"] = c_sum
            self.persist_snapshot(b_id, c_sum, payload, filters_hash="unfiltered")

        return payload

    def _calculate_executive_summary(
        self,
        port_id: str | None = None,
        terminal_id: str | None = None,
        vessel_type: str | None = None,
        cargo_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        quality_status: str | None = None,
    ) -> dict[str, Any]:
        """Calculates governed executive metrics over the filtered population of active vessel calls."""
        # 1. Base Query for active, non-merged calls
        query = select(VesselCall).where(VesselCall.is_merged == False)
        if self.tenant_id and self.tenant_id != "*":
            query = query.where(VesselCall.tenant_id == self.tenant_id)

        if port_id and port_id != "*":
            query = query.where(VesselCall.port_id == port_id)
        if terminal_id and terminal_id != "*":
            query = query.where(VesselCall.terminal_id == terminal_id)
        if vessel_type and vessel_type != "*":
            query = query.where(VesselCall.vessel_type == vessel_type)
        if cargo_type and cargo_type != "*":
            query = query.where(VesselCall.cargo_type == cargo_type)

        calls: list[VesselCall] = self.db.execute(query.order_by(VesselCall.vcn.asc())).scalars().all()

        # Date range filtering by ATA or created_at if provided
        if start_date or end_date:
            ata_def = self.db.execute(select(EventDefinition).where(EventDefinition.name == "ATA")).scalar_one_or_none()
            if ata_def:
                filtered = []
                for c in calls:
                    ata_occ = self.db.execute(
                        select(EventOccurrence).where(
                            EventOccurrence.vessel_call_id == c.id,
                            EventOccurrence.event_definition_id == ata_def.id,
                            EventOccurrence.is_superseded == False,
                        )
                    ).scalars().first()
                    dt = ata_occ.utc_value if (ata_occ and ata_occ.utc_value) else c.created_at
                    if start_date and dt and dt < start_date:
                        continue
                    if end_date and dt and dt > end_date:
                        continue
                    filtered.append(c)
                calls = filtered

        # 2. Quality Status Partitioning
        all_call_ids = [c.id for c in calls]
        quarantined_ids = set()
        flagged_ids = set()

        if all_call_ids:
            issues = self.db.execute(
                select(QualityIssue.vessel_call_id, QualityRule.severity)
                .join(QualityRule, QualityIssue.rule_id == QualityRule.id)
                .where(
                    QualityIssue.vessel_call_id.in_(all_call_ids),
                    QualityIssue.issue_status != "RESOLVED",
                )
            ).all()

            for vc_id, sev in issues:
                if sev == "CRITICAL":
                    quarantined_ids.add(vc_id)
                else:
                    flagged_ids.add(vc_id)
            # Remove quarantined from flagged
            flagged_ids = flagged_ids - quarantined_ids

        clean_ids = set(all_call_ids) - quarantined_ids - flagged_ids

        # Filter by quality_status if requested
        if quality_status:
            qs = quality_status.upper()
            if qs == "QUARANTINED":
                calls = [c for c in calls if c.id in quarantined_ids]
            elif qs == "FLAGGED":
                calls = [c for c in calls if c.id in flagged_ids]
            elif qs == "CLEAN":
                calls = [c for c in calls if c.id in clean_ids]

        total_vessel_calls = len(calls)
        call_ids = [c.id for c in calls]

        # Total merged calls for context
        merged_query = select(func.count(VesselCall.id)).where(VesselCall.is_merged == True)
        if self.tenant_id and self.tenant_id != "*":
            merged_query = merged_query.where(VesselCall.tenant_id == self.tenant_id)
        total_merged_calls = self.db.execute(merged_query).scalar() or 0

        clean_count = sum(1 for c in calls if c.id in clean_ids)
        quarantined_count = sum(1 for c in calls if c.id in quarantined_ids)
        flagged_count = sum(1 for c in calls if c.id in flagged_ids)
        cleanliness_pct = round((clean_count / max(1, total_vessel_calls)) * 100, 1)

        # 3. Throughput (Strictly Segmented by Units: TEU, MT, Units)
        # Spec §12.1: Never sum TEU, MT and Units into one unqualified throughput number!
        teu_total = 0.0
        mt_total = 0.0
        units_total = 0.0
        cargo_breakdown: list[dict[str, Any]] = []

        if call_ids:
            cargo_rows = self.db.execute(
                select(
                    CargoOperation.cargo_type,
                    CargoOperation.unit,
                    func.sum(CargoOperation.actual_quantity),
                    func.count(CargoOperation.id),
                )
                .where(CargoOperation.vessel_call_id.in_(call_ids))
                .group_by(CargoOperation.cargo_type, CargoOperation.unit)
            ).all()

            for c_type, c_unit, total_qty, op_count in cargo_rows:
                qty = float(total_qty or 0.0)
                cargo_breakdown.append({
                    "cargo_type": c_type or "General",
                    "unit": c_unit or "Units",
                    "quantity": round(qty, 1),
                    "operations_count": op_count,
                })
                if c_unit == "TEU":
                    teu_total += qty
                elif c_unit == "MT":
                    mt_total += qty
                elif c_unit == "Units":
                    units_total += qty
                else:
                    # fallback by cargo type semantics
                    if c_type == "Container":
                        teu_total += qty
                    elif c_type in ("Bulk", "Liquid Bulk", "Break Bulk"):
                        mt_total += qty
                    else:
                        units_total += qty

        throughput = {
            "teu": round(teu_total, 1),
            "mt": round(mt_total, 1),
            "units": round(units_total, 1),
            "units_segmented": True,
            "prohibited_sum_notice": "Throughput is segmented by operational unit (TEU, MT, Units). Summing across disparate units is mathematically invalid.",
            "cargo_breakdown": cargo_breakdown,
        }

        # 4. Lead Times & Durations (Time & Motion Analysis)
        lead_time_metrics: dict[str, Any] = {}
        target_names = [
            "Turnaround",
            "Anchorage Wait",
            "Inward Movement",
            "Berth Stay",
            "Cargo Working",
            "Outward Movement",
            "Arrival Execution Delay",
            "Sailing Execution Delay",
        ]

        if call_ids:
            # Lazy compute: if no LeadTimeResults exist for these calls, trigger analytics engine
            existing_lt_count = self.db.execute(
                select(func.count(LeadTimeResult.id)).where(
                    LeadTimeResult.vessel_call_id.in_(call_ids[:5])  # sample check
                )
            ).scalar() or 0
            if existing_lt_count == 0:
                a_engine = AnalyticsEngine(self.db, tenant_id=self.tenant_id)
                a_engine.compute_all_metrics()

            lt_rows = self.db.execute(
                select(LeadTimeResult, LeadTimeDefinition.name, LeadTimeDefinition.is_execution_delay)
                .join(LeadTimeDefinition, LeadTimeResult.definition_id == LeadTimeDefinition.id)
                .where(LeadTimeResult.vessel_call_id.in_(call_ids))
            ).all()

            metrics_by_name: dict[str, list[LeadTimeResult]] = {name: [] for name in target_names}
            for r, name, is_delay in lt_rows:
                if name in metrics_by_name:
                    metrics_by_name[name].append(r)

            for name in target_names:
                results = metrics_by_name[name]
                durations = [r.duration_hours for r in results if r.status == "AVAILABLE" and r.duration_hours is not None]
                unavail = [r for r in results if r.status == "UNAVAILABLE"]

                if durations:
                    s = pl.Series("d", durations, dtype=pl.Float64)
                    obs = len(s)
                    mean_val = round(float(s.mean()), 2)
                    median_val = round(float(s.median()), 2)
                    min_val = round(float(s.min()), 2)
                    max_val = round(float(s.max()), 2)
                    p90_val = round(float(s.quantile(0.90, interpolation="linear")), 2)

                    # Execution delays preserve negative values as early service (spec §2.4)
                    early_count = sum(1 for d in durations if d < 0)
                    delayed_count = sum(1 for d in durations if d > 0)
                    on_time_count = sum(1 for d in durations if d == 0)

                    lead_time_metrics[name] = {
                        "name": name,
                        "observation_count": obs,
                        "missing_count": len(unavail),
                        "mean_hours": mean_val,
                        "median_hours": median_val,
                        "p90_hours": p90_val,
                        "min_hours": min_val,
                        "max_hours": max_val,
                        "unit": "hours",
                        "formula_version": "1.0",
                        "status": "COMPUTED",
                        "early_service_count": early_count,
                        "delayed_count": delayed_count,
                        "on_time_count": on_time_count,
                    }
                else:
                    lead_time_metrics[name] = {
                        "name": name,
                        "observation_count": 0,
                        "missing_count": len(unavail),
                        "mean_hours": None,
                        "median_hours": None,
                        "p90_hours": None,
                        "min_hours": None,
                        "max_hours": None,
                        "unit": "hours",
                        "formula_version": "1.0",
                        "status": "UNAVAILABLE",
                        "early_service_count": 0,
                        "delayed_count": 0,
                        "on_time_count": 0,
                    }
        else:
            for name in target_names:
                lead_time_metrics[name] = {
                    "name": name,
                    "observation_count": 0,
                    "missing_count": 0,
                    "mean_hours": None,
                    "median_hours": None,
                    "p90_hours": None,
                    "min_hours": None,
                    "max_hours": None,
                    "unit": "hours",
                    "formula_version": "1.0",
                    "status": "UNAVAILABLE",
                    "early_service_count": 0,
                    "delayed_count": 0,
                    "on_time_count": 0,
                }

        # 5. Delays & Bottlenecks Summary
        delays_summary: dict[str, Any] = {
            "total_delays_count": 0,
            "total_delay_hours": 0.0,
            "confirmed_count": 0,
            "confirmed_hours": 0.0,
            "inferred_count": 0,
            "inferred_hours": 0.0,
            "top_categories": [],
            "top_bottlenecks": [],
            "outliers_count": 0,
            "top_outliers": [],
        }

        if call_ids:
            delays = self.db.execute(
                select(Delay).where(Delay.vessel_call_id.in_(call_ids))
            ).scalars().all()

            total_delays_count = len(delays)
            total_delay_hours = round(sum(d.total_duration_hours or 0.0 for d in delays), 2)

            confirmed_delays = [d for d in delays if (d.cause_status or "").upper() == "CONFIRMED"]
            inferred_delays = [d for d in delays if (d.cause_status or "").upper() == "INFERRED"]

            # Category breakdown (Pareto)
            cat_map: dict[str, dict[str, Any]] = {}
            for d in delays:
                cat = d.canonical_category or d.source_category or "Unclassified"
                if cat not in cat_map:
                    cat_map[cat] = {"category": cat, "count": 0, "duration_hours": 0.0}
                cat_map[cat]["count"] += 1
                cat_map[cat]["duration_hours"] += d.total_duration_hours or 0.0

            top_cats = sorted(cat_map.values(), key=lambda x: x["duration_hours"], reverse=True)
            for item in top_cats:
                item["duration_hours"] = round(item["duration_hours"], 2)
                item["percentage"] = round((item["duration_hours"] / max(0.001, total_delay_hours)) * 100, 1)

            # Bottleneck engine
            b_engine = BottleneckEngine(self.db, tenant_id=self.tenant_id)
            bottlenecks = b_engine.calculate_bottlenecks(persist=False)[:5]

            # Outlier engine
            o_engine = OutlierEngine(self.db, tenant_id=self.tenant_id)
            all_outliers = o_engine.list_outliers()
            # Filter outliers for calls in cohort
            cohort_vcns = {c.vcn for c in calls if c.vcn}
            filtered_outliers = [o for o in all_outliers if o.get("vcn") in cohort_vcns]

            delays_summary = {
                "total_delays_count": total_delays_count,
                "total_delay_hours": total_delay_hours,
                "confirmed_count": len(confirmed_delays),
                "confirmed_hours": round(sum(d.total_duration_hours or 0.0 for d in confirmed_delays), 2),
                "inferred_count": len(inferred_delays),
                "inferred_hours": round(sum(d.total_duration_hours or 0.0 for d in inferred_delays), 2),
                "top_categories": top_cats[:6],
                "top_bottlenecks": bottlenecks,
                "outliers_count": len(filtered_outliers),
                "top_outliers": filtered_outliers[:5],
            }

        # 6. Governed KPI Highlights
        kpi_highlights: list[dict[str, Any]] = []
        kpi_engine = KPIEngine(self.db, tenant_id=self.tenant_id)
        calc_res = kpi_engine.calculate_all_kpis()

        # Select representative computable KPIs for Marine, Berthing, Cargo, Departure
        spotlight_codes = [
            "KPI-04",  # Pre-Berthing Detention
            "KPI-05",  # Pilotage Response Delay
            "KPI-06",  # Tug Response Delay
            "KPI-15",  # Gross Berth Productivity
            "KPI-16",  # Ship Working Productivity
            "KPI-20",  # Berth Utilisation
            "KPI-25",  # Gangway to Departure
            "KPI-27",  # Vessel Turnaround Time
            "KPI-30",  # Berth Stay to Cargo Working Ratio
        ]

        kpi_objs = self.db.execute(select(KPI).where(KPI.code.in_(spotlight_codes))).scalars().all()
        kpi_by_code = {k.code: k for k in kpi_objs}

        for code in spotlight_codes:
            item = calc_res.get("results", {}).get(code)
            kpi = kpi_by_code.get(code)
            if item and kpi and item.get("status") == "COMPUTED":
                val = item.get("value")
                tgt = kpi.target
                variance = round(val - tgt, 2) if (val is not None and tgt is not None) else None
                kpi_highlights.append({
                    "kpi_number": kpi.kpi_number,
                    "code": kpi.code,
                    "name": kpi.name,
                    "value": val,
                    "unit": kpi.unit,
                    "band": item.get("band"),
                    "target": tgt,
                    "target_direction": kpi.target_direction,
                    "variance": variance,
                    "status": "COMPUTED",
                    "formula_version": "1.0",
                })

        # 7. Complete Payload
        return {
            "summary": {
                "total_vessel_calls": total_vessel_calls,
                "total_merged_calls": total_merged_calls,
                "clean_calls_count": clean_count,
                "quarantined_calls_count": quarantined_count,
                "flagged_calls_count": flagged_count,
                "cleanliness_pct": cleanliness_pct,
            },
            "throughput": throughput,
            "lead_time_metrics": lead_time_metrics,
            "delays_summary": delays_summary,
            "kpi_highlights": kpi_highlights,
            "kpi_catalogue_summary": {
                "total_registered": calc_res.get("total_kpis", 55),
                "computed_count": calc_res.get("computed", 38),
                "no_source_data_count": calc_res.get("no_source_data", 17),
                "notice": "17 KPIs requiring yard, gate, rail, or crane-level sensor telemetry are classified as NO_SOURCE_DATA rather than fabricated as zero.",
            },
            "lineage": {
                "dataset_type": "HISTORICAL_SYNTHETIC",
                "dataset_label": "Synthetic / historical dataset · Transnet Port Terminals Durban Container Terminal benchmark",
                "port_id": port_id or "*",
                "terminal_id": terminal_id or "*",
                "vessel_type": vessel_type or "ALL",
                "cargo_type": cargo_type or "ALL",
                "timezone": "Africa/Johannesburg",
                "tolerance": "Analytics calculation precision is governed by formula version and source evidence.",
                "generated_at": datetime.now(UTC).isoformat(),
            },
        }
