from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.auth.tenant import resolve_principal_tenant
from apps.api.core.database import get_db
from apps.api.models.canonical import VesselCall
from apps.api.models.identity import MatchCandidate, MatchEvidence, MergeDecision
from apps.api.services.identity.engine import IdentityEngine
from apps.api.services.identity.merger import MergerService
from apps.api.services.identity.survivorship import SurvivorshipEngine

router = APIRouter(prefix="/identity", tags=["Identity Resolution"])


class AttributeEvidenceSchema(BaseModel):
    attribute: str
    record_1_value: str | None = None
    record_2_value: str | None = None
    agreement: str
    weight: float
    contribution: float
    explanation: str


class MatchCandidateSchema(BaseModel):
    id: str
    source_record_1_id: str
    source_record_2_id: str
    vessel_name_1: str | None = None
    vessel_name_2: str | None = None
    vcn_1: str | None = None
    vcn_2: str | None = None
    match_score: float
    status: str
    match_type: str | None = None
    conflict_detected: bool
    conflict_reasons: list[str] | None = None
    evidences: list[AttributeEvidenceSchema] | None = None


class MergeRequest(BaseModel):
    candidate_id: str
    manual_override: bool = False
    custom_survivorship: dict[str, Any] | None = None
    notes: str | None = None


class UnmergeRequest(BaseModel):
    notes: str | None = None


@router.post("/resolve")
def run_identity_resolution(
    auto_merge: bool = Query(True, description="Whether to automatically merge eligible candidates"),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("merge", "vessel_call")),
):
    """
    Scans unmerged vessel calls, evaluates pairwise deterministic and probabilistic matching rules,
    persists explainable evidence, and merges qualifying duplicates.
    """
    tenant_id = resolve_principal_tenant(principal)
    engine = IdentityEngine(db, tenant_id=tenant_id)
    candidates = engine.generate_candidates()

    merged_count = 0
    if auto_merge:
        decisions = engine.auto_merge_candidates()
        merged_count = len(decisions)

    total_candidates = len(candidates)
    active_count = engine.get_consolidated_population_count()

    return {
        "status": "success",
        "tenant_id": tenant_id,
        "total_candidates_found": total_candidates,
        "auto_merged_count": merged_count,
        "consolidated_base_population": active_count,
    }


