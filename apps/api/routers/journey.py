from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.models.canonical import VesselCall
from apps.api.models.journey import (
    CanonicalObservation,
    Handover,
    JourneyInstance,
    JourneyNarrative,
    ObservationCorrection,
    ReconstructionHistory,
    StageOccurrence,
)
from apps.api.services.journey.corrections import JourneyCorrectionService
from apps.api.services.journey.narrative import JourneyNarrativeService
from apps.api.services.journey.reconstructor import JourneyReconstructionEngine

router = APIRouter(prefix="/journey", tags=["Journey Reconstruction"])


class CorrectionRequest(BaseModel):
    event_definition_id: str
    new_utc_value: datetime
    reason: str
    prior_event_occurrence_id: Optional[str] = None
    approval_state: str = "APPROVED"


@router.post("/reconstruct")
def run_reconstruction(
    vessel_call_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("recalculate", "vessel_call")),
):
    """
    Reconstructs the journey for one vessel call, or every unmerged vessel call in the
    principal's tenant when no id is given.
    """
    engine = JourneyReconstructionEngine(db, tenant_id=principal.data_scope.tenant_id)
    if vessel_call_id:
        vc = db.execute(select(VesselCall).where(VesselCall.id == vessel_call_id)).scalar_one_or_none()
        if not vc:
            raise HTTPException(status_code=404, detail="VesselCall not found")
        instance = engine.reconstruct_vessel_call(vc, triggered_by="MANUAL")
        db.commit()
        return {"status": "success", "vessel_call_id": vessel_call_id, "journey_instance_id": str(instance.id)}

    summary = engine.reconstruct_all(triggered_by="MANUAL")
    return {"status": "success", **summary}


@router.get("/{vessel_call_id}")
def get_journey(
    vessel_call_id: str,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Unified chronological timeline, stage grouping, decomposition, and deviation report."""
    vc = db.execute(select(VesselCall).where(VesselCall.id == vessel_call_id)).scalar_one_or_none()
    if not vc:
        raise HTTPException(status_code=404, detail="VesselCall not found")

    instance = db.execute(
        select(JourneyInstance).where(JourneyInstance.vessel_call_id == vessel_call_id)
    ).scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="No reconstructed journey for this vessel call")

    stages = db.execute(
        select(StageOccurrence)
        .where(StageOccurrence.journey_instance_id == instance.id)
        .order_by(StageOccurrence.sequence_index, StageOccurrence.shift_occurrence_index)
    ).scalars().all()

    handovers = db.execute(
        select(Handover).where(
            Handover.from_stage_occurrence_id.in_([s.id for s in stages]) if stages else Handover.id.is_(None)
        )
    ).scalars().all()

    return {
        "vessel_call_id": vessel_call_id,
        "vcn": vc.vcn,
        "vessel_name": vc.vessel_name,
        "journey_instance_id": str(instance.id),
        "status": instance.status,
        "reconstruction_version": instance.reconstruction_version,
        "rule_version": instance.rule_version,
        "computed_at": instance.computed_at.isoformat() if instance.computed_at else None,
        "coverage_summary": instance.coverage_summary,
        "time_decomposition": instance.time_decomposition,
        "deviation_report": instance.deviation_report,
        "stages": [
            {
                "id": str(s.id),
                "stage_name": s.stage_name,
                "sequence_index": s.sequence_index,
                "shift_occurrence_index": s.shift_occurrence_index,
                "availability": s.availability,
                "is_missing": s.is_missing,
                "is_inferred": s.is_inferred,
                "inference_reason": s.inference_reason,
                "start_time": s.start_time.isoformat() if s.start_time else None,
                "end_time": s.end_time.isoformat() if s.end_time else None,
                "duration_hours": s.duration_hours,
                "time_category": s.time_category,
                "status": s.status,
                "deviation_type": s.deviation_type,
                "deviation_detail": s.deviation_detail,
            }
            for s in stages
        ],
        "handovers": [
            {
                "from_stage_occurrence_id": str(h.from_stage_occurrence_id),
                "to_stage_occurrence_id": str(h.to_stage_occurrence_id),
                "from_actor": h.from_actor,
                "to_actor": h.to_actor,
                "status": h.status,
                "handover_time": h.handover_time.isoformat() if h.handover_time else None,
                "wait_duration_hours": h.wait_duration_hours,
            }
            for h in handovers
        ],
    }


@router.get("/{vessel_call_id}/conflicts")
def get_conflicts(
    vessel_call_id: str,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Canonical occurrence selection decisions, with every retained observation visible."""
    rows = db.execute(
        select(CanonicalObservation).where(CanonicalObservation.vessel_call_id == vessel_call_id)
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "event_definition_id": str(r.event_definition_id),
            "candidate_event_occurrence_ids": r.candidate_event_occurrence_ids,
            "selected_event_occurrence_id": str(r.selected_event_occurrence_id) if r.selected_event_occurrence_id else None,
            "conflict_detected": r.conflict_detected,
            "selection_method": r.selection_method,
            "selection_reasoning": r.selection_reasoning,
            "quality_issue_id": str(r.quality_issue_id) if r.quality_issue_id else None,
            "decided_by": r.decided_by,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        }
        for r in rows
    ]


