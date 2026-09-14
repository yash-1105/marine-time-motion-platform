"""
Canonical occurrence selection (phase-06-journey.md §2, spec §9).

When multiple source records observe the same logical event (e.g. two ATA readings), every
observation is retained. This module only decides which one *governs* downstream calculations,
using source priority, verification status and confidence, and records the decision with full
evidence. It never deletes a conflicting observation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.canonical import EventOccurrence, VesselCall
from apps.api.models.config import EventDefinition
from apps.api.models.journey import CanonicalObservation
from apps.api.models.quality import QualityIssue, QualityRule

from .template_loader import REPEATABLE_EVENTS

THRESHOLDS_PATH = "config/thresholds.yaml"


def _load_selection_config() -> Dict[str, Any]:
    try:
        with open(THRESHOLDS_PATH, "r") as f:
            data = yaml.safe_load(f) or {}
        return data.get("thresholds", {}).get("canonical_occurrence_selection", {})
    except Exception:
        return {}


class CanonicalOccurrenceSelector:
    def __init__(self, db: Session):
        self.db = db
        cfg = _load_selection_config()
        self.verification_priority: List[str] = cfg.get("verification_priority", ["Verified", "Conflicting"])
        self.source_priority: List[str] = cfg.get("source_priority", [])
        self.rule_version = "1.0"

    def _rank(self, occ: EventOccurrence) -> tuple:
        """Lower tuple sorts first (wins)."""
        verification_rank = (
            self.verification_priority.index(occ.verification_status)
            if occ.verification_status in self.verification_priority
            else len(self.verification_priority)
        )
        confidence_rank = -(occ.confidence or 0.0)
        source_rank = (
            self.source_priority.index(occ.source_system)
            if occ.source_system in self.source_priority
            else len(self.source_priority)
        )
        # Stable tiebreak: earlier ingested observation wins deterministically.
        created_rank = occ.created_at or datetime.min.replace(tzinfo=timezone.utc)
        return (verification_rank, confidence_rank, source_rank, created_rank)

    def _find_related_quality_issue(self, vessel_call_id, occurrence_ids: List[str]) -> Optional[str]:
        refs = {f"EventOccurrence:{oid}" for oid in occurrence_ids}
        issues = self.db.execute(
            select(QualityIssue, QualityRule)
            .join(QualityRule)
            .where(QualityIssue.vessel_call_id == vessel_call_id)
        ).all()
        for issue, rule in issues:
            if issue.record_reference in refs:
                return str(issue.id)
        return None

    def resolve_vessel_call(self, vc: VesselCall) -> List[CanonicalObservation]:
        """
        Groups this vessel call's event occurrences by event_definition_id. For any
        non-repeatable event with more than one live observation, resolves canonical selection.
        Returns the CanonicalObservation rows created/updated (conflicting groups only).
        """
        event_defs = {e.id: e.name for e in self.db.execute(select(EventDefinition)).scalars().all()}

        occurrences = self.db.execute(
            select(EventOccurrence).where(
                EventOccurrence.vessel_call_id == vc.id,
                EventOccurrence.is_superseded == False,  # noqa: E712
            )
        ).scalars().all()

        by_definition: Dict[Any, List[EventOccurrence]] = {}
        for occ in occurrences:
            by_definition.setdefault(occ.event_definition_id, []).append(occ)

        results = []
        for def_id, occs in by_definition.items():
            event_name = event_defs.get(def_id, "")
            if event_name in REPEATABLE_EVENTS:
                continue  # legitimate repeats (shifting) are not conflicts
            if len(occs) <= 1:
                continue

            ranked = sorted(occs, key=self._rank)
            selected = ranked[0]

            comparison = []
            for occ in occs:
                comparison.append(
                    {
                        "event_occurrence_id": str(occ.id),
                        "source_system": occ.source_system,
                        "verification_status": occ.verification_status,
                        "confidence": occ.confidence,
                        "utc_value": occ.utc_value.isoformat() if occ.utc_value else None,
                        "selected": occ.id == selected.id,
                    }
                )

            reasoning = {
                "method": "verification_status, then confidence, then source priority",
                "comparison": comparison,
                "winning_reason": self._explain(selected, occs),
            }

            candidate_ids = [str(o.id) for o in occs]
            existing = self.db.execute(
                select(CanonicalObservation).where(
                    CanonicalObservation.vessel_call_id == vc.id,
                    CanonicalObservation.event_definition_id == def_id,
                )
            ).scalar_one_or_none()

            quality_issue_id = self._find_related_quality_issue(vc.id, candidate_ids)

            if existing and existing.selection_method == "STEWARD_OVERRIDE":
                # A steward has already made a governed decision; do not silently override it.
                results.append(existing)
                continue

            if not existing:
                existing = CanonicalObservation(
                    vessel_call_id=vc.id,
                    event_definition_id=def_id,
                )
                self.db.add(existing)

            existing.candidate_event_occurrence_ids = candidate_ids
            existing.selected_event_occurrence_id = selected.id
            existing.conflict_detected = True
            existing.selection_method = "AUTOMATIC"
            existing.selection_reasoning = reasoning
            existing.quality_issue_id = quality_issue_id
            existing.decided_by = "system:canonical_selector"
            existing.decided_at = datetime.now(timezone.utc)
            existing.rule_version = self.rule_version
            self.db.flush()
            results.append(existing)

        return results

    def _explain(self, selected: EventOccurrence, all_occs: List[EventOccurrence]) -> str:
        others = [o for o in all_occs if o.id != selected.id]
        if not others:
            return "Only observation available."
        other = others[0]
        if selected.verification_status != other.verification_status:
            return (
                f"Selected because verification status '{selected.verification_status}' outranks "
                f"'{other.verification_status}'."
            )
        if (selected.confidence or 0) != (other.confidence or 0):
            return f"Selected because confidence {selected.confidence} exceeds {other.confidence}."
        return f"Selected because source '{selected.source_system}' has higher configured priority."

    def get_canonical_occurrence_id(self, vessel_call_id, event_definition_id) -> Optional[Any]:
        """Returns the governing EventOccurrence id for a logical event slot, if a
        canonical-selection decision was recorded for it."""
        row = self.db.execute(
            select(CanonicalObservation).where(
                CanonicalObservation.vessel_call_id == vessel_call_id,
                CanonicalObservation.event_definition_id == event_definition_id,
            )
        ).scalar_one_or_none()
        return row.selected_event_occurrence_id if row else None