@router.get("/candidates")
def list_candidates(
    status_filter: str | None = Query(None, alias="status"),
    conflict_only: bool | None = Query(None),
    min_score: float | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """
    Returns explainable match candidates with filtering and pagination.
    """
    query = select(MatchCandidate).order_by(desc(MatchCandidate.match_score))

    if status_filter:
        query = query.where(MatchCandidate.status == status_filter)
    if conflict_only is not None:
        query = query.where(MatchCandidate.conflict_detected == conflict_only)
    if min_score is not None:
        query = query.where(MatchCandidate.match_score >= min_score)

    offset = (page - 1) * limit
    candidates = db.execute(query.offset(offset).limit(limit)).scalars().all()

    # Enrich with VCN and vessel names
    results = []
    for c in candidates:
        v1 = db.execute(select(VesselCall).where(VesselCall.id == c.source_record_1_id)).scalar_one_or_none()
        v2 = db.execute(select(VesselCall).where(VesselCall.id == c.source_record_2_id)).scalar_one_or_none()
        results.append({
            "id": str(c.id),
            "source_record_1_id": c.source_record_1_id,
            "source_record_2_id": c.source_record_2_id,
            "vessel_name_1": v1.vessel_name if v1 else "Unknown",
            "vessel_name_2": v2.vessel_name if v2 else "Unknown",
            "vcn_1": v1.vcn if v1 else None,
            "vcn_2": v2.vcn if v2 else None,
            "match_score": c.match_score,
            "status": c.status,
            "match_type": c.match_type,
            "conflict_detected": c.conflict_detected,
            "conflict_reasons": c.conflict_reasons,
        })

    return {
        "page": page,
        "limit": limit,
        "count": len(results),
        "items": results,
    }


@router.get("/candidates/{candidate_id}")
def get_candidate_details(
    candidate_id: str,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """
    Retrieves full explainable match evidence breakdown for a single candidate pair.
    """
    candidate = db.execute(
        select(MatchCandidate).where(MatchCandidate.id == candidate_id)
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="MatchCandidate not found")

    v1 = db.execute(select(VesselCall).where(VesselCall.id == candidate.source_record_1_id)).scalar_one_or_none()
    v2 = db.execute(select(VesselCall).where(VesselCall.id == candidate.source_record_2_id)).scalar_one_or_none()

    evidence_rows = db.execute(
        select(MatchEvidence).where(MatchEvidence.match_candidate_id == candidate.id)
    ).scalars().all()

    evidence_list = [
        ev.evidence_detail for ev in evidence_rows if isinstance(ev.evidence_detail, dict)
    ]

    return {
        "id": str(candidate.id),
        "source_record_1_id": candidate.source_record_1_id,
        "source_record_2_id": candidate.source_record_2_id,
        "vessel_name_1": v1.vessel_name if v1 else None,
        "vessel_name_2": v2.vessel_name if v2 else None,
        "vcn_1": v1.vcn if v1 else None,
        "vcn_2": v2.vcn if v2 else None,
        "match_score": candidate.match_score,
        "status": candidate.status,
        "match_type": candidate.match_type,
        "conflict_detected": candidate.conflict_detected,
        "conflict_reasons": candidate.conflict_reasons,
        "evidence_breakdown": evidence_list,
    }


@router.get("/preview/{candidate_id}")
def get_merge_preview(
    candidate_id: str,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """
    Generates side-by-side comparison table and consolidated preview with field-level provenance.
    """
    candidate = db.execute(
        select(MatchCandidate).where(MatchCandidate.id == candidate_id)
    ).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="MatchCandidate not found")

    v1 = db.execute(select(VesselCall).where(VesselCall.id == candidate.source_record_1_id)).scalar_one_or_none()
    v2 = db.execute(select(VesselCall).where(VesselCall.id == candidate.source_record_2_id)).scalar_one_or_none()
    if not v1 or not v2:
        raise HTTPException(status_code=404, detail="One or both vessel calls not found")

    preview = SurvivorshipEngine.generate_preview(v1, v2)
    preview["candidate_id"] = str(candidate.id)
    preview["match_score"] = candidate.match_score
    preview["conflict_detected"] = candidate.conflict_detected
    preview["conflict_reasons"] = candidate.conflict_reasons
    return preview


@router.post("/merge")
def merge_candidate(
    req: MergeRequest,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("merge", "vessel_call")),
):
    """
    Executes a governed merge decision, writing full prior snapshot, updating survivor attributes,
    and marking the duplicate record.
    """
    try:
        decision = MergerService.execute_merge(
            db=db,
            candidate_id=req.candidate_id,
            actor=principal.email or principal.user_id,
            manual=req.manual_override,
            custom_survivorship=req.custom_survivorship,
        )
        return {
            "status": "success",
            "message": "Vessel calls merged successfully",
            "decision_id": str(decision.id),
            "survivor_record_id": decision.survivor_record_id,
            "merged_record_id": decision.merged_record_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/unmerge/{decision_id}")
def unmerge_decision(
    decision_id: str,
    req: UnmergeRequest = None,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("unmerge", "vessel_call")),
):
    """
    Executes a safe and complete unmerge, restoring the original records and children
    intact from the prior state snapshot.
    """
    try:
        notes = req.notes if req else None
        res = MergerService.execute_unmerge(
            db=db,
            decision_id=decision_id,
            actor=principal.email or principal.user_id,
            notes=notes,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/decisions")
def list_merge_decisions(
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """
    Lists merge decisions with audit trail and snapshot metadata.
    """
    decisions = db.execute(
        select(MergeDecision).order_by(desc(MergeDecision.created_at))
    ).scalars().all()

    return [
        {
            "id": str(d.id),
            "match_candidate_id": str(d.match_candidate_id),
            "decision": d.decision,
            "is_reversible": d.is_reversible,
            "survivor_record_id": d.survivor_record_id,
            "merged_record_id": d.merged_record_id,
            "rule_version": d.rule_version,
            "actor": d.actor,
            "notes": d.notes,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in decisions
    ]


@router.get("/population")
def get_population_summary(
    tenant_id: str | None = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
):
    """
    Returns the total rows, merged rows, and active consolidated population count.
    """
    target_tenant = resolve_principal_tenant(principal, tenant_id)
    all_calls = db.execute(
        select(VesselCall).where(VesselCall.tenant_id == target_tenant)
    ).scalars().all()

    total_rows = len(all_calls)
    merged_count = sum(1 for v in all_calls if v.is_merged)
    consolidated_count = total_rows - merged_count

    return {
        "tenant_id": target_tenant,
        "total_rows": total_rows,
        "merged_rows": merged_count,
        "consolidated_base_population": consolidated_count,
        "target_base_population": 72,
        "reconciled": consolidated_count == 72,
    }
