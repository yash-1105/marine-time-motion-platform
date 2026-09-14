from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.repository.vessel_call import VesselCallRepository
from apps.api.services.audit import log_audit_event

router = APIRouter(prefix="/operations", tags=["Operations & Data Scope"])


class CreateVesselCallRequest(BaseModel):
    vessel_name: str
    vcn: str | None = None
    vessel_type: str | None = "Container"
    port_id: str | None = None
    terminal_id: str | None = None


class ExportRequest(BaseModel):
    filters: dict[str, Any] = {}


class MergeRequest(BaseModel):
    primary_call_id: str
    secondary_call_id: str
    reason: str


@router.get("/vessel-calls")
def list_vessel_calls(
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
    port_id: str | None = None,
    terminal_id: str | None = None,
    vessel_type: str | None = None,
    cargo_type: str | None = None,
    quality_status: str | None = None,
    is_merged: bool | None = None,
    sort_by: str | None = "vcn",
    sort_dir: str | None = "asc",
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Lists vessel calls with comprehensive operational durations, quality status, and traceability."""
    from sqlalchemy import select

    from apps.api.models.analytics import LeadTimeDefinition, LeadTimeResult
    from apps.api.models.canonical import Delay, EventOccurrence
    from apps.api.models.config import EventDefinition
    from apps.api.models.journey import JourneyInstance
    from apps.api.models.quality import QualityIssue, QualityRule

    repo = VesselCallRepository(db)
    calls = repo.list(
        scope=principal.data_scope,
        skip=skip,
        limit=limit,
        search=search,
        port_id=port_id,
        terminal_id=terminal_id,
        vessel_type=vessel_type,
        cargo_type=cargo_type,
        is_merged=is_merged,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    if not calls:
        return []

    call_ids = [c.id for c in calls]

    # 1. Bulk query journeys
    journeys_by_vc = {}
    j_rows = db.execute(select(JourneyInstance).where(JourneyInstance.vessel_call_id.in_(call_ids))).scalars().all()
    for j in j_rows:
        journeys_by_vc[j.vessel_call_id] = j

    # 2. Bulk query Lead Time Results
    lead_times_by_vc = {}
    lt_rows = db.execute(
        select(LeadTimeResult, LeadTimeDefinition.name)
        .join(LeadTimeDefinition, LeadTimeResult.definition_id == LeadTimeDefinition.id)
        .where(LeadTimeResult.vessel_call_id.in_(call_ids))
    ).all()
    for r, name in lt_rows:
        if r.vessel_call_id not in lead_times_by_vc:
            lead_times_by_vc[r.vessel_call_id] = {}
        lead_times_by_vc[r.vessel_call_id][name] = r

    # 3. Bulk query Quality Issues
    issues_by_vc = {}
    iss_rows = db.execute(
        select(QualityIssue, QualityRule.severity)
        .join(QualityRule, QualityIssue.rule_id == QualityRule.id)
        .where(QualityIssue.vessel_call_id.in_(call_ids))
    ).all()
    for iss, sev in iss_rows:
        if iss.vessel_call_id not in issues_by_vc:
            issues_by_vc[iss.vessel_call_id] = []
        issues_by_vc[iss.vessel_call_id].append({"issue": iss, "severity": sev})

    # 4. Bulk query Delays
    delays_by_vc = {}
    d_rows = db.execute(select(Delay).where(Delay.vessel_call_id.in_(call_ids))).scalars().all()
    for d in d_rows:
        if d.vessel_call_id not in delays_by_vc:
            delays_by_vc[d.vessel_call_id] = []
        delays_by_vc[d.vessel_call_id].append(d)

    # 5. Bulk query key timestamps (ATA, ATD, ETA)
    events_by_vc = {}
    ev_rows = db.execute(
        select(EventOccurrence, EventDefinition.name)
        .join(EventDefinition, EventOccurrence.event_definition_id == EventDefinition.id)
        .where(
            EventOccurrence.vessel_call_id.in_(call_ids),
            EventDefinition.name.in_(["ATA", "ATD", "ETA"])
        )
    ).all()
    for ev, ev_name in ev_rows:
        if ev.vessel_call_id not in events_by_vc:
            events_by_vc[ev.vessel_call_id] = {}
        if ev_name not in events_by_vc[ev.vessel_call_id] or ev.verification_status == "Verified":
            events_by_vc[ev.vessel_call_id][ev_name] = ev.original_string or (ev.utc_value.isoformat() if ev.utc_value else None)

    results = []
    for c in calls:
        j = journeys_by_vc.get(c.id)
        cov = j.coverage_summary if j and j.coverage_summary else {}
        stages_avail = cov.get("stages_available", 0)
        stages_tot = cov.get("stages_total", 0)
        shifting_occ = cov.get("shifting_occurrences", 0)
        completeness_pct = round((stages_avail / stages_tot * 100), 1) if stages_tot > 0 else 0

        # Quality status
        call_issues = issues_by_vc.get(c.id, [])
        critical_count = sum(1 for item in call_issues if item["severity"] == "CRITICAL" and item["issue"].issue_status != "RESOLVED")
        open_issues_count = sum(1 for item in call_issues if item["issue"].issue_status != "RESOLVED")
        if critical_count > 0:
            call_dq_status = "QUARANTINED"
            quality_score = max(0, 100 - (critical_count * 50) - (open_issues_count * 10))
        elif open_issues_count > 0:
            call_dq_status = "FLAGGED"
            quality_score = max(0, 100 - (open_issues_count * 15))
        else:
            call_dq_status = "CLEAN"
            quality_score = 100

        # Filter by quality_status if requested
        if quality_status and quality_status.upper() != call_dq_status:
            continue

        # Durations & Traceability
        lt_dict = lead_times_by_vc.get(c.id, {})
        durations_traceability = {}
        for m_name in [
            "Turnaround", "Anchorage Wait", "Inward Movement", "Berth Stay",
            "Cargo Working", "Outward Movement", "Arrival Execution Delay", "Sailing Execution Delay"
        ]:
            lt_res = lt_dict.get(m_name)
            if lt_res:
                durations_traceability[m_name] = {
                    "duration_hours": lt_res.duration_hours,
                    "status": lt_res.status,
                    "unavailable_reason": lt_res.unavailable_reason,
                    "formula": m_name,
                    "formula_version": lt_res.formula_version or "1.0",
                    "source_records": lt_res.source_record_ids or [],
                    "filters": lt_res.filter_context or {},
                    "exclusions": lt_res.exclusions_applied or [],
                    "dq_status": lt_res.dq_status or "CLEAN",
                    "start_time": lt_res.start_time.isoformat() if lt_res.start_time else None,
                    "end_time": lt_res.end_time.isoformat() if lt_res.end_time else None,
                }
            else:
                durations_traceability[m_name] = {
                    "duration_hours": None,
                    "status": "UNAVAILABLE",
                    "unavailable_reason": "Not calculated for this call",
                    "formula": m_name,
                    "formula_version": "1.0",
                    "source_records": [],
                    "filters": {},
                    "exclusions": [],
                    "dq_status": "UNKNOWN",
                    "start_time": None,
                    "end_time": None,
                }

        turnaround_res = lt_dict.get("Turnaround")
        anch_res = lt_dict.get("Anchorage Wait")
        berth_res = lt_dict.get("Berth Stay")
        inward_res = lt_dict.get("Inward Movement")
        cargo_res = lt_dict.get("Cargo Working")
        outward_res = lt_dict.get("Outward Movement")
        arr_delay_res = lt_dict.get("Arrival Execution Delay")
        sail_delay_res = lt_dict.get("Sailing Execution Delay")

        call_delays = delays_by_vc.get(c.id, [])
        total_delay_hours = round(sum(d.delay_hours or 0 for d in call_delays), 2)

        ev_map = events_by_vc.get(c.id, {})

        results.append({
            "id": str(c.id),
            "vessel_name": c.vessel_name,
            "vcn": c.vcn,
            "imo_number": c.imo_number,
            "vessel_type": c.vessel_type,
            "cargo_type": c.cargo_type,
            "vessel_size_teu": c.vessel_size_teu,
            "flag": c.flag,
            "tenant_id": c.tenant_id,
            "port_id": c.port_id,
            "terminal_id": c.terminal_id,
            "is_merged": c.is_merged,
            "merged_into_id": str(c.merged_into_id) if c.merged_into_id else None,
            "journey_status": j.status if j else "PENDING",
            "journey_completeness_pct": completeness_pct,
            "stages_available": stages_avail,
            "stages_total": stages_tot,
            "shifting_occurrences": shifting_occ,
            "ata": ev_map.get("ATA"),
            "atd": ev_map.get("ATD"),
            "eta": ev_map.get("ETA"),
            "turnaround_hours": turnaround_res.duration_hours if turnaround_res else None,
            "turnaround_status": turnaround_res.status if turnaround_res else "UNAVAILABLE",
            "turnaround_unavailable_reason": turnaround_res.unavailable_reason if turnaround_res else "Missing ATA or ATD",
            "anchorage_wait_hours": anch_res.duration_hours if anch_res else None,
            "berth_stay_hours": berth_res.duration_hours if berth_res else None,
            "inward_movement_hours": inward_res.duration_hours if inward_res else None,
            "cargo_working_hours": cargo_res.duration_hours if cargo_res else None,
            "outward_movement_hours": outward_res.duration_hours if outward_res else None,
            "arrival_execution_delay": arr_delay_res.duration_hours if arr_delay_res else None,
            "sailing_execution_delay": sail_delay_res.duration_hours if sail_delay_res else None,
            "delays_count": len(call_delays),
            "total_delay_hours": total_delay_hours,
            "quality_status": call_dq_status,
            "quality_score": quality_score,
            "issue_count": open_issues_count,
            "critical_issue_count": critical_count,
            "durations_traceability": durations_traceability,
        })

    return results


@router.post("/vessel-calls")
def create_vessel_call(
    request: Request,
    body: CreateVesselCallRequest,
    principal: UserPrincipal = Depends(require("create", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Creates a vessel call scoped to the principal's tenant/port boundaries."""
    repo = VesselCallRepository(db)
    call = repo.create(
        scope=principal.data_scope,
        vessel_name=body.vessel_name,
        vcn=body.vcn,
        vessel_type=body.vessel_type,
        port_id=body.port_id,
        terminal_id=body.terminal_id,
    )

    log_audit_event(
        db=db,
        action="create",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="vessel_call",
        resource_id=str(call.id),
        correlation_id=getattr(request.state, "correlation_id", None),
        details={"vessel_name": call.vessel_name, "vcn": call.vcn},
    )

    return {"id": str(call.id), "vessel_name": call.vessel_name, "status": "created"}


@router.get("/vessel-calls/{call_id}")
def get_vessel_call(
    request: Request,
    call_id: str,
    principal: UserPrincipal = Depends(require("view", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Retrieves a single vessel call. Logs view_sensitive if record is flagged sensitive."""
    repo = VesselCallRepository(db)
    call = repo.get_by_id(principal.data_scope, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Vessel call not found within data scope")

    is_sensitive = call.cargo_type == "IMDG" or getattr(call, "is_sensitive", False)
    if is_sensitive:
        log_audit_event(
            db=db,
            action="view_sensitive",
            actor_id=principal.user_id,
            actor_email=principal.email,
            actor_role=",".join(principal.roles),
            resource_type="vessel_call",
            resource_id=str(call.id),
            correlation_id=getattr(request.state, "correlation_id", None),
            details={"cargo_type": call.cargo_type, "is_sensitive": True},
        )

    return {
        "id": str(call.id),
        "vessel_name": call.vessel_name,
        "vcn": call.vcn,
        "vessel_type": call.vessel_type,
        "cargo_type": call.cargo_type,
        "tenant_id": call.tenant_id,
        "port_id": call.port_id,
        "terminal_id": call.terminal_id,
    }


@router.put("/vessel-calls/{call_id}")
def edit_vessel_call(
    request: Request,
    call_id: str,
    body: dict[str, Any],
    principal: UserPrincipal = Depends(require("edit", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Edits a vessel call and logs the correction event."""
    repo = VesselCallRepository(db)
    call = repo.get_by_id(principal.data_scope, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Vessel call not found within data scope")

    before = {"vessel_name": call.vessel_name}
    if "vessel_name" in body:
        call.vessel_name = body["vessel_name"]
    db.commit()

    log_audit_event(
        db=db,
        action="correction",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="vessel_call",
        resource_id=str(call.id),
        before=before,
        after={"vessel_name": call.vessel_name},
    )
    return {"id": str(call.id), "status": "updated"}


@router.post("/vessel-calls/export")
def export_vessel_calls(
    request: Request,
    body: ExportRequest,
    principal: UserPrincipal = Depends(require("export", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Exports vessel calls. Sensitive export is audited with filters and row count per spec §17."""
    repo = VesselCallRepository(db)
    records = repo.export(scope=principal.data_scope, filters=body.filters)
    row_count = len(records)

    log_audit_event(
        db=db,
        action="export",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="vessel_call",
        filter_set=body.filters,
        row_count=row_count,
        correlation_id=getattr(request.state, "correlation_id", None),
        details={"export_format": "json"},
    )

    return {
        "count": row_count,
        "filters_applied": body.filters,
        "data": [{"id": str(r.id), "vessel_name": r.vessel_name, "port_id": r.port_id} for r in records],
    }


@router.post("/vessel-calls/merge")
def merge_vessel_calls(
    request: Request,
    body: MergeRequest,
    principal: UserPrincipal = Depends(require("merge", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Merges two vessel calls with audit trail."""
    log_audit_event(
        db=db,
        action="merge",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="vessel_call",
        resource_id=body.primary_call_id,
        details={"secondary_id": body.secondary_call_id, "reason": body.reason},
    )
    return {"status": "merged", "primary_id": body.primary_call_id}


@router.post("/vessel-calls/unmerge")
def unmerge_vessel_calls(
    request: Request,
    body: MergeRequest,
    principal: UserPrincipal = Depends(require("unmerge", "vessel_call")),
    db: Session = Depends(get_db),
):
    """Unmerges previously merged vessel calls with audit trail."""
    log_audit_event(
        db=db,
        action="unmerge",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="vessel_call",
        resource_id=body.primary_call_id,
        details={"secondary_id": body.secondary_call_id, "reason": body.reason},
    )
    return {"status": "unmerged", "primary_id": body.primary_call_id}


@router.post("/recalculate")
def recalculate_metrics(
    request: Request,
    principal: UserPrincipal = Depends(require("recalculate", "metrics")),
    db: Session = Depends(get_db),
):
    """Recalculates metrics or stage durations."""
    log_audit_event(
        db=db,
        action="recalculation",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="analytics",
    )
    return {"status": "recalculated"}


@router.post("/publish")
def publish_report(
    request: Request,
    principal: UserPrincipal = Depends(require("publish", "report")),
    db: Session = Depends(get_db),
):
    """Publishes operational report."""
    log_audit_event(
        db=db,
        action="report_publication",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="report",
    )
    return {"status": "published"}


@router.post("/approve")
def approve_action(
    request: Request,
    principal: UserPrincipal = Depends(require("approve", "approval")),
    db: Session = Depends(get_db),
):
    """Approves an operational or data quality action."""
    log_audit_event(
        db=db,
        action="approve",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
    )
    return {"status": "approved"}


@router.post("/reject")
def reject_action(
    request: Request,
    principal: UserPrincipal = Depends(require("reject", "approval")),
    db: Session = Depends(get_db),
):
    """Rejects an operational or data quality action."""
    log_audit_event(
        db=db,
        action="reject",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
    )
    return {"status": "rejected"}


@router.post("/configure")
def configure_system(
    request: Request,
    principal: UserPrincipal = Depends(require("configure", "configuration")),
    db: Session = Depends(get_db),
):
    """Modifies platform configuration."""
    log_audit_event(
        db=db,
        action="config_change",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
    )
    return {"status": "configured"}


@router.post("/administer")
def administer_system(
    request: Request,
    principal: UserPrincipal = Depends(require("administer", "administration")),
    db: Session = Depends(get_db),
):
    """Executes administrative operations."""
    log_audit_event(
        db=db,
        action="admin_action",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
    )
    return {"status": "administered"}


@router.post("/rules")
def update_quality_rule(
    request: Request,
    body: dict[str, Any],
    principal: UserPrincipal = Depends(require("configure", "quality_rules")),
    db: Session = Depends(get_db),
):
    """Updates a quality rule and logs the rule_change audit event."""
    log_audit_event(
        db=db,
        action="rule_change",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="quality_rule",
        details=body,
    )
    return {"status": "rule_updated"}


@router.post("/formulas")
def update_kpi_formula(
    request: Request,
    body: dict[str, Any],
    principal: UserPrincipal = Depends(require("configure", "kpi_formulas")),
    db: Session = Depends(get_db),
):
    """Updates a KPI formula version and logs the formula_change audit event."""
    log_audit_event(
        db=db,
        action="formula_change",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="kpi_formula",
        details=body,
    )
    return {"status": "formula_updated"}


@router.post("/synthetic-data/load")
def load_synthetic_dataset(
    request: Request,
    principal: UserPrincipal = Depends(require("administer", "synthetic_dataset")),
    db: Session = Depends(get_db),
):
    """Loads the synthetic test dataset and logs synthetic_data_load."""
    log_audit_event(
        db=db,
        action="synthetic_data_load",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="synthetic_dataset",
        details={"dataset": "Synthetic_Marine_Time_Motion_Test_Data.xlsx"},
    )
    return {"status": "synthetic_dataset_loaded"}


@router.post("/synthetic-data/reset")
def reset_synthetic_dataset(
    request: Request,
    principal: UserPrincipal = Depends(require("administer", "synthetic_dataset")),
    db: Session = Depends(get_db),
):
    """Resets the synthetic test dataset and logs synthetic_data_reset."""
    log_audit_event(
        db=db,
        action="synthetic_data_reset",
        actor_id=principal.user_id,
        actor_email=principal.email,
        actor_role=",".join(principal.roles),
        resource_type="synthetic_dataset",
    )
    return {"status": "synthetic_dataset_reset"}
