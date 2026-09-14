"""
Vessel journey reconstruction (phase-06-journey.md, spec §9).

For every vessel call: build the chronological event graph against the configured template,
reconstruct stages, preserve every observation, separate missing from inferred events, compute
stage durations and an active/wait/hold/delay/unclassified decomposition that sums to the total
without double-counting, name deviations, model handovers, and persist a versioned history.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.canonical import EventOccurrence, VesselCall
from apps.api.models.config import EventDefinition
from apps.api.models.journey import (
    Handover,
    JourneyInstance,
    ReconstructionHistory,
    StageOccurrence,
)

from .canonical_selector import CanonicalOccurrenceSelector
from .template_loader import REPEATABLE_EVENTS, ensure_template

TIME_CATEGORIES = ["ACTIVE_SERVICE", "PASSIVE_WAIT", "HOLD", "DELAY", "UNCLASSIFIED"]

# Main-path stages walked in sequence for decomposition purposes (excludes the repeatable
# shifting stage and the always-branch clearance stages, which are handled separately).
MAIN_PATH_MAX_SEQUENCE = 99


def _hours(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds() / 3600.0, 6)


class JourneyReconstructionEngine:
    def __init__(self, db: Session, tenant_id: Optional[str] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.template, self.stages = ensure_template(db)
        self.selector = CanonicalOccurrenceSelector(db)
        self.event_def_by_name = {
            e.name: e.id for e in self.db.execute(select(EventDefinition)).scalars().all()
        }
        self.event_def_by_id = {v: k for k, v in self.event_def_by_name.items()}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconstruct_all(self, triggered_by: str = "SYSTEM") -> Dict[str, Any]:
        query = select(VesselCall).where(VesselCall.is_merged == False)  # noqa: E712
        if self.tenant_id:
            query = query.where(VesselCall.tenant_id == self.tenant_id)
        vessel_calls = self.db.execute(query).scalars().all()

        reconstructed = 0
        failed = 0
        for vc in vessel_calls:
            try:
                self.reconstruct_vessel_call(vc, triggered_by=triggered_by)
                reconstructed += 1
            except Exception as exc:  # pragma: no cover - defensive
                failed += 1
                print(f"Journey reconstruction failed for {vc.vcn}: {exc}")
                import traceback

                traceback.print_exc()
        self.db.commit()
        return {"total": len(vessel_calls), "reconstructed": reconstructed, "failed": failed}

    def reconstruct_vessel_call(self, vc: VesselCall, triggered_by: str = "SYSTEM") -> JourneyInstance:
        # 1. Canonical occurrence selection for conflicting single-occurrence events.
        self.selector.resolve_vessel_call(vc)

        # 2. Build the resolved event-instant map (name -> live canonical EventOccurrence).
        instants, repeatable = self._build_event_instant_map(vc)

        # 3. Get or create the journey instance for this vessel call.
        instance = self.db.execute(
            select(JourneyInstance).where(JourneyInstance.vessel_call_id == vc.id)
        ).scalar_one_or_none()
        if not instance:
            instance = JourneyInstance(
                vessel_call_id=vc.id,
                template_id=self.template.id,
                status="PENDING",
                reconstruction_version=1,
            )
            self.db.add(instance)
            self.db.flush()
        else:
            instance.reconstruction_version = (instance.reconstruction_version or 1) + 1
            # Clear prior stage occurrences / handovers for a clean re-run (history is preserved
            # separately in reconstruction_history, so nothing is lost).
            prior_occs = self.db.execute(
                select(StageOccurrence).where(StageOccurrence.journey_instance_id == instance.id)
            ).scalars().all()
            prior_ids = [occ.id for occ in prior_occs]
            if prior_ids:
                for ho in self.db.execute(
                    select(Handover).where(
                        Handover.from_stage_occurrence_id.in_(prior_ids)
                        | Handover.to_stage_occurrence_id.in_(prior_ids)
                    )
                ).scalars().all():
                    self.db.delete(ho)
                self.db.flush()
            for occ in prior_occs:
                self.db.delete(occ)
            self.db.flush()

        instance.rule_version = self.template.rule_version

        # 4. Walk the main-path stages, building non-overlapping StageOccurrence rows.
        main_stages = [s for s in self.stages if s["sequence_index"] <= MAIN_PATH_MAX_SEQUENCE and not s["is_repeatable"]]
        branch_stages = [s for s in self.stages if s["sequence_index"] > MAIN_PATH_MAX_SEQUENCE]
        shift_stage_defs = [s for s in self.stages if s["is_repeatable"]]

        stage_occurrences: List[StageOccurrence] = []
        primary_intervals = []  # (stage_row, category, start, end, hours) for main-path decomposition

        for sdef in main_stages:
            row, interval = self._build_stage_occurrence(instance, sdef, instants, sequence_index=sdef["sequence_index"])
            stage_occurrences.append(row)
            if interval:
                primary_intervals.append(interval)

        for sdef in branch_stages:
            row, _ = self._build_stage_occurrence(instance, sdef, instants, sequence_index=sdef["sequence_index"])
            stage_occurrences.append(row)

        shift_rows = self._build_shift_occurrences(instance, shift_stage_defs, repeatable)
        stage_occurrences.extend(shift_rows)

        self.db.add_all(stage_occurrences)
        self.db.flush()

        # 5. Time decomposition: sum main-path buckets, then carve out shifting overlap so the
        #    total never double-counts (spec §9: "components sum to total without double-counting").
        decomposition = self._compute_decomposition(primary_intervals, shift_rows)

        # 6. Deviation report: sequence violations + missing stages on the main path.
        deviations = self._build_deviation_report(stage_occurrences)

        # 7. Coverage summary.
        available = sum(1 for s in stage_occurrences if s.availability == "AVAILABLE")
        missing = sum(1 for s in stage_occurrences if s.is_missing)
        inferred = sum(1 for s in stage_occurrences if s.is_inferred)
        coverage = {
            "stages_total": len(stage_occurrences),
            "stages_available": available,
            "stages_missing": missing,
            "stages_inferred": inferred,
            "shifting_occurrences": len(shift_rows),
        }

        instance.coverage_summary = coverage
        instance.time_decomposition = decomposition
        instance.deviation_report = deviations
        instance.status = "RECONSTRUCTED" if available > 0 else "FAILED"
        instance.computed_at = datetime.now(timezone.utc)
        self.db.flush()

        # 8. Handovers between consecutive main-path stages.
        self._build_handovers(instance, [row for row in stage_occurrences if row.sequence_index <= MAIN_PATH_MAX_SEQUENCE and row.shift_occurrence_index == 0])

        # 9. Versioned reconstruction history (never overwritten; every run appends).
        snapshot = self._snapshot(instance, stage_occurrences)
        history = ReconstructionHistory(
            journey_instance_id=instance.id,
            vessel_call_id=vc.id,
            run_version=instance.reconstruction_version,
            rule_version=self.template.rule_version,
            triggered_by=triggered_by,
            snapshot=snapshot,
        )
        self.db.add(history)
        self.db.flush()

        return instance

    # ------------------------------------------------------------------
    # Event resolution
    # ------------------------------------------------------------------

    def _build_event_instant_map(self, vc: VesselCall):
        occurrences = self.db.execute(
            select(EventOccurrence).where(
                EventOccurrence.vessel_call_id == vc.id,
                EventOccurrence.is_superseded == False,  # noqa: E712
                EventOccurrence.is_quarantined == False,  # noqa: E712
            )
        ).scalars().all()

        by_def: Dict[Any, List[EventOccurrence]] = {}
        for occ in occurrences:
            by_def.setdefault(occ.event_definition_id, []).append(occ)

        instants: Dict[str, Optional[EventOccurrence]] = {}
        repeatable: Dict[str, List[EventOccurrence]] = {}

        for def_id, occs in by_def.items():
            name = self.event_def_by_id.get(def_id)
            if not name:
                continue
            if name in REPEATABLE_EVENTS:
                repeatable[name] = sorted(occs, key=lambda o: o.utc_value or datetime.min.replace(tzinfo=timezone.utc))
                continue
            if len(occs) == 1:
                instants[name] = occs[0]
            else:
                canonical_id = self.selector.get_canonical_occurrence_id(vc.id, def_id)
                selected = next((o for o in occs if o.id == canonical_id), occs[0])
                instants[name] = selected

        return instants, repeatable

    # ------------------------------------------------------------------
    # Stage construction
    # ------------------------------------------------------------------

    def _build_stage_occurrence(self, instance: JourneyInstance, sdef: Dict[str, Any], instants: Dict[str, Optional[EventOccurrence]], sequence_index: int):
        start_occ = instants.get(sdef["start_event"])
        end_occ = instants.get(sdef["end_event"])

        row = StageOccurrence(
            journey_instance_id=instance.id,
            stage_id=sdef["id"],
            stage_name=sdef["name"],
            sequence_index=sequence_index,
            shift_occurrence_index=0,
            time_category=sdef["time_category"],
        )

        if start_occ is None or end_occ is None:
            row.availability = "UNAVAILABLE"
            row.is_missing = True
            row.status = "MISSING"
            missing_side = sdef["start_event"] if start_occ is None else sdef["end_event"]
            row.inference_reason = f"No canonical observation recorded for '{missing_side}'."
            return row, None

        row.start_event_occurrence_id = start_occ.id
        row.end_event_occurrence_id = end_occ.id
        row.start_time = start_occ.utc_value
        row.end_time = end_occ.utc_value
        row.duration_hours = _hours(start_occ.utc_value, end_occ.utc_value)
        row.availability = "AVAILABLE"
        row.status = "AVAILABLE"

        if row.duration_hours is not None and row.duration_hours < 0:
            row.deviation_type = "SEQUENCE_VIOLATION"
            row.deviation_detail = {
                "description": (
                    f"'{sdef['end_event']}' occurred before '{sdef['start_event']}': "
                    f"duration preserved as negative, not corrected."
                ),
                "duration_hours": row.duration_hours,
            }
            row.status = "DEVIATED"

        interval = (row, sdef["time_category"], start_occ.utc_value, end_occ.utc_value, row.duration_hours)
        return row, interval

    def _build_shift_occurrences(self, instance: JourneyInstance, shift_stage_defs: List[Dict[str, Any]], repeatable: Dict[str, List[EventOccurrence]]):
        rows: List[StageOccurrence] = []
        if not shift_stage_defs:
            return rows
        sdef = shift_stage_defs[0]  # single "Optional Shifting" stage definition
        starts = repeatable.get(sdef["start_event"], [])
        ends = repeatable.get(sdef["end_event"], [])

        pair_count = max(len(starts), len(ends))
        for i in range(pair_count):
            start_occ = starts[i] if i < len(starts) else None
            end_occ = ends[i] if i < len(ends) else None
            row = StageOccurrence(
                journey_instance_id=instance.id,
                stage_id=sdef["id"],
                stage_name=sdef["name"],
                sequence_index=sdef["sequence_index"],
                shift_occurrence_index=i + 1,
                time_category=sdef["time_category"],
            )
            if start_occ is None or end_occ is None:
                row.availability = "UNAVAILABLE"
                row.is_missing = True
                row.status = "MISSING"
                row.inference_reason = "Shift start/end event incomplete for this occurrence."
            else:
                row.start_event_occurrence_id = start_occ.id
                row.end_event_occurrence_id = end_occ.id
                row.start_time = start_occ.utc_value
                row.end_time = end_occ.utc_value
                row.duration_hours = _hours(start_occ.utc_value, end_occ.utc_value)
                row.availability = "AVAILABLE"
                row.status = "AVAILABLE"
            rows.append(row)
        return rows

    # ------------------------------------------------------------------
    # Decomposition, deviations, handovers, history
    # ------------------------------------------------------------------

    def _compute_decomposition(self, primary_intervals, shift_rows: List[StageOccurrence]) -> Dict[str, Any]:
        buckets = {cat: 0.0 for cat in TIME_CATEGORIES}
        available_any = False

        for row, category, start, end, hours in primary_intervals:
            if hours is None:
                continue
            available_any = True
            buckets[category] = buckets.get(category, 0.0) + hours

        delay_hours_from_shifting = 0.0
        for shift in shift_rows:
            if shift.availability != "AVAILABLE" or shift.duration_hours is None:
                continue
            overlap_row = self._find_overlapping_interval(primary_intervals, shift.start_time, shift.end_time)
            if overlap_row is not None:
                _, category, _, _, _ = overlap_row
                carve = min(shift.duration_hours, buckets.get(category, 0.0))
                buckets[category] = buckets.get(category, 0.0) - carve
                delay_hours_from_shifting += carve
            else:
                # Cannot determine which stage the shift interrupted; still surface it under
                # DELAY without touching other buckets (never fabricate a subtraction we can't justify).
                delay_hours_from_shifting += shift.duration_hours

        buckets["DELAY"] = round(buckets.get("DELAY", 0.0) + delay_hours_from_shifting, 6)
        for cat in TIME_CATEGORIES:
            buckets[cat] = round(buckets.get(cat, 0.0), 6)

        total = round(sum(buckets.values()), 6)
        return {
            **buckets,
            "total_hours": total if available_any else None,
            "status": "AVAILABLE" if available_any else "UNAVAILABLE",
        }

    @staticmethod
    def _find_overlapping_interval(primary_intervals, start: Optional[datetime], end: Optional[datetime]):
        if start is None or end is None:
            return None
        for interval in primary_intervals:
            _, _, istart, iend, _ = interval
            if istart is None or iend is None:
                continue
            if istart <= start and end <= iend:
                return interval
        return None

    @staticmethod
    def _build_deviation_report(stage_occurrences: List[StageOccurrence]) -> List[Dict[str, Any]]:
        deviations = []
        for row in stage_occurrences:
            if row.deviation_type:
                deviations.append(
                    {
                        "stage": row.stage_name,
                        "type": row.deviation_type,
                        "detail": row.deviation_detail,
                    }
                )
        return deviations

    def _build_handovers(self, instance: JourneyInstance, ordered_main_rows: List[StageOccurrence]):
        ordered_main_rows = sorted(ordered_main_rows, key=lambda r: r.sequence_index)
        stage_by_name = {s["name"]: s for s in self.stages}

        for i in range(len(ordered_main_rows) - 1):
            current = ordered_main_rows[i]
            nxt = ordered_main_rows[i + 1]
            current_def = stage_by_name.get(current.stage_name, {})
            next_def = stage_by_name.get(nxt.stage_name, {})

            handover = Handover(
                from_stage_occurrence_id=current.id,
                to_stage_occurrence_id=nxt.id,
                from_actor=current_def.get("actor_to"),
                to_actor=next_def.get("actor_from"),
            )
            if current.availability == "AVAILABLE" and nxt.availability == "AVAILABLE":
                handover.status = "AVAILABLE"
                handover.handover_time = current.end_time
                handover.wait_duration_hours = _hours(current.end_time, nxt.start_time)
            else:
                handover.status = "UNAVAILABLE"
            self.db.add(handover)
        self.db.flush()

    @staticmethod
    def _snapshot(instance: JourneyInstance, stage_occurrences: List[StageOccurrence]) -> Dict[str, Any]:
        return {
            "run_version": instance.reconstruction_version,
            "status": instance.status,
            "coverage_summary": instance.coverage_summary,
            "time_decomposition": instance.time_decomposition,
            "deviation_report": instance.deviation_report,
            "stages": [
                {
                    "stage_name": s.stage_name,
                    "shift_occurrence_index": s.shift_occurrence_index,
                    "availability": s.availability,
                    "start_time": s.start_time.isoformat() if s.start_time else None,
                    "end_time": s.end_time.isoformat() if s.end_time else None,
                    "duration_hours": s.duration_hours,
                    "time_category": s.time_category,
                    "is_missing": s.is_missing,
                    "is_inferred": s.is_inferred,
                    "deviation_type": s.deviation_type,
                }
                for s in stage_occurrences
            ],
        }