@router.get("/{vessel_call_id}/events")
def get_vessel_events(
    vessel_call_id: str,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Retrieves all canonical event occurrences and timestamp envelopes for a vessel call."""
    from apps.api.models.canonical import EventOccurrence
    from apps.api.models.config import EventDefinition

    events = db.execute(
        select(EventOccurrence, EventDefinition)
        .join(EventDefinition, EventOccurrence.event_definition_id == EventDefinition.id)
        .where(EventOccurrence.vessel_call_id == vessel_call_id)
        .order_by(EventOccurrence.utc_value.asc().nulls_last())
    ).all()

    return [
        {
            "id": str(ev.id),
            "event_name": defn.name,
            "category": defn.category,
            "original_string": ev.original_string,
            "utc_value": ev.utc_value.isoformat() if ev.utc_value else None,
            "timezone": ev.source_timezone,
            "source_system": ev.source_system,
            "source_record_id": ev.source_record_id,
            "verification_status": ev.verification_status,
            "confidence": ev.confidence,
            "is_quarantined": ev.is_quarantined,
            "capture_method": ev.capture_method,
        }
        for ev, defn in events
    ]


@router.post("/{vessel_call_id}/corrections")
def create_correction(
    vessel_call_id: str,
    req: CorrectionRequest,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("edit", "vessel_call")),
):
    """
    Creates a new canonical observation superseding the prior one, with reason, actor, timestamp
    and approval state. Never mutates raw. Triggers recalculation once approved.
    """
    try:
        correction = JourneyCorrectionService.create_correction(
            db=db,
            vessel_call_id=vessel_call_id,
            event_definition_id=req.event_definition_id,
            new_utc_value=req.new_utc_value,
            reason=req.reason,
            actor=principal.email or principal.user_id,
            prior_event_occurrence_id=req.prior_event_occurrence_id,
            approval_state=req.approval_state,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {
        "status": "success",
        "correction_id": str(correction.id),
        "new_event_occurrence_id": str(correction.new_event_occurrence_id),
        "prior_event_occurrence_id": str(correction.prior_event_occurrence_id) if correction.prior_event_occurrence_id else None,
        "approval_state": correction.approval_state,
        "recalculated_at": correction.recalculated_at.isoformat() if correction.recalculated_at else None,
    }


@router.get("/{vessel_call_id}/corrections")
def list_corrections(
    vessel_call_id: str,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    rows = db.execute(
        select(ObservationCorrection)
        .where(ObservationCorrection.vessel_call_id == vessel_call_id)
        .order_by(desc(ObservationCorrection.created_at))
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "event_definition_id": str(r.event_definition_id) if r.event_definition_id else None,
            "prior_event_occurrence_id": str(r.prior_event_occurrence_id) if r.prior_event_occurrence_id else None,
            "new_event_occurrence_id": str(r.new_event_occurrence_id) if r.new_event_occurrence_id else None,
            "reason": r.reason,
            "actor": r.actor,
            "approval_state": r.approval_state,
            "recalculated_at": r.recalculated_at.isoformat() if r.recalculated_at else None,
        }
        for r in rows
    ]


@router.post("/{vessel_call_id}/narrative")
def generate_narrative(
    vessel_call_id: str,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Generates a grounded, factual AI narrative citing internal record ids."""
    try:
        narrative = JourneyNarrativeService.generate(db, vessel_call_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return {
        "id": str(narrative.id),
        "narrative_text": narrative.narrative_text,
        "grounding_record_ids": narrative.grounding_record_ids,
        "model_name": narrative.model_name,
        "is_ai_generated": narrative.is_ai_generated,
        "inference_status": narrative.inference_status,
        "generated_at": narrative.generated_at.isoformat() if narrative.generated_at else None,
    }


@router.get("/{vessel_call_id}/history")
def get_reconstruction_history(
    vessel_call_id: str,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    rows = db.execute(
        select(ReconstructionHistory)
        .where(ReconstructionHistory.vessel_call_id == vessel_call_id)
        .order_by(ReconstructionHistory.run_version)
    ).scalars().all()
    return [
        {
            "run_version": r.run_version,
            "rule_version": r.rule_version,
            "triggered_by": r.triggered_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "snapshot": r.snapshot,
        }
        for r in rows
    ]


@router.get("/coverage/summary")
def get_coverage_summary(
    tenant_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """Aggregate reconstruction coverage across all active vessel calls in scope."""
    target_tenant = tenant_id or principal.data_scope.tenant_id
    vessel_calls = db.execute(
        select(VesselCall).where(VesselCall.tenant_id == target_tenant, VesselCall.is_merged == False)  # noqa: E712
    ).scalars().all()
    vc_ids = [vc.id for vc in vessel_calls]

    instances = db.execute(
        select(JourneyInstance).where(JourneyInstance.vessel_call_id.in_(vc_ids))
    ).scalars().all() if vc_ids else []

    reconstructed = sum(1 for i in instances if i.status == "RECONSTRUCTED")
    return {
        "tenant_id": target_tenant,
        "total_vessel_calls": len(vessel_calls),
        "reconstructed": reconstructed,
        "coverage": f"{reconstructed} of {len(vessel_calls)}",
    }
