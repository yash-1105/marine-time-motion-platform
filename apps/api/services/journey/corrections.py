"""
Steward corrections (phase-06-journey.md §3).

A correction never overwrites raw and never mutates the prior canonical value. It creates a new
canonical EventOccurrence (never touching raw.*), links it to a full-history ObservationCorrection
row, marks the prior canonical value superseded (not deleted), records the decision as a governed
canonical-observation override, and triggers recalculation of that vessel call's journey.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.canonical import EventOccurrence, VesselCall
from apps.api.models.journey import CanonicalObservation, JourneyInstance, ObservationCorrection
from apps.api.services.audit import log_audit_event

from .reconstructor import JourneyReconstructionEngine


class JourneyCorrectionService:
    @staticmethod
    def create_correction(
        db: Session,
        vessel_call_id: str,
        event_definition_id: str,
        new_utc_value: datetime,
        reason: str,
        actor: str,
        prior_event_occurrence_id: Optional[str] = None,
        approval_state: str = "APPROVED",
    ) -> ObservationCorrection:
        vc = db.execute(select(VesselCall).where(VesselCall.id == vessel_call_id)).scalar_one_or_none()
        if not vc:
            raise ValueError(f"VesselCall {vessel_call_id} not found")

        prior: Optional[EventOccurrence] = None
        if prior_event_occurrence_id:
            prior = db.execute(
                select(EventOccurrence).where(EventOccurrence.id == prior_event_occurrence_id)
            ).scalar_one_or_none()

        next_index = 1
        if prior:
            next_index = (prior.occurrence_index or 0) + 1000  # keep well clear of raw ingestion indices

        new_occ = EventOccurrence(
            vessel_call_id=vc.id,
            event_definition_id=event_definition_id,
            occurrence_index=next_index,
            movement_scope=prior.movement_scope if prior else "ARRIVAL",
            original_string=None,
            parsed_value=new_utc_value,
            source_timezone=prior.source_timezone if prior else "Africa/Johannesburg",
            utc_value=new_utc_value,
            capture_method="STEWARD_CORRECTION",
            confidence=1.0,
            verification_status="Verified",
            source_system="STEWARD_CORRECTION",
            source_record_id=None,
            ingestion_batch_id=None,
            correction_history=[
                {
                    "reason": reason,
                    "actor": actor,
                    "prior_event_occurrence_id": str(prior.id) if prior else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
            inference_status=None,
            human_review_state=approval_state,
            is_quarantined=False,
        )
        db.add(new_occ)
        db.flush()

        if approval_state == "APPROVED" and prior:
            prior.is_superseded = True
            prior.superseded_by_id = new_occ.id

        correction = ObservationCorrection(
            vessel_call_id=vc.id,
            event_definition_id=event_definition_id,
            prior_event_occurrence_id=prior.id if prior else None,
            new_event_occurrence_id=new_occ.id,
            reason=reason,
            actor=actor,
            approval_state=approval_state,
            approved_by=actor if approval_state == "APPROVED" else None,
            approved_at=datetime.now(timezone.utc) if approval_state == "APPROVED" else None,
            triggers_recalculation=True,
        )
        db.add(correction)
        db.flush()

        if approval_state == "APPROVED":
            JourneyCorrectionService._record_canonical_override(
                db, vc.id, event_definition_id, new_occ.id, prior.id if prior else None, correction, actor, reason
            )

        log_audit_event(
            db,
            action="JOURNEY_OBSERVATION_CORRECTION",
            actor_id=actor,
            resource_type="event_occurrence",
            resource_id=str(new_occ.id),
            details={
                "vessel_call_id": str(vc.id),
                "correction_id": str(correction.id),
                "prior_event_occurrence_id": str(prior.id) if prior else None,
                "reason": reason,
                "approval_state": approval_state,
            },
        )

        if approval_state == "APPROVED" and correction.triggers_recalculation:
            engine = JourneyReconstructionEngine(db, tenant_id=vc.tenant_id)
            engine.reconstruct_vessel_call(vc, triggered_by="CORRECTION")
            correction.recalculated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(correction)
        return correction

    @staticmethod
    def _record_canonical_override(
        db: Session,
        vessel_call_id: str,
        event_definition_id: str,
        new_occ_id: str,
        prior_occ_id: Optional[str],
        correction: ObservationCorrection,
        actor: str,
        reason: str,
    ) -> None:
        existing = db.execute(
            select(CanonicalObservation).where(
                CanonicalObservation.vessel_call_id == vessel_call_id,
                CanonicalObservation.event_definition_id == event_definition_id,
            )
        ).scalar_one_or_none()
        if not existing:
            existing = CanonicalObservation(
                vessel_call_id=vessel_call_id,
                event_definition_id=event_definition_id,
                candidate_event_occurrence_ids=[],
            )
            db.add(existing)
            db.flush()

        candidates = set(existing.candidate_event_occurrence_ids or [])
        candidates.add(str(new_occ_id))
        if prior_occ_id:
            candidates.add(str(prior_occ_id))

        existing.candidate_event_occurrence_ids = sorted(candidates)
        existing.selected_event_occurrence_id = new_occ_id
        existing.selection_method = "STEWARD_OVERRIDE"
        existing.conflict_detected = existing.conflict_detected or len(candidates) > 1
        existing.selection_reasoning = {
            "correction_id": str(correction.id),
            "reason": reason,
            "actor": actor,
        }
        existing.decided_by = actor
        existing.decided_at = datetime.now(timezone.utc)
        db.flush()
