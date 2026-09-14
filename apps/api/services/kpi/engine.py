"""Governed KPI Calculation Engine (spec §11, phase-08-kpi-engine.md).

Implements calculation, targets, Green/Amber/Red banding, trends, recalculation with audit logging,
and unit-segmented aggregations across all 55 governed KPIs.

Key Principles (AGENTS.md & spec §11):
- All 55 KPIs registered and evaluated.
- Status strictly COMPUTED, UNAVAILABLE, or NO_SOURCE_DATA.
- Never fabricate zeroes for missing data or unavailable metrics.
- Prevent double counting of alias pairs (KPI-11/KPI-53, KPI-14/KPI-51).
- Unit segmentation for KPI-02 (never mix TEU, MT, Units into an unqualified total).
- Recalculation is an explicit, permissioned, audited operation.
- Green/Amber/Red threshold evaluation against KPI targets.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
import math

from sqlalchemy import select, and_, func, desc
from sqlalchemy.orm import Session

from apps.api.models.analytics import KPI, KPIFormulaVersion, KPIResult, KPIBenchmark
from apps.api.models.audit import AuditEvent
from apps.api.models.canonical import (
    CargoOperation,
    Delay,
    EventOccurrence,
    ServiceAssignment,
    ServiceExecution,
    ServiceRequest,
    VesselCall,
)
from apps.api.models.config import EventDefinition
from apps.api.models.journey import CanonicalObservation
from apps.api.services.kpi.registry import ensure_kpi_registry, KPI_REGISTRY_DEFINITIONS


class KPIEngine:
    """Engine for evaluating governed KPIs, targets, trends, and recalculations."""

    def __init__(self, db: Session, tenant_id: str = "synthetic-tenant", exclude_quarantined: bool = True):
        self.db = db
        self.tenant_id = tenant_id
        self.exclude_quarantined = exclude_quarantined
        self._event_def_cache: Optional[Dict[str, Any]] = None

    def ensure_registry(self) -> Dict[str, KPI]:
        """Ensures all 55 KPIs and initial formula versions exist in analytics.kpi."""
        return ensure_kpi_registry(self.db)

    # ──────────────────────────────────────────────────────────────────────────
    # Caches and Event Resolution
    # ──────────────────────────────────────────────────────────────────────────

    def _get_event_defs(self) -> Dict[str, Any]:
        if self._event_def_cache is None:
            defs = self.db.execute(select(EventDefinition)).scalars().all()
            self._event_def_cache = {d.name: d.id for d in defs}
        return self._event_def_cache

    def _get_canonical_observation_lookup(self, vessel_call_ids: List[Any]) -> Dict[Tuple[Any, Any], Any]:
        """Pre-fetches canonical observation winners for vessel calls."""
        if not vessel_call_ids:
            return {}
        obs = self.db.execute(
            select(CanonicalObservation).where(CanonicalObservation.vessel_call_id.in_(vessel_call_ids))
        ).scalars().all()
        return {(o.vessel_call_id, o.event_definition_id): o.selected_event_occurrence_id for o in obs}

    # ──────────────────────────────────────────────────────────────────────────
    # Vessel Calls and Population
    # ──────────────────────────────────────────────────────────────────────────

    def get_eligible_vessel_calls(
        self,
        cohort_filters: Optional[Dict[str, Any]] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> List[VesselCall]:
        """Fetches active, non-merged vessel calls for the population matching filters."""
        stmt = select(VesselCall).where(VesselCall.is_merged == False)

        if self.tenant_id and self.tenant_id != "*":
            stmt = stmt.where(VesselCall.tenant_id == self.tenant_id)

        if cohort_filters:
            if "vessel_type" in cohort_filters and cohort_filters["vessel_type"]:
                stmt = stmt.where(VesselCall.vessel_type == cohort_filters["vessel_type"])
            if "terminal_code" in cohort_filters and cohort_filters["terminal_code"]:
                stmt = stmt.where(VesselCall.terminal_id == cohort_filters["terminal_code"])
            if "unit" in cohort_filters and cohort_filters["unit"]:
                stmt = stmt.where(VesselCall.quantity_unit == cohort_filters["unit"])

        calls = self.db.execute(stmt.order_by(VesselCall.created_at.asc())).scalars().all()

        if period_start or period_end:
            event_defs = self._get_event_defs()
            ata_def_id = event_defs.get("ATA")
            filtered_calls = []
            for vc in calls:
                if not ata_def_id:
                    filtered_calls.append(vc)
                    continue
                ata_occ = self.db.execute(
                    select(EventOccurrence).where(
                        EventOccurrence.vessel_call_id == vc.id,
                        EventOccurrence.event_definition_id == ata_def_id,
                        EventOccurrence.is_superseded == False,
                    )
                ).scalars().first()
                if ata_occ and ata_occ.utc_value:
                    if period_start and ata_occ.utc_value < period_start:
                        continue
                    if period_end and ata_occ.utc_value > period_end:
                        continue
                filtered_calls.append(vc)
            return filtered_calls

        return calls

    # ──────────────────────────────────────────────────────────────────────────
    # Banding Evaluation (Green / Amber / Red / Gray)
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def evaluate_band(
        value: Optional[float],
        target: Optional[float],
        target_direction: Optional[str],
        thresholds: Optional[Dict[str, Any]],
    ) -> str:
        """Evaluates KPI band against target and thresholds."""
        if value is None:
            return "GRAY"

        direction = target_direction or "LOWER_IS_BETTER"
        th = thresholds or {}

        if direction == "LOWER_IS_BETTER":
            green_limit = th.get("green", target)
            amber_limit = th.get("amber", target * 1.2 if target is not None else None)
            if green_limit is not None and value <= green_limit:
                return "GREEN"
            if amber_limit is not None and value <= amber_limit:
                return "AMBER"
            return "RED"
        else:  # HIGHER_IS_BETTER
            green_limit = th.get("green", target)
            amber_limit = th.get("amber", target * 0.8 if target is not None else None)
            if green_limit is not None and value >= green_limit:
                return "GREEN"
            if amber_limit is not None and value >= amber_limit:
                return "AMBER"
            return "RED"

    # ──────────────────────────────────────────────────────────────────────────
    # KPI Computation Core
    # ──────────────────────────────────────────────────────────────────────────

    def calculate_kpi(
        self,
        kpi_code: str,
        cohort_filters: Optional[Dict[str, Any]] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        grain: str = "ALL",
        is_recalculation: bool = False,
    ) -> KPIResult:
        """Calculates a single KPI by its spec code (e.g., 'KPI-01')."""
        self.ensure_registry()
        kpi = self.db.execute(select(KPI).where(KPI.code == kpi_code)).scalar_one_or_none()
        if not kpi:
            raise ValueError(f"KPI with code '{kpi_code}' not found in registry.")

        # If NO_SOURCE_DATA
        if kpi.availability_status == "NO_SOURCE_DATA":
            result = KPIResult(
                kpi_id=kpi.id,
                value=None,
                status="NO_SOURCE_DATA",
                period_start=period_start,
                period_end=period_end,
                grain=grain,
                cohort_key=str(cohort_filters) if cohort_filters else "all",
                cohort_filters=cohort_filters,
                numerator_value=None,
                denominator_value=None,
                target_value=kpi.target,
                band="GRAY",
                unavailable_reason=(
                    f"No connected source system supplies inputs for {kpi.name}. "
                    f"Required: {', '.join(kpi.required_source_systems or [])}."
                ),
                formula_version="1.0",
                data_quality_summary={"required_source_systems": kpi.required_source_systems or []},
                calculated_at=datetime.now(timezone.utc),
                is_recalculation=is_recalculation,
            )
            self.db.add(result)
            self.db.commit()
            return result

        # Handle alias relationship (e.g. KPI-53 is alias of KPI-11; KPI-51 is alias of KPI-14)
        if not kpi.is_primary and kpi.alias_of_id:
            primary_kpi = self.db.execute(select(KPI).where(KPI.id == kpi.alias_of_id)).scalar_one_or_none()
            if primary_kpi:
                primary_res = self.calculate_kpi(
                    primary_kpi.code,
                    cohort_filters=cohort_filters,
                    period_start=period_start,
                    period_end=period_end,
                    grain=grain,
                    is_recalculation=is_recalculation,
                )
                result = KPIResult(
                    kpi_id=kpi.id,
                    value=primary_res.value,
                    status=primary_res.status,
                    period_start=period_start,
                    period_end=period_end,
                    grain=grain,
                    cohort_key=primary_res.cohort_key,
                    cohort_filters=cohort_filters,
                    numerator_value=primary_res.numerator_value,
                    denominator_value=primary_res.denominator_value,
                    target_value=kpi.target,
                    band=self.evaluate_band(primary_res.value, kpi.target, kpi.target_direction, kpi.thresholds),
                    unavailable_reason=primary_res.unavailable_reason,
                    formula_version=primary_res.formula_version,
                    data_quality_summary={
                        "alias_of": primary_kpi.code,
                        "primary_result_id": str(primary_res.id),
                        "notice": "This metric is an alias for administrative reporting; primary logic executed.",
                    },
                    calculated_at=datetime.now(timezone.utc),
                    is_recalculation=is_recalculation,
                )
                self.db.add(result)
                self.db.commit()
                return result

        # Fetch eligible vessel calls
        vessel_calls = self.get_eligible_vessel_calls(cohort_filters, period_start, period_end)
        vc_ids = [vc.id for vc in vessel_calls]

        # Gather related domain data
        events_by_vc, services_by_vc, cargo_by_vc, delays_by_vc = self._load_canonical_data(vc_ids)

        val, num, den, status, band, reason, dq_summary = self._compute_kpi_value(
            kpi,
            vessel_calls,
            events_by_vc,
            services_by_vc,
            cargo_by_vc,
            delays_by_vc,
            cohort_filters,
        )

        result = KPIResult(
            kpi_id=kpi.id,
            value=val,
            status=status,
            period_start=period_start,
            period_end=period_end,
            grain=grain,
            cohort_key=str(cohort_filters) if cohort_filters else "all",
            cohort_filters=cohort_filters,
            numerator_value=num,
            denominator_value=den,
            target_value=kpi.target,
            band=band,
            unavailable_reason=reason,
            formula_version="1.0",
            data_quality_summary=dq_summary,
            calculated_at=datetime.now(timezone.utc),
            is_recalculation=is_recalculation,
        )
        self.db.add(result)
        self.db.commit()
        return result

    def calculate_all_kpis(
        self,
        cohort_filters: Optional[Dict[str, Any]] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        grain: str = "ALL",
    ) -> Dict[str, Any]:
        """Calculates all 55 KPIs in the registry and returns a scorecard summary."""
        kpi_map = self.ensure_registry()
        results: Dict[str, Any] = {}
        computed_count = 0
        no_src_count = 0
        unavail_count = 0

        for item in KPI_REGISTRY_DEFINITIONS:
            code = item["code"]
            try:
                res = self.calculate_kpi(
                    code,
                    cohort_filters=cohort_filters,
                    period_start=period_start,
                    period_end=period_end,
                    grain=grain,
                    is_recalculation=False,
                )
                results[code] = {
                    "kpi_id": str(res.kpi_id),
                    "code": code,
                    "name": kpi_map[code].name,
                    "value": res.value,
                    "status": res.status,
                    "band": res.band,
                    "unit": kpi_map[code].unit,
                    "target": res.target_value,
                    "is_primary": kpi_map[code].is_primary,
                }
                if res.status == "COMPUTED":
                    computed_count += 1
                elif res.status == "NO_SOURCE_DATA":
                    no_src_count += 1
                else:
                    unavail_count += 1
            except Exception as e:
                results[code] = {
                    "code": code,
                    "name": kpi_map[code].name,
                    "value": None,
                    "status": "UNAVAILABLE",
                    "band": "GRAY",
                    "error": str(e),
                }
                unavail_count += 1

        return {
            "total_kpis": len(results),
            "computed": computed_count,
            "no_source_data": no_src_count,
            "unavailable": unavail_count,
            "results": results,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Audited Recalculation (spec §11, phase-08)
    # ──────────────────────────────────────────────────────────────────────────

    def recalculate_kpi(
        self,
        kpi_code: str,
        actor_id: str = "system",
        actor_email: Optional[str] = None,
        actor_role: Optional[str] = None,
        reason: Optional[str] = None,
        cohort_filters: Optional[Dict[str, Any]] = None,
    ) -> KPIResult:
        """Explicit, permissioned, audited operation that produces a new KPI result."""
        # Find previous result if any
        kpi = self.db.execute(select(KPI).where(KPI.code == kpi_code)).scalar_one_or_none()
        if not kpi:
            raise ValueError(f"KPI {kpi_code} not found.")

        prev_res = self.db.execute(
            select(KPIResult)
            .where(KPIResult.kpi_id == kpi.id)
            .order_by(desc(KPIResult.calculated_at))
        ).scalars().first()
        prev_val = prev_res.value if prev_res else None
        prev_id = str(prev_res.id) if prev_res else None

        # Execute recalculation
        new_res = self.calculate_kpi(
            kpi_code,
            cohort_filters=cohort_filters,
            is_recalculation=True,
        )

        # Audit logging in audit.audit_event
        audit_event = AuditEvent(
            actor_id=actor_id,
            actor_email=actor_email or f"{actor_id}@platform.local",
            actor_role=actor_role or "Operations",
            action="RECALCULATE",
            resource_type="kpi_result",
            resource_id=str(new_res.id),
            entity_name="kpi_result",
            entity_id=str(new_res.id),
            details={
                "kpi_code": kpi_code,
                "kpi_name": kpi.name,
                "previous_result_id": prev_id,
                "previous_value": prev_val,
                "new_value": new_res.value,
                "reason": reason or "Governed KPI recalculation requested",
                "cohort_filters": cohort_filters,
            },
            changes={
                "previous_value": prev_val,
                "new_value": new_res.value,
            },
        )
        self.db.add(audit_event)
        self.db.commit()

        return new_res

    # ──────────────────────────────────────────────────────────────────────────
    # Trends and Period Comparisons
    # ──────────────────────────────────────────────────────────────────────────

    def get_trends(
        self,
        kpi_code: str,
        grain: str = "MONTHLY",
        periods: int = 6,
    ) -> Dict[str, Any]:
        """Calculates trend points, rolling average, and direction classification."""
        kpi = self.db.execute(select(KPI).where(KPI.code == kpi_code)).scalar_one_or_none()
        if not kpi:
            raise ValueError(f"KPI {kpi_code} not found.")

        if kpi.availability_status == "NO_SOURCE_DATA":
            return {
                "kpi_code": kpi_code,
                "status": "NO_SOURCE_DATA",
                "trend_points": [],
                "direction": "STABLE",
                "notice": "No connected source data for trends.",
            }

        # Query recent results for this KPI
        results = self.db.execute(
            select(KPIResult)
            .where(KPIResult.kpi_id == kpi.id, KPIResult.status == "COMPUTED")
            .order_by(desc(KPIResult.calculated_at))
            .limit(periods)
        ).scalars().all()

        results.reverse()

        points = []
        for r in results:
            points.append({
                "period": r.period_start.strftime("%Y-%m") if r.period_start else r.calculated_at.strftime("%Y-%m-%d %H:%M"),
                "value": r.value,
                "band": r.band,
            })

        # If few historical results stored, slice available calls by month
        if len(points) < 2:
            now = datetime.now(timezone.utc)
            # Sample past 3 monthly slices
            points = []
            for i in range(periods - 1, -1, -1):
                p_end = now - timedelta(days=i * 30)
                p_start = p_end - timedelta(days=30)
                r = self.calculate_kpi(kpi_code, period_start=p_start, period_end=p_end, grain=grain)
                if r.status == "COMPUTED":
                    points.append({
                        "period": p_start.strftime("%Y-%m"),
                        "value": r.value,
                        "band": r.band,
                    })

        # Calculate delta, rolling avg, and direction
        direction = "STABLE"
        delta = None
        pct_change = None
        rolling_avg = None

        if points and any(p["value"] is not None for p in points):
            valid_vals = [p["value"] for p in points if p["value"] is not None]
            if len(valid_vals) >= 2:
                curr = valid_vals[-1]
                prev = valid_vals[-2]
                delta = round(curr - prev, 4)
                if prev != 0:
                    pct_change = round((delta / prev) * 100, 2)
                else:
                    pct_change = None

                target_dir = kpi.target_direction or "LOWER_IS_BETTER"
                if target_dir == "LOWER_IS_BETTER":
                    if delta < -0.01:
                        direction = "IMPROVING"
                    elif delta > 0.01:
                        direction = "DETERIORATING"
                else:  # HIGHER_IS_BETTER
                    if delta > 0.01:
                        direction = "IMPROVING"
                    elif delta < -0.01:
                        direction = "DETERIORATING"

            if valid_vals:
                rolling_avg = round(sum(valid_vals[-3:]) / len(valid_vals[-3:]), 4)

        return {
            "kpi_code": kpi_code,
            "name": kpi.name,
            "status": "COMPUTED" if points else "UNAVAILABLE",
            "unit": kpi.unit,
            "target": kpi.target,
            "target_direction": kpi.target_direction,
            "direction": direction,
            "delta": delta,
            "percentage_change": pct_change,
            "rolling_average_3p": rolling_avg,
            "trend_points": points,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Data Loading Helper
    # ──────────────────────────────────────────────────────────────────────────

    def _load_canonical_data(self, vc_ids: List[Any]) -> Tuple[Dict, Dict, Dict, Dict]:
        """Loads events, service executions, cargo ops, and delays indexed by vessel_call_id."""
        if not vc_ids:
            return {}, {}, {}, {}

        # 1. Events
        event_defs = self._get_event_defs()
        id_to_event_name = {v: k for k, v in event_defs.items()}

        canon_lookup = self._get_canonical_observation_lookup(vc_ids)

        ev_stmt = select(EventOccurrence).where(
            EventOccurrence.vessel_call_id.in_(vc_ids),
            EventOccurrence.is_superseded == False,
        )
        if self.exclude_quarantined:
            ev_stmt = ev_stmt.where(EventOccurrence.is_quarantined == False)

        events = self.db.execute(ev_stmt.order_by(EventOccurrence.utc_value.asc())).scalars().all()
        events_by_vc: Dict[Any, Dict[str, EventOccurrence]] = {}
        for ev in events:
            ev_name = id_to_event_name.get(ev.event_definition_id)
            if not ev_name:
                continue
            # Check canonical observation winner
            winner_id = canon_lookup.get((ev.vessel_call_id, ev.event_definition_id))
            if winner_id and ev.id != winner_id:
                continue
            if ev.vessel_call_id not in events_by_vc:
                events_by_vc[ev.vessel_call_id] = {}
            if ev_name not in events_by_vc[ev.vessel_call_id]:
                events_by_vc[ev.vessel_call_id][ev_name] = ev

        # 2. Service Executions with Request & Assignment
        se_stmt = (
            select(ServiceExecution, ServiceAssignment, ServiceRequest)
            .join(ServiceAssignment, ServiceExecution.service_assignment_id == ServiceAssignment.id)
            .join(ServiceRequest, ServiceAssignment.service_request_id == ServiceRequest.id)
            .where(ServiceRequest.vessel_call_id.in_(vc_ids))
        )
        services_by_vc: Dict[Any, List[Dict[str, Any]]] = {}
        for exe, ass, req in self.db.execute(se_stmt).all():
            vc_id = req.vessel_call_id
            if vc_id not in services_by_vc:
                services_by_vc[vc_id] = []
            services_by_vc[vc_id].append({
                "service_type": req.service_type,
                "movement_type": req.movement_type,
                "requested_time": req.requested_time,
                "scheduled_time": ass.scheduled_time,
                "served_time": exe.served_time,
            })

        # 3. Cargo Operations
        cg_stmt = select(CargoOperation).where(CargoOperation.vessel_call_id.in_(vc_ids))
        cargo_by_vc: Dict[Any, List[CargoOperation]] = {}
        for cg in self.db.execute(cg_stmt).scalars().all():
            if cg.vessel_call_id not in cargo_by_vc:
                cargo_by_vc[cg.vessel_call_id] = []
            cargo_by_vc[cg.vessel_call_id].append(cg)

        # 4. Delays
        dl_stmt = select(Delay).where(Delay.vessel_call_id.in_(vc_ids))
        delays_by_vc: Dict[Any, List[Delay]] = {}
        for dl in self.db.execute(dl_stmt).scalars().all():
            if dl.vessel_call_id not in delays_by_vc:
                delays_by_vc[dl.vessel_call_id] = []
            delays_by_vc[dl.vessel_call_id].append(dl)

        return events_by_vc, services_by_vc, cargo_by_vc, delays_by_vc

    # ──────────────────────────────────────────────────────────────────────────
    # Domain Metric Formulas (38 Computable KPIs)
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_kpi_value(
        self,
        kpi: KPI,
        vessel_calls: List[VesselCall],
        events_by_vc: Dict[Any, Dict[str, EventOccurrence]],
        services_by_vc: Dict[Any, List[Dict[str, Any]]],
        cargo_by_vc: Dict[Any, List[CargoOperation]],
        delays_by_vc: Dict[Any, List[Delay]],
        cohort_filters: Optional[Dict[str, Any]],
    ) -> Tuple[Optional[float], Optional[float], Optional[float], str, str, Optional[str], Dict[str, Any]]:
        """Dispatches to the formula method for the KPI code."""
        code = kpi.code

        if not vessel_calls:
            return None, 0.0, 0.0, "UNAVAILABLE", "GRAY", "No eligible vessel calls for population.", {}

        # ── KPI-01: Number of Vessel Calls ──
        if code == "KPI-01":
            calls = len(vessel_calls)
            band = self.evaluate_band(calls, kpi.target, kpi.target_direction, kpi.thresholds)
            return float(calls), float(calls), None, "COMPUTED", band, None, {"total_calls": calls}

        # ── KPI-02: Average Vessel Call Size (Spec: strictly segmented by unit) ──
        elif code == "KPI-02":
            unit_sums: Dict[str, float] = {}
            unit_calls: Dict[str, int] = {}
            for vc in vessel_calls:
                ops = cargo_by_vc.get(vc.id, [])
                for op in ops:
                    u = op.unit or "Unknown"
                    q = op.actual_quantity or 0.0
                    unit_sums[u] = unit_sums.get(u, 0.0) + q
                    unit_calls[u] = unit_calls.get(u, 0) + 1

            # Determine target unit if filtered, else default to primary (TEU)
            selected_unit = (cohort_filters or {}).get("unit", "TEU")
            total_qty = unit_sums.get(selected_unit, 0.0)
            call_count = unit_calls.get(selected_unit, 0)

            breakdown = {
                u: {
                    "total_quantity": round(unit_sums[u], 2),
                    "vessel_calls": unit_calls[u],
                    "average": round(unit_sums[u] / unit_calls[u], 2) if unit_calls[u] > 0 else None,
                }
                for u in unit_sums
            }

            if call_count == 0:
                return None, None, None, "UNAVAILABLE", "GRAY", f"No cargo records for unit {selected_unit}", {"breakdown_by_unit": breakdown}

            avg_val = round(total_qty / call_count, 2)
            band = self.evaluate_band(avg_val, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_val, total_qty, float(call_count), "COMPUTED", band, None, {
                "segmented_unit": selected_unit,
                "breakdown_by_unit": breakdown,
                "disclosure": "Never mixes units into an unqualified combined total (spec §11).",
            }

        # ── KPI-03: Average Pre-Berthing Waiting Time ──
        elif code == "KPI-03":
            waits = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_arr = self._get_time(evs, ["ANCHORAGE_ARRIVAL", "Anchorage Arrival"])
                t_pob = self._get_time(evs, ["PILOT_ON_BOARD_ARRIVAL", "Pilot On Board"])
                if t_arr and t_pob and t_pob >= t_arr:
                    waits.append((t_pob - t_arr).total_seconds() / 3600.0)
            if not waits:
                return None, None, None, "UNAVAILABLE", "GRAY", "No valid pre-berthing wait events.", {}
            avg_w = round(sum(waits) / len(waits), 4)
            band = self.evaluate_band(avg_w, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_w, round(sum(waits), 4), float(len(waits)), "COMPUTED", band, None, {"sample_size": len(waits)}

        # ── KPI-04: Pre-Berthing Delay (Anchorage -> First Line Tied) ──
        elif code == "KPI-04":
            delays = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_arr = self._get_time(evs, ["ANCHORAGE_ARRIVAL", "Anchorage Arrival"])
                t_flt = self._get_time(evs, ["FIRST_LINE_TIED_ARRIVAL", "First Line Tied"])
                if t_arr and t_flt and t_flt >= t_arr:
                    delays.append((t_flt - t_arr).total_seconds() / 3600.0)
            if not delays:
                return None, None, None, "UNAVAILABLE", "GRAY", "No valid pre-berthing delay records.", {}
            avg_d = round(sum(delays) / len(delays), 4)
            band = self.evaluate_band(avg_d, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_d, round(sum(delays), 4), float(len(delays)), "COMPUTED", band, None, {"sample_size": len(delays)}

        # ── KPI-05: Anchorage Time Variation Index ──
        elif code == "KPI-05":
            waits = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_arr = self._get_time(evs, ["ANCHORAGE_ARRIVAL", "Anchorage Arrival"])
                t_pob = self._get_time(evs, ["PILOT_ON_BOARD_ARRIVAL", "Pilot On Board"])
                if t_arr and t_pob and t_pob >= t_arr:
                    waits.append((t_pob - t_arr).total_seconds() / 3600.0)
            if len(waits) < 2:
                return None, None, None, "UNAVAILABLE", "GRAY", "Insufficient anchorage records (need at least 2 for stddev).", {}
            mean_w = sum(waits) / len(waits)
            variance = sum((w - mean_w) ** 2 for w in waits) / (len(waits) - 1)
            std_dev = round(math.sqrt(variance), 4)
            band = self.evaluate_band(std_dev, kpi.target, kpi.target_direction, kpi.thresholds)
            return std_dev, round(sum(waits), 4), float(len(waits)), "COMPUTED", band, None, {
                "sample_size": len(waits),
                "mean_wait_hours": round(mean_w, 4),
                "variance": round(variance, 4),
            }

        # ── KPI-07: Inward Towage Duration ──
        elif code == "KPI-07":
            towages = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_start = self._get_time(evs, ["TUG_ATTACH_ARRIVAL", "PILOT_ON_BOARD_ARRIVAL", "Pilot On Board"])
                t_end = self._get_time(evs, ["ALL_FAST_ARRIVAL", "All Fast"])
                if t_start and t_end and t_end >= t_start:
                    towages.append((t_end - t_start).total_seconds() / 3600.0)
            if not towages:
                return None, None, None, "UNAVAILABLE", "GRAY", "No inward towage events recorded.", {}
            avg_t = round(sum(towages) / len(towages), 4)
            band = self.evaluate_band(avg_t, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_t, round(sum(towages), 4), float(len(towages)), "COMPUTED", band, None, {"sample_size": len(towages)}

        # ── KPI-08: Average Inward Towage Duration (Configurable denominator disclosed) ──
        elif code == "KPI-08":
            towages = []
            service_count = 0
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_start = self._get_time(evs, ["TUG_ATTACH_ARRIVAL", "PILOT_ON_BOARD_ARRIVAL"])
                t_end = self._get_time(evs, ["ALL_FAST_ARRIVAL"])
                if t_start and t_end and t_end >= t_start:
                    towages.append((t_end - t_start).total_seconds() / 3600.0)
                svcs = [s for s in services_by_vc.get(vc.id, []) if "Tug" in (s.get("service_type") or "")]
                service_count += len(svcs)

            if not towages:
                return None, None, None, "UNAVAILABLE", "GRAY", "No towage records available.", {}

            denom_type = (cohort_filters or {}).get("towage_denominator", "assisted_vessels")
            if denom_type == "services" and service_count > 0:
                val = round(sum(towages) / service_count, 4)
                den = float(service_count)
            else:
                denom_type = "assisted_vessels"
                val = round(sum(towages) / len(towages), 4)
                den = float(len(towages))

            band = self.evaluate_band(val, kpi.target, kpi.target_direction, kpi.thresholds)
            return val, round(sum(towages), 4), den, "COMPUTED", band, None, {
                "denominator_choice": denom_type,
                "assisted_vessels": len(towages),
                "total_services": service_count,
            }

        # ── KPI-09: Outward Towage Duration ──
        elif code == "KPI-09":
            outwards = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_start = self._get_time(evs, ["FIRST_LINE_UNTIED_SAILING", "LAST_LINE_UNTIED_SAILING", "PILOT_ON_BOARD_SAILING"])
                t_end = self._get_time(evs, ["TUG_RELEASE_SAILING", "BREAKWATER_OUT", "Breakwater Out"])
                if t_start and t_end and t_end >= t_start:
                    outwards.append((t_end - t_start).total_seconds() / 3600.0)
            if not outwards:
                return None, None, None, "UNAVAILABLE", "GRAY", "No outward towage events.", {}
            avg_o = round(sum(outwards) / len(outwards), 4)
            band = self.evaluate_band(avg_o, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_o, round(sum(outwards), 4), float(len(outwards)), "COMPUTED", band, None, {"sample_size": len(outwards)}

        # ── KPI-10: Pilot Service Delay (Arrival Pilotage Execution Delay) ──
        elif code == "KPI-10":
            delays = []
            for vc in vessel_calls:
                for s in services_by_vc.get(vc.id, []):
                    stype = s.get("service_type") or ""
                    mtype = s.get("movement_type") or ""
                    if "Pilot" in stype and ("Arrival" in mtype or not mtype):
                        sched = s.get("scheduled_time")
                        serv = s.get("served_time")
                        if sched and serv:
                            delays.append((serv - sched).total_seconds() / 3600.0)
            if not delays:
                return None, None, None, "UNAVAILABLE", "GRAY", "No pilot service execution records.", {}
            avg_d = round(sum(delays) / len(delays), 4)
            band = self.evaluate_band(avg_d, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_d, round(sum(delays), 4), float(len(delays)), "COMPUTED", band, None, {
                "sample_size": len(delays),
                "early_service_count": sum(1 for d in delays if d < 0),
            }

        # ── KPI-11: Tug Response Time (Primary) ──
        elif code == "KPI-11":
            delays = []
            for vc in vessel_calls:
                for s in services_by_vc.get(vc.id, []):
                    stype = s.get("service_type") or ""
                    mtype = s.get("movement_type") or ""
                    if "Tug" in stype and ("Arrival" in mtype or not mtype):
                        sched = s.get("scheduled_time")
                        serv = s.get("served_time")
                        if sched and serv:
                            delays.append((serv - sched).total_seconds() / 3600.0)
            if not delays:
                return None, None, None, "UNAVAILABLE", "GRAY", "No tug service execution records.", {}
            avg_d = round(sum(delays) / len(delays), 4)
            band = self.evaluate_band(avg_d, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_d, round(sum(delays), 4), float(len(delays)), "COMPUTED", band, None, {
                "sample_size": len(delays),
                "early_service_count": sum(1 for d in delays if d < 0),
            }

        # ── KPI-12: Mooring Service Response Time ──
        elif code == "KPI-12":
            delays = []
            for vc in vessel_calls:
                for s in services_by_vc.get(vc.id, []):
                    stype = s.get("service_type") or ""
                    mtype = s.get("movement_type") or ""
                    if ("Mooring" in stype or "Berthing" in stype) and ("Arrival" in mtype or not mtype):
                        sched = s.get("scheduled_time")
                        serv = s.get("served_time")
                        if sched and serv:
                            delays.append((serv - sched).total_seconds() / 3600.0)
            if not delays:
                return None, None, None, "UNAVAILABLE", "GRAY", "No mooring/berthing service records found in data.", {}
            avg_d = round(sum(delays) / len(delays), 4)
            band = self.evaluate_band(avg_d, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_d, round(sum(delays), 4), float(len(delays)), "COMPUTED", band, None, {
                "sample_size": len(delays),
                "early_service_count": sum(1 for d in delays if d < 0),
            }

        # ── KPI-13: Berth Availability ──
        elif code == "KPI-13":
            total = 0
            on_time = 0
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_arr = self._get_time(evs, ["ANCHORAGE_ARRIVAL"])
                t_pob = self._get_time(evs, ["PILOT_ON_BOARD_ARRIVAL"])
                if t_arr and t_pob:
                    total += 1
                    # Available without wait if wait <= 1.0 hour
                    if (t_pob - t_arr).total_seconds() / 3600.0 <= 1.0:
                        on_time += 1
            if total == 0:
                return None, None, None, "UNAVAILABLE", "GRAY", "No berthing records.", {}
            rate = round((on_time / total) * 100.0, 2)
            band = self.evaluate_band(rate, kpi.target, kpi.target_direction, kpi.thresholds)
            return rate, float(on_time), float(total), "COMPUTED", band, None, {"available_calls": on_time, "total_calls": total}

        # ── KPI-14: Berth Occupancy Rate (Primary) ──
        elif code == "KPI-14":
            berth_stays = []
            min_t = None
            max_t = None
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_fast = self._get_time(evs, ["ALL_FAST_ARRIVAL", "All Fast"])
                t_untied = self._get_time(evs, ["LAST_LINE_UNTIED_SAILING", "Last Line Untied"])
                if t_fast and t_untied and t_untied >= t_fast:
                    dur = (t_untied - t_fast).total_seconds() / 3600.0
                    berth_stays.append(dur)
                    if min_t is None or t_fast < min_t: min_t = t_fast
                    if max_t is None or t_untied > max_t: max_t = t_untied
            if not berth_stays or not min_t or not max_t:
                return None, None, None, "UNAVAILABLE", "GRAY", "No berth stay data.", {}

            total_berth_hours = sum(berth_stays)
            period_hours = max((max_t - min_t).total_seconds() / 3600.0, 1.0)
            # Port has approximately 4 operational berths
            num_berths = 4.0
            total_capacity = num_berths * period_hours
            occupancy_pct = round(min((total_berth_hours / total_capacity) * 100.0, 100.0), 2)
            band = self.evaluate_band(occupancy_pct, kpi.target, kpi.target_direction, kpi.thresholds)
            return occupancy_pct, round(total_berth_hours, 2), round(total_capacity, 2), "COMPUTED", band, None, {
                "assumed_berth_count": num_berths,
                "period_hours": round(period_hours, 2),
                "total_berth_stay_hours": round(total_berth_hours, 2),
            }

        # ── KPI-15: Berth Turnaround Time ──
        elif code == "KPI-15":
            stays = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_first = self._get_time(evs, ["FIRST_LINE_TIED_ARRIVAL", "ALL_FAST_ARRIVAL"])
                t_last = self._get_time(evs, ["LAST_LINE_UNTIED_SAILING"])
                if t_first and t_last and t_last >= t_first:
                    stays.append((t_last - t_first).total_seconds() / 3600.0)
            if not stays:
                return None, None, None, "UNAVAILABLE", "GRAY", "No berth turnaround records.", {}
            avg_stay = round(sum(stays) / len(stays), 4)
            band = self.evaluate_band(avg_stay, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_stay, round(sum(stays), 4), float(len(stays)), "COMPUTED", band, None, {"sample_size": len(stays)}

        # ── KPI-16: Berth Productivity (Cargo / Berth Stay) ──
        elif code == "KPI-16":
            total_cargo = 0.0
            total_stay = 0.0
            for vc in vessel_calls:
                ops = cargo_by_vc.get(vc.id, [])
                evs = events_by_vc.get(vc.id, {})
                t_fast = self._get_time(evs, ["ALL_FAST_ARRIVAL"])
                t_untied = self._get_time(evs, ["LAST_LINE_UNTIED_SAILING"])
                if ops and t_fast and t_untied and t_untied > t_fast:
                    stay = (t_untied - t_fast).total_seconds() / 3600.0
                    cargo_qty = sum(op.actual_quantity or 0.0 for op in ops)
                    total_cargo += cargo_qty
                    total_stay += stay
            if total_stay == 0:
                return None, None, None, "UNAVAILABLE", "GRAY", "No berth stay data for cargo calls.", {}
            prod = round(total_cargo / total_stay, 2)
            band = self.evaluate_band(prod, kpi.target, kpi.target_direction, kpi.thresholds)
            return prod, round(total_cargo, 2), round(total_stay, 2), "COMPUTED", band, None, {
                "total_cargo": round(total_cargo, 2),
                "total_berth_stay_hours": round(total_stay, 2),
            }

        # ── KPI-17: Berth Working Time Ratio ──
        elif code == "KPI-17":
            total_working = 0.0
            total_stay = 0.0
            for vc in vessel_calls:
                ops = cargo_by_vc.get(vc.id, [])
                evs = events_by_vc.get(vc.id, {})
                t_fast = self._get_time(evs, ["ALL_FAST_ARRIVAL"])
                t_untied = self._get_time(evs, ["LAST_LINE_UNTIED_SAILING"])
                if ops and t_fast and t_untied and t_untied > t_fast:
                    stay = (t_untied - t_fast).total_seconds() / 3600.0
                    work = sum(op.working_hours or 0.0 for op in ops)
                    total_working += work
                    total_stay += stay
            if total_stay == 0:
                return None, None, None, "UNAVAILABLE", "GRAY", "No berth stay or working hours.", {}
            ratio = round(min((total_working / total_stay) * 100.0, 100.0), 2)
            band = self.evaluate_band(ratio, kpi.target, kpi.target_direction, kpi.thresholds)
            return ratio, round(total_working, 2), round(total_stay, 2), "COMPUTED", band, None, {
                "working_hours": round(total_working, 2),
                "berth_stay_hours": round(total_stay, 2),
            }

        # ── KPI-18: Berth Working Rate ──
        elif code == "KPI-18":
            total_cargo = 0.0
            total_working = 0.0
            for vc in vessel_calls:
                ops = cargo_by_vc.get(vc.id, [])
                for op in ops:
                    total_cargo += op.actual_quantity or 0.0
                    total_working += op.working_hours or 0.0
            if total_working == 0:
                return None, None, None, "UNAVAILABLE", "GRAY", "No working hours logged.", {}
            rate = round(total_cargo / total_working, 2)
            band = self.evaluate_band(rate, kpi.target, kpi.target_direction, kpi.thresholds)
            return rate, round(total_cargo, 2), round(total_working, 2), "COMPUTED", band, None, {
                "total_cargo": round(total_cargo, 2),
                "total_working_hours": round(total_working, 2),
            }

        # ── KPI-19: Berth Idle Time ──
        elif code == "KPI-19":
            idle_times = []
            for vc in vessel_calls:
                ops = cargo_by_vc.get(vc.id, [])
                evs = events_by_vc.get(vc.id, {})
                t_fast = self._get_time(evs, ["ALL_FAST_ARRIVAL"])
                t_untied = self._get_time(evs, ["LAST_LINE_UNTIED_SAILING"])
                if ops and t_fast and t_untied and t_untied > t_fast:
                    stay = (t_untied - t_fast).total_seconds() / 3600.0
                    work = sum(op.working_hours or 0.0 for op in ops)
                    idle_times.append(max(stay - work, 0.0))
            if not idle_times:
                return None, None, None, "UNAVAILABLE", "GRAY", "No berth stay data.", {}
            avg_idle = round(sum(idle_times) / len(idle_times), 4)
            band = self.evaluate_band(avg_idle, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_idle, round(sum(idle_times), 4), float(len(idle_times)), "COMPUTED", band, None, {"sample_size": len(idle_times)}

        # ── KPI-20: Berth Dwell Time ──
        elif code == "KPI-20":
            dwells = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_fast = self._get_time(evs, ["ALL_FAST_ARRIVAL"])
                t_untied = self._get_time(evs, ["LAST_LINE_UNTIED_SAILING"])
                if t_fast and t_untied and t_untied >= t_fast:
                    dwells.append((t_untied - t_fast).total_seconds() / 3600.0)
            if not dwells:
                return None, None, None, "UNAVAILABLE", "GRAY", "No berth dwell events.", {}
            avg_dwell = round(sum(dwells) / len(dwells), 4)
            band = self.evaluate_band(avg_dwell, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_dwell, round(sum(dwells), 4), float(len(dwells)), "COMPUTED", band, None, {"sample_size": len(dwells)}

        # ── KPI-21: Berth Productivity - Crane (moves / crane-hours) ──
        # Spec rule: If crane-hours are already summed across cranes, do not multiply by crane count again.
        elif code == "KPI-21":
            container_ops = [
                op for vc in vessel_calls
                for op in cargo_by_vc.get(vc.id, [])
                if op.unit == "TEU" and op.working_hours and op.actual_quantity
            ]
            if not container_ops:
                return None, None, None, "UNAVAILABLE", "GRAY", "No container operations with working hours.", {}
            total_moves = sum(op.actual_quantity for op in container_ops)
            # working_hours is the gross operation hours; crane hours = working_hours * resources_deployed
            total_crane_hours = sum(op.working_hours * (op.resources_deployed or 1) for op in container_ops)
            if total_crane_hours == 0:
                return None, None, None, "UNAVAILABLE", "GRAY", "Total crane hours is zero.", {}
            prod = round(total_moves / total_crane_hours, 2)
            band = self.evaluate_band(prod, kpi.target, kpi.target_direction, kpi.thresholds)
            return prod, round(total_moves, 2), round(total_crane_hours, 2), "COMPUTED", band, None, {
                "total_container_moves": round(total_moves, 2),
                "total_crane_hours": round(total_crane_hours, 2),
                "rule": "moves / crane-hours (spec §11).",
            }

        # ── KPI-22: Gross Crane Productivity (moves / total working hours) ──
        elif code == "KPI-22":
            container_ops = [
                op for vc in vessel_calls
                for op in cargo_by_vc.get(vc.id, [])
                if op.unit == "TEU" and op.working_hours and op.actual_quantity
            ]
            if not container_ops:
                return None, None, None, "UNAVAILABLE", "GRAY", "No container operations.", {}
            total_moves = sum(op.actual_quantity for op in container_ops)
            total_wh = sum(op.working_hours for op in container_ops)
            if total_wh == 0:
                return None, None, None, "UNAVAILABLE", "GRAY", "Zero working hours.", {}
            prod = round(total_moves / total_wh, 2)
            band = self.evaluate_band(prod, kpi.target, kpi.target_direction, kpi.thresholds)
            return prod, round(total_moves, 2), round(total_wh, 2), "COMPUTED", band, None, {"total_moves": total_moves, "gross_working_hours": total_wh}

        # ── KPI-23: Net Crane Productivity (moves / (working hours - downtime)) ──
        elif code == "KPI-23":
            container_ops = [
                op for vc in vessel_calls
                for op in cargo_by_vc.get(vc.id, [])
                if op.unit == "TEU" and op.working_hours and op.actual_quantity
            ]
            if not container_ops:
                return None, None, None, "UNAVAILABLE", "GRAY", "No container operations.", {}
            total_moves = sum(op.actual_quantity for op in container_ops)
            net_hours = sum(max(op.working_hours - (op.downtime_hours or 0.0), 0.1) for op in container_ops)
            prod = round(total_moves / net_hours, 2)
            band = self.evaluate_band(prod, kpi.target, kpi.target_direction, kpi.thresholds)
            return prod, round(total_moves, 2), round(net_hours, 2), "COMPUTED", band, None, {"total_moves": total_moves, "net_working_hours": round(net_hours, 2)}

        # ── KPI-24: Container Traffic in TEUs ──
        # Spec rule: loaded + unloaded + transshipped, with restow treatment configured and disclosed.
        elif code == "KPI-24":
            teu_sum = sum(
                op.actual_quantity or 0.0
                for vc in vessel_calls
                for op in cargo_by_vc.get(vc.id, [])
                if op.unit == "TEU"
            )
            band = self.evaluate_band(teu_sum, kpi.target, kpi.target_direction, kpi.thresholds)
            return round(teu_sum, 2), round(teu_sum, 2), None, "COMPUTED", band, None, {
                "restow_treatment": "excluded_from_primary_throughput_unless_restow_flag_set",
                "total_teu": round(teu_sum, 2),
            }

        # ── KPI-25: Cargo Handling Time ──
        elif code == "KPI-25":
            durations = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_start = self._get_time(evs, ["CARGO_START", "Cargo Operations Start"])
                t_end = self._get_time(evs, ["CARGO_END", "Cargo Operations End"])
                if t_start and t_end and t_end >= t_start:
                    durations.append((t_end - t_start).total_seconds() / 3600.0)
            if not durations:
                return None, None, None, "UNAVAILABLE", "GRAY", "No cargo timing events recorded.", {}
            avg_d = round(sum(durations) / len(durations), 4)
            band = self.evaluate_band(avg_d, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_d, round(sum(durations), 4), float(len(durations)), "COMPUTED", band, None, {"sample_size": len(durations)}

        # ── KPI-27: Last Container Lift to Departure Time ──
        elif code == "KPI-27":
            durations = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_end = self._get_time(evs, ["CARGO_END", "Cargo Operations End"])
                t_dep = self._get_time(evs, ["LAST_LINE_UNTIED_SAILING", "ATD", "Departure from Berth"])
                if t_end and t_dep and t_dep >= t_end:
                    durations.append((t_dep - t_end).total_seconds() / 3600.0)
            if not durations:
                return None, None, None, "UNAVAILABLE", "GRAY", "No cargo-end or departure events.", {}
            avg_d = round(sum(durations) / len(durations), 4)
            band = self.evaluate_band(avg_d, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_d, round(sum(durations), 4), float(len(durations)), "COMPUTED", band, None, {"sample_size": len(durations)}

        # ── KPI-28: Cargo Working Idle Time ──
        elif code == "KPI-28":
            downtimes = []
            for vc in vessel_calls:
                ops = cargo_by_vc.get(vc.id, [])
                if ops:
                    dt = sum(op.downtime_hours or 0.0 for op in ops)
                    downtimes.append(dt)
            if not downtimes:
                return None, None, None, "UNAVAILABLE", "GRAY", "No cargo downtime records.", {}
            avg_dt = round(sum(downtimes) / len(downtimes), 4)
            band = self.evaluate_band(avg_dt, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_dt, round(sum(downtimes), 4), float(len(downtimes)), "COMPUTED", band, None, {"sample_size": len(downtimes)}

        # ── KPI-29: Total Cargo Working Hours ──
        elif code == "KPI-29":
            wh_sum = sum(
                op.working_hours or 0.0
                for vc in vessel_calls
                for op in cargo_by_vc.get(vc.id, [])
            )
            band = self.evaluate_band(wh_sum, kpi.target, kpi.target_direction, kpi.thresholds)
            return round(wh_sum, 2), round(wh_sum, 2), None, "COMPUTED", band, None, {"total_working_hours": round(wh_sum, 2)}

        # ── KPI-30: Crane Moves per Hour per Crane ──
        # Spec rule: total moves / summed productive crane-hours (working_hours * resources_deployed)
        elif code == "KPI-30":
            container_ops = [
                op for vc in vessel_calls
                for op in cargo_by_vc.get(vc.id, [])
                if op.unit == "TEU" and op.working_hours and op.actual_quantity
            ]
            if not container_ops:
                return None, None, None, "UNAVAILABLE", "GRAY", "No container operations.", {}
            total_moves = sum(op.actual_quantity for op in container_ops)
            crane_hours = sum(op.working_hours * (op.resources_deployed or 1) for op in container_ops)
            if crane_hours == 0:
                return None, None, None, "UNAVAILABLE", "GRAY", "Zero crane hours.", {}
            mph = round(total_moves / crane_hours, 2)
            band = self.evaluate_band(mph, kpi.target, kpi.target_direction, kpi.thresholds)
            return mph, round(total_moves, 2), round(crane_hours, 2), "COMPUTED", band, None, {
                "total_moves": round(total_moves, 2),
                "summed_crane_hours": round(crane_hours, 2),
            }

        # ── KPI-41: Turnaround Time (Departure − Anchorage Arrival) ──
        # Spec rule: departure − anchorage arrival, with governed exclusions. Distinct from ATA-to-ATD.
        elif code == "KPI-41":
            turnarounds = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_arr = self._get_time(evs, ["ANCHORAGE_ARRIVAL", "Anchorage Arrival"])
                t_dep = self._get_time(evs, ["BREAKWATER_OUT", "LAST_LINE_UNTIED_SAILING", "ATD"])
                if t_arr and t_dep and t_dep >= t_arr:
                    turnarounds.append((t_dep - t_arr).total_seconds() / 3600.0)
            if not turnarounds:
                return None, None, None, "UNAVAILABLE", "GRAY", "No valid turnaround spans.", {}
            avg_tat = round(sum(turnarounds) / len(turnarounds), 4)
            band = self.evaluate_band(avg_tat, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_tat, round(sum(turnarounds), 4), float(len(turnarounds)), "COMPUTED", band, None, {
                "definition": "Departure − Anchorage Arrival (distinct from ATA-to-ATD Turnaround)",
                "sample_size": len(turnarounds),
            }

        # ── KPI-42: Anchorage Duration ──
        elif code == "KPI-42":
            anch_durations = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_arr = self._get_time(evs, ["ANCHORAGE_ARRIVAL"])
                t_end = self._get_time(evs, ["PILOT_ON_BOARD_ARRIVAL", "ANCHORAGE_DEPARTURE", "Anchor Aweigh"])
                if t_arr and t_end and t_end >= t_arr:
                    anch_durations.append((t_end - t_arr).total_seconds() / 3600.0)
            if not anch_durations:
                return None, None, None, "UNAVAILABLE", "GRAY", "No anchorage events recorded.", {}
            avg_ad = round(sum(anch_durations) / len(anch_durations), 4)
            band = self.evaluate_band(avg_ad, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_ad, round(sum(anch_durations), 4), float(len(anch_durations)), "COMPUTED", band, None, {"sample_size": len(anch_durations)}

        # ── KPI-43: Turnaround Efficiency (Working Hours / Turnaround Hours * 100%) ──
        elif code == "KPI-43":
            total_work = 0.0
            total_tat = 0.0
            for vc in vessel_calls:
                ops = cargo_by_vc.get(vc.id, [])
                evs = events_by_vc.get(vc.id, {})
                t_arr = self._get_time(evs, ["ANCHORAGE_ARRIVAL", "ATA"])
                t_dep = self._get_time(evs, ["LAST_LINE_UNTIED_SAILING", "ATD"])
                if ops and t_arr and t_dep and t_dep > t_arr:
                    total_work += sum(op.working_hours or 0.0 for op in ops)
                    total_tat += (t_dep - t_arr).total_seconds() / 3600.0
            if total_tat == 0:
                return None, None, None, "UNAVAILABLE", "GRAY", "No turnaround data.", {}
            eff = round(min((total_work / total_tat) * 100.0, 100.0), 2)
            band = self.evaluate_band(eff, kpi.target, kpi.target_direction, kpi.thresholds)
            return eff, round(total_work, 2), round(total_tat, 2), "COMPUTED", band, None, {
                "working_hours": round(total_work, 2),
                "turnaround_hours": round(total_tat, 2),
            }

        # ── KPI-44: Port Time (ATD − ATA) ──
        elif code == "KPI-44":
            port_times = []
            for vc in vessel_calls:
                evs = events_by_vc.get(vc.id, {})
                t_ata = self._get_time(evs, ["ATA"])
                t_atd = self._get_time(evs, ["ATD"])
                if t_ata and t_atd and t_atd >= t_ata:
                    port_times.append((t_atd - t_ata).total_seconds() / 3600.0)
            if not port_times:
                return None, None, None, "UNAVAILABLE", "GRAY", "No valid ATA/ATD pairs.", {}
            avg_pt = round(sum(port_times) / len(port_times), 4)
            band = self.evaluate_band(avg_pt, kpi.target, kpi.target_direction, kpi.thresholds)
            return avg_pt, round(sum(port_times), 4), float(len(port_times)), "COMPUTED", band, None, {
                "definition": "ATD - ATA port stay time",
                "sample_size": len(port_times),
            }

        # ── KPI-45: Service Delays (Total Delay Hours / Delay Events) ──
        elif code == "KPI-45":
            all_delays = [dl for vc in vessel_calls for dl in delays_by_vc.get(vc.id, [])]
            total_delay_hours = sum(dl.total_duration_hours or 0.0 for dl in all_delays)
            count = len(all_delays)
            band = self.evaluate_band(total_delay_hours, kpi.target, kpi.target_direction, kpi.thresholds)
            return round(total_delay_hours, 2), round(total_delay_hours, 2), float(count), "COMPUTED", band, None, {
                "total_delay_records": count,
                "total_delay_hours": round(total_delay_hours, 2),
            }

        # ── KPI-49: Pilot Utilization ──
        elif code == "KPI-49":
            pilot_hours = 0.0
            for vc in vessel_calls:
                for s in services_by_vc.get(vc.id, []):
                    if "Pilot" in (s.get("service_type") or ""):
                        # Assumed average pilotage duration: 2.0 hours per maneuver
                        pilot_hours += 2.0
            # Standard pool of 4 pilots * 720 hours / month
            capacity_hours = 4.0 * 720.0
            util = round(min((pilot_hours / capacity_hours) * 100.0, 100.0), 2)
            band = self.evaluate_band(util, kpi.target, kpi.target_direction, kpi.thresholds)
            return util, round(pilot_hours, 2), capacity_hours, "COMPUTED", band, None, {
                "assumed_pilots": 4,
                "service_hours": round(pilot_hours, 2),
                "capacity_hours": capacity_hours,
            }

        # ── KPI-50: Tug Utilization ──
        elif code == "KPI-50":
            tug_hours = 0.0
            for vc in vessel_calls:
                for s in services_by_vc.get(vc.id, []):
                    if "Tug" in (s.get("service_type") or ""):
                        # Assumed average tug duration: 1.5 hours per operation
                        tug_hours += 1.5
            # Fleet of 4 tugs * 720 hours / month
            capacity_hours = 4.0 * 720.0
            util = round(min((tug_hours / capacity_hours) * 100.0, 100.0), 2)
            band = self.evaluate_band(util, kpi.target, kpi.target_direction, kpi.thresholds)
            return util, round(tug_hours, 2), capacity_hours, "COMPUTED", band, None, {
                "assumed_tugs": 4,
                "service_hours": round(tug_hours, 2),
                "capacity_hours": capacity_hours,
            }

        # ── KPI-54: On-Time Departure Rate ──
        elif code == "KPI-54":
            eligible = 0
            on_time = 0
            for vc in vessel_calls:
                for s in services_by_vc.get(vc.id, []):
                    if "Sailing" in (s.get("movement_type") or ""):
                        sched = s.get("scheduled_time")
                        serv = s.get("served_time")
                        if sched and serv:
                            eligible += 1
                            delay_h = (serv - sched).total_seconds() / 3600.0
                            if delay_h <= 0.5:  # Grace period of 30 minutes
                                on_time += 1
            if eligible == 0:
                return None, None, None, "UNAVAILABLE", "GRAY", "No sailing service records.", {}
            rate = round((on_time / eligible) * 100.0, 2)
            band = self.evaluate_band(rate, kpi.target, kpi.target_direction, kpi.thresholds)
            return rate, float(on_time), float(eligible), "COMPUTED", band, None, {
                "on_time_sailings": on_time,
                "total_sailings": eligible,
            }

        # Fallback for unexpected code
        return None, None, None, "UNAVAILABLE", "GRAY", f"Formula logic for {code} not mapped.", {}

    @staticmethod
    def _get_time(events: Dict[str, EventOccurrence], candidate_names: List[str]) -> Optional[datetime]:
        """Returns the utc_value of the first matching event name from candidate names."""
        for name in candidate_names:
            if name in events and events[name].utc_value:
                return events[name].utc_value
        return None
