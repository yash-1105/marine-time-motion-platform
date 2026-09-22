"""Governed KPI REST API (spec §11, §16, phase-08-kpi-engine.md).

All routes are protected by repository-level authorization dependency `require()`.
Supports all 55 governed KPIs, scorecards, Green/Amber/Red status banding, trends,
primary/alias management to prevent double counting, and audited recalculation.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.models.analytics import KPI, KPIFormulaVersion, KPIResult, LeadTimeDefinition, StatisticalAggregate
from apps.api.models.canonical import ServiceAssignment, ServiceExecution, ServiceRequest, VesselCall
from apps.api.models.ingestion import IngestionBatch
from apps.api.services.kpi.benchmarks import KPIBenchmarkService
from apps.api.services.kpi.engine import KPIEngine
from apps.api.services.kpi.registry import ensure_kpi_registry

router = APIRouter(prefix="/kpis", tags=["KPI Engine & Scorecard"])


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ──────────────────────────────────────────────────────────────────────────────


class KPICalculateRequest(BaseModel):
    cohort_filters: dict[str, Any] | None = Field(None, description="Filters such as vessel_type, terminal_code, unit")
    period_start: datetime | None = Field(None, description="Start date for reporting period")
    period_end: datetime | None = Field(None, description="End date for reporting period")
    grain: str = Field("ALL", description="ALL | DAILY | WEEKLY | MONTHLY | QUARTERLY | ANNUAL")


class KPIRecalculateRequest(BaseModel):
    reason: str = Field(..., description="Mandatory audit justification for recalculation")
    cohort_filters: dict[str, Any] | None = Field(None, description="Filters applied to recalculation cohort")


class KPIBenchmarkCreateRequest(BaseModel):
    peer_port: str = Field(..., description="Name of peer port (e.g. Port of Rotterdam)")
    benchmark_value: float = Field(..., description="Numerical benchmark value")
    source: str | None = Field(None, description="Source citation (leave empty if peer data absent)")
    period: str | None = Field(None, description="Period of benchmark (leave empty if peer data absent)")
    notes: str | None = Field(None, description="Contextual notes on methodology")


class PrimarySwapRequest(BaseModel):
    make_primary: bool = Field(True, description="Whether to designate this KPI as primary")


def _service_line_rows(
    db: Session,
    tenant_id: str,
    service_type: str | None = None,
    movement_type: str | None = None,
    vessel_type: str | None = None,
    cargo_type: str | None = None,
) -> list[tuple[ServiceRequest, ServiceAssignment, ServiceExecution, VesselCall]]:
    """Return source records for the governed Service Type performance view."""
    stmt = (
        select(ServiceRequest, ServiceAssignment, ServiceExecution, VesselCall)
        .join(ServiceAssignment, ServiceAssignment.service_request_id == ServiceRequest.id)
        .join(ServiceExecution, ServiceExecution.service_assignment_id == ServiceAssignment.id)
        .join(VesselCall, VesselCall.id == ServiceRequest.vessel_call_id)
        .where(VesselCall.is_merged.is_(False))
        .order_by(
            ServiceRequest.service_type.asc(),
            ServiceRequest.movement_type.asc(),
            ServiceAssignment.scheduled_time.asc(),
        )
    )
    if tenant_id != "*":
        stmt = stmt.where(VesselCall.tenant_id == tenant_id)
    if service_type:
        stmt = stmt.where(ServiceRequest.service_type == service_type)
    if movement_type:
        stmt = stmt.where(ServiceRequest.movement_type == movement_type)
    if vessel_type:
        stmt = stmt.where(VesselCall.vessel_type == vessel_type)
    if cargo_type:
        stmt = stmt.where(VesselCall.cargo_type == cargo_type)
    return db.execute(stmt).all()


def _resolve_tenant(principal: UserPrincipal, explicit_tenant: str | None = None) -> str:
    if explicit_tenant:
        return explicit_tenant
    if principal.data_scope.tenant_id in ("*", "tenant-synthetic-01"):
        return "synthetic-tenant"
    return principal.data_scope.tenant_id


# ──────────────────────────────────────────────────────────────────────────────
# Registry & Catalogue Endpoints
# ──────────────────────────────────────────────────────────────────────────────


@router.get("")
def list_kpis(
    category: str | None = Query(None, description="Filter by KPI category"),
    status: str | None = Query(None, description="COMPUTED | NO_SOURCE_DATA"),
    is_primary: bool | None = Query(None, description="Filter by primary vs alias"),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "kpi")),
):
    """Lists all 55 governed KPIs in the registry with metadata and status."""
    ensure_kpi_registry(db)
    stmt = select(KPI).where(KPI.code.isnot(None), KPI.is_active.is_(True)).order_by(KPI.kpi_number.asc())

    if category:
        stmt = stmt.where(KPI.category == category)
    if status:
        stmt = stmt.where(KPI.availability_status == status)
    if is_primary is not None:
        stmt = stmt.where(KPI.is_primary == is_primary)

    kpis = db.execute(stmt).scalars().all()
    return [
        {
            "id": str(k.id),
            "kpi_number": k.kpi_number,
            "code": k.code,
            "name": k.name,
            "category": k.category,
            "description": k.description,
            "formula": k.formula,
            "numerator": k.numerator,
            "denominator": k.denominator,
            "unit": k.unit,
            "aggregation_method": k.aggregation_method,
            "target": k.target,
            "target_direction": k.target_direction,
            "thresholds": k.thresholds,
            "is_primary": k.is_primary,
            "alias_of_id": str(k.alias_of_id) if k.alias_of_id else None,
            "availability_status": k.availability_status,
            "required_source_systems": k.required_source_systems or [],
            "owner": k.owner,
        }
        for k in kpis
    ]


@router.get("/scorecard")
def get_scorecard(
    tenant_id: str | None = Query(None),
    include_aliases: bool = Query(False, description="Whether to include duplicate alias concepts"),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "kpi")),
):
    """Returns the governed executive scorecard covering all KPIs with Green/Amber/Red banding.

    Prevents double-counting by excluding aliases unless explicitly requested.
    """
    target_tenant = _resolve_tenant(principal, tenant_id)
    engine = KPIEngine(db, tenant_id=target_tenant)

    # Scorecards are read far more often than they are recalculated.  The ingestion
    # pipeline persists the governed ALL-grain result for every KPI, so reuse that
    # complete snapshot instead of running all 55 formulas (and their canonical
    # data loads) on every page request.  Fall back to the engine when a complete
    # snapshot is not available or predates the active committed batch.
    kpi_map = engine.ensure_registry()
    snapshot_filter = (
        KPIResult.period_start.is_(None),
        KPIResult.period_end.is_(None),
        KPIResult.grain == "ALL",
        KPIResult.cohort_key == "all",
        # SQLAlchemy's JSON column stores a Python None as JSON `null` by
        # default, not necessarily SQL NULL.  Accept both representations so a
        # persisted unfiltered snapshot is actually reusable.
        or_(KPIResult.cohort_filters.is_(None), cast(KPIResult.cohort_filters, String) == "null"),
        KPIResult.is_recalculation.is_(False),
        KPIResult.kpi_id.in_([k.id for k in kpi_map.values()]),
    )
    # Fetch one persisted result per KPI in SQL.  Loading all historical
    # scorecard rows and de-duplicating in Python grows without bound after each
    # governed recalculation, which made otherwise cached scorecard reads slow.
    ranked_snapshot = (
        select(
            KPIResult.id.label("result_id"),
            func.row_number()
            .over(partition_by=KPIResult.kpi_id, order_by=KPIResult.calculated_at.desc())
            .label("rank"),
        )
        .where(*snapshot_filter)
        .subquery()
    )
    persisted_rows = (
        db.execute(
            select(KPIResult)
            .join(ranked_snapshot, KPIResult.id == ranked_snapshot.c.result_id)
            .where(ranked_snapshot.c.rank == 1)
        )
        .scalars()
        .all()
    )
    latest_by_kpi = {row.kpi_id: row for row in persisted_rows}

    active_batch = (
        db.execute(
            select(IngestionBatch)
            .where(
                IngestionBatch.tenant_id == target_tenant,
                IngestionBatch.is_active.is_(True),
                IngestionBatch.status == "COMMITTED",
            )
            .order_by(IngestionBatch.created_at.desc())
        )
        .scalars()
        .first()
    )
    snapshot_is_current = (
        bool(latest_by_kpi)
        and len(latest_by_kpi) == len(kpi_map)
        and (
            not active_batch
            or all(
                row.calculated_at is not None and row.calculated_at >= active_batch.created_at
                for row in latest_by_kpi.values()
            )
        )
    )

    if snapshot_is_current:
        results = {
            code: {
                "kpi_id": str(row.kpi_id),
                "code": code,
                "name": kpi_map[code].name,
                "value": row.value,
                "status": row.status,
                "band": row.band,
                "unit": kpi_map[code].unit,
                "target": row.target_value,
                "is_primary": kpi_map[code].is_primary,
            }
            for code, kpi in kpi_map.items()
            for row in [latest_by_kpi[kpi.id]]
        }
        calc_res = {
            "total_kpis": len(results),
            "computed": sum(1 for item in results.values() if item["status"] == "COMPUTED"),
            "no_source_data": sum(1 for item in results.values() if item["status"] == "NO_SOURCE_DATA"),
            "unavailable": sum(1 for item in results.values() if item["status"] == "UNAVAILABLE"),
            "results": results,
        }
    else:
        calc_res = engine.calculate_all_kpis()

    # Organize by category
    kpi_objs = (
        db.execute(select(KPI).where(KPI.is_active.is_(True)).order_by(KPI.kpi_number.asc())).scalars().all()
    )
    kpi_by_code = {k.code: k for k in kpi_objs}

    categories: dict[str, list[dict[str, Any]]] = {}
    for code, item in calc_res["results"].items():
        kpi = kpi_by_code.get(code)
        if not kpi:
            continue
        if not include_aliases and not kpi.is_primary:
            continue

        cat = kpi.category or "General"
        if cat not in categories:
            categories[cat] = []

        categories[cat].append(
            {
                "kpi_number": kpi.kpi_number,
                "code": kpi.code,
                "name": kpi.name,
                "value": item.get("value"),
                "status": item.get("status"),
                "band": item.get("band"),
                "unit": kpi.unit,
                "target": kpi.target,
                "target_direction": kpi.target_direction,
                "thresholds": kpi.thresholds,
                "is_primary": kpi.is_primary,
                "availability_status": kpi.availability_status,
                "required_source_systems": kpi.required_source_systems or [],
            }
        )

    return {
        "tenant_id": target_tenant,
        "total_kpis": calc_res["total_kpis"],
        "computed": calc_res["computed"],
        "no_source_data": calc_res["no_source_data"],
        "unavailable": calc_res["unavailable"],
        "include_aliases": include_aliases,
        "categories": categories,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Calculation & Recalculation Endpoints
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/calculate")
def calculate_kpis(
    body: KPICalculateRequest,
    tenant_id: str | None = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("recalculate", "kpi")),
):
    """Executes population-level KPI calculation with filters."""
    target_tenant = _resolve_tenant(principal, tenant_id)
    engine = KPIEngine(db, tenant_id=target_tenant)
    res = engine.calculate_all_kpis(
        cohort_filters=body.cohort_filters,
        period_start=body.period_start,
        period_end=body.period_end,
        grain=body.grain,
    )
    return res


@router.post("/{id_or_code}/recalculate")
def recalculate_kpi_endpoint(
    id_or_code: str,
    body: KPIRecalculateRequest,
    tenant_id: str | None = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("recalculate", "kpi")),
):
    """Explicit, permissioned, audited recalculation of a specific KPI.

    Produces an audit trail event in audit.audit_event.
    """
    target_tenant = _resolve_tenant(principal, tenant_id)
    engine = KPIEngine(db, tenant_id=target_tenant)

    kpi = None
    try:
        val_uuid = UUID(id_or_code)
        kpi = db.execute(select(KPI).where(KPI.id == val_uuid)).scalar_one_or_none()
    except ValueError:
        kpi = db.execute(select(KPI).where(KPI.code == id_or_code)).scalar_one_or_none()

    if not kpi:
        raise HTTPException(status_code=404, detail=f"KPI '{id_or_code}' not found.")

    res = engine.recalculate_kpi(
        kpi.code,
        actor_id=principal.user_id or principal.email or "api-user",
        actor_email=principal.email,
        actor_role=",".join(principal.roles) if principal.roles else "Analyst",
        reason=body.reason,
        cohort_filters=body.cohort_filters,
    )

    return {
        "status": "SUCCESS",
        "kpi_id": str(kpi.id),
        "code": kpi.code,
        "name": kpi.name,
        "value": res.value,
        "result_status": res.status,
        "band": res.band,
        "is_recalculation": res.is_recalculation,
        "calculated_at": res.calculated_at.isoformat() if res.calculated_at else None,
        "audit_notice": "Recalculation recorded in audit.audit_event.",
    }


# ──────────────────────────────────────────────────────────────────────────────
# KPI Detail, Results, Trends, and Benchmarks
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/statistics")
def list_governed_statistics(
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "kpi")),
):
    """Expose persisted governed percentile aggregates in the KPI experience.

    These are produced by AnalyticsEngine/Polars during the ingestion pipeline; this
    route intentionally never recalculates a percentile in a second implementation.
    """
    rows = db.execute(
        select(StatisticalAggregate, LeadTimeDefinition)
        .join(LeadTimeDefinition, LeadTimeDefinition.id == StatisticalAggregate.definition_id)
        .where(StatisticalAggregate.cohort_key == "all")
        .order_by(LeadTimeDefinition.name.asc())
    ).all()
    return {
        "percentile_method": "linear_interpolation",
        "items": [
            {
                "definition_id": str(definition.id),
                "name": definition.name,
                "unit": definition.unit,
                "observation_count": aggregate.observation_count,
                "missing_count": aggregate.missing_count,
                "p75": aggregate.p75_hours,
                "p90": aggregate.p90_hours,
                "small_sample_warning": aggregate.small_sample_warning,
                "status": "UNAVAILABLE" if not aggregate.observation_count else "AVAILABLE",
                "traceability": {
                    "formula_version": aggregate.formula_version,
                    "filters_applied": aggregate.cohort_filters or {},
                    "quarantine_excluded": aggregate.quarantine_excluded,
                    "percentile_method": aggregate.percentile_method,
                    "outlier_vcns": aggregate.outlier_vcns or [],
                    "calculated_at": aggregate.calculated_at.isoformat() if aggregate.calculated_at else None,
                },
            }
            for aggregate, definition in rows
        ],
    }


@router.get("/service-lines")
def get_service_line_kpis(
    service_type: str | None = Query(None),
    movement_type: str | None = Query(None),
    vessel_type: str | None = Query(None),
    cargo_type: str | None = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "kpi")),
):
    """Service Type performance view, using only ServiceRequest/Assignment/Execution data.

    The requested term "Service Line" has no governed source field.  The data model's
    actual equivalent is ServiceRequest.service_type, so each row reports the mean
    scheduled-to-served execution delay for one real service type/movement cohort.
    """
    tenant_id = _resolve_tenant(principal)
    rows = _service_line_rows(db, tenant_id, service_type, movement_type, vessel_type, cargo_type)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for request, assignment, execution, vessel_call in rows:
        key = (request.service_type, request.movement_type or "Unspecified")
        group = groups.setdefault(key, {"delays": [], "missing_count": 0, "record_ids": [], "vessel_call_ids": []})
        group["record_ids"].extend([str(request.id), str(assignment.id), str(execution.id)])
        group["vessel_call_ids"].append(str(vessel_call.id))
        if assignment.scheduled_time is None or execution.served_time is None:
            group["missing_count"] += 1
            continue
        group["delays"].append((execution.served_time - assignment.scheduled_time).total_seconds() / 3600.0)

    items = []
    for (line, movement), group in sorted(groups.items()):
        delays = group["delays"]
        count = len(delays)
        value = round(sum(delays) / count, 6) if count else None
        items.append(
            {
                "service_line": line,
                "movement_type": movement,
                "value": value,
                "unit": "hours",
                "status": "COMPUTED" if count else "UNAVAILABLE",
                "unavailable_reason": None
                if count
                else "Scheduled_Time and Served_Time are required for execution delay.",
                "numerator": round(sum(delays), 6) if count else None,
                "denominator": count if count else None,
                "observation_count": count,
                "missing_count": group["missing_count"],
                "formula": "mean(Served_Time − Scheduled_Time)",
                "aggregation_method": "arithmetic mean within service type and movement cohort",
                "source_fields": [
                    "ServiceRequest.service_type",
                    "ServiceRequest.movement_type",
                    "ServiceAssignment.scheduled_time",
                    "ServiceExecution.served_time",
                ],
                "exclusions": ["merged vessel calls", "records with missing scheduled or served time"],
                "filters_applied": {
                    k: v
                    for k, v in {
                        "service_type": service_type,
                        "movement_type": movement_type,
                        "vessel_type": vessel_type,
                        "cargo_type": cargo_type,
                    }.items()
                    if v
                },
                "source_record_ids": group["record_ids"],
                "vessel_call_ids": sorted(set(group["vessel_call_ids"])),
            }
        )
    return {
        "interpretation": "Service Line is represented by the source-backed Service Type dimension; Shipping Line is a separate vessel-call dimension.",
        "items": items,
    }


@router.get("/service-lines/records")
def get_service_line_records(
    service_type: str = Query(...),
    movement_type: str | None = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "kpi")),
):
    """Drill through a Service Type KPI cohort to its underlying execution records."""
    tenant_id = _resolve_tenant(principal)
    rows = _service_line_rows(db, tenant_id, service_type, movement_type)
    return {
        "service_type": service_type,
        "movement_type": movement_type,
        "items": [
            {
                "vessel_call_id": str(vessel.id),
                "vcn": vessel.vcn,
                "vessel_name": vessel.vessel_name,
                "service_request_id": str(request.id),
                "service_assignment_id": str(assignment.id),
                "service_execution_id": str(execution.id),
                "scheduled_time": assignment.scheduled_time.isoformat() if assignment.scheduled_time else None,
                "served_time": execution.served_time.isoformat() if execution.served_time else None,
                "execution_delay_hours": round(
                    (execution.served_time - assignment.scheduled_time).total_seconds() / 3600.0, 6
                )
                if assignment.scheduled_time and execution.served_time
                else None,
                "status": "AVAILABLE" if assignment.scheduled_time and execution.served_time else "UNAVAILABLE",
            }
            for request, assignment, execution, vessel in rows
        ],
    }


@router.get("/benchmarks")
def list_benchmarks(
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "kpi")),
):
    """Lists peer benchmarks across all KPIs (records absent peer data without fabricating numbers)."""
    service = KPIBenchmarkService(db)
    return service.list_all_benchmarks()


@router.post("/benchmarks")
def create_benchmark(
    body: KPIBenchmarkCreateRequest,
    kpi_id_or_code: str = Query(..., description="Target KPI ID or Code"),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("configure", "kpi")),
):
    """Admin endpoint to create a peer port benchmark."""
    service = KPIBenchmarkService(db)
    bm = service.create_benchmark(
        kpi_code_or_id=kpi_id_or_code,
        peer_port=body.peer_port,
        benchmark_value=body.benchmark_value,
        source=body.source,
        period=body.period,
        notes=body.notes,
        created_by=principal.user_id or principal.email or "admin",
    )
    return {
        "id": str(bm.id),
        "peer_port": bm.peer_port,
        "benchmark_value": bm.benchmark_value,
        "source": bm.source,
        "period": bm.period,
        "notes": bm.notes,
    }


@router.get("/{id_or_code}")
def get_kpi_detail(
    id_or_code: str,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "kpi")),
):
    """Returns details, formula, thresholds, formula versions, and primary/alias linkage for a KPI."""
    kpi = None
    try:
        val_uuid = UUID(id_or_code)
        kpi = db.execute(select(KPI).where(KPI.id == val_uuid)).scalar_one_or_none()
    except ValueError:
        kpi = db.execute(select(KPI).where(KPI.code == id_or_code)).scalar_one_or_none()

    if not kpi:
        raise HTTPException(status_code=404, detail=f"KPI '{id_or_code}' not found.")

    formula_versions = db.execute(select(KPIFormulaVersion).where(KPIFormulaVersion.kpi_id == kpi.id)).scalars().all()

    latest_result = (
        db.execute(select(KPIResult).where(KPIResult.kpi_id == kpi.id).order_by(desc(KPIResult.calculated_at)))
        .scalars()
        .first()
    )

    return {
        "id": str(kpi.id),
        "kpi_number": kpi.kpi_number,
        "code": kpi.code,
        "name": kpi.name,
        "category": kpi.category,
        "description": kpi.description,
        "formula": kpi.formula,
        "numerator": kpi.numerator,
        "denominator": kpi.denominator,
        "unit": kpi.unit,
        "aggregation_method": kpi.aggregation_method,
        "eligible_population": kpi.eligible_population,
        "required_events": kpi.required_events,
        "required_fields": kpi.required_fields,
        "exclusions": kpi.exclusions,
        "target": kpi.target,
        "target_direction": kpi.target_direction,
        "thresholds": kpi.thresholds,
        "owner": kpi.owner,
        "is_primary": kpi.is_primary,
        "alias_of_id": str(kpi.alias_of_id) if kpi.alias_of_id else None,
        "availability_status": kpi.availability_status,
        "required_source_systems": kpi.required_source_systems,
        "formula_versions": [{"version": fv.version, "expression": fv.expression} for fv in formula_versions],
        "latest_result": {
            "value": latest_result.value if latest_result else None,
            "status": latest_result.status if latest_result else None,
            "band": latest_result.band if latest_result else None,
            "calculated_at": latest_result.calculated_at.isoformat()
            if latest_result and latest_result.calculated_at
            else None,
            "is_recalculation": latest_result.is_recalculation if latest_result else False,
            "data_quality_summary": latest_result.data_quality_summary if latest_result else None,
        }
        if latest_result
        else None,
    }


@router.get("/{id_or_code}/results")
def get_kpi_results(
    id_or_code: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "kpi")),
):
    """Returns chronological calculation results for a KPI."""
    kpi = None
    try:
        val_uuid = UUID(id_or_code)
        kpi = db.execute(select(KPI).where(KPI.id == val_uuid)).scalar_one_or_none()
    except ValueError:
        kpi = db.execute(select(KPI).where(KPI.code == id_or_code)).scalar_one_or_none()

    if not kpi:
        raise HTTPException(status_code=404, detail=f"KPI '{id_or_code}' not found.")

    results = (
        db.execute(
            select(KPIResult).where(KPIResult.kpi_id == kpi.id).order_by(desc(KPIResult.calculated_at)).limit(limit)
        )
        .scalars()
        .all()
    )

    return [
        {
            "id": str(r.id),
            "value": r.value,
            "status": r.status,
            "band": r.band,
            "numerator_value": r.numerator_value,
            "denominator_value": r.denominator_value,
            "target_value": r.target_value,
            "unavailable_reason": r.unavailable_reason,
            "is_recalculation": r.is_recalculation,
            "calculated_at": r.calculated_at.isoformat() if r.calculated_at else None,
            "cohort_filters": r.cohort_filters,
            "data_quality_summary": r.data_quality_summary,
        }
        for r in results
    ]


@router.get("/{id_or_code}/trends")
def get_kpi_trends(
    id_or_code: str,
    grain: str = Query("MONTHLY", description="DAILY | WEEKLY | MONTHLY | QUARTERLY | ANNUAL"),
    periods: int = Query(6, ge=2, le=24),
    tenant_id: str | None = Query(None),
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "kpi")),
):
    """Calculates trends, baseline rolling average, and direction for a KPI."""
    target_tenant = _resolve_tenant(principal, tenant_id)
    engine = KPIEngine(db, tenant_id=target_tenant)

    kpi = None
    try:
        val_uuid = UUID(id_or_code)
        kpi = db.execute(select(KPI).where(KPI.id == val_uuid)).scalar_one_or_none()
    except ValueError:
        kpi = db.execute(select(KPI).where(KPI.code == id_or_code)).scalar_one_or_none()

    if not kpi:
        raise HTTPException(status_code=404, detail=f"KPI '{id_or_code}' not found.")

    return engine.get_trends(kpi.code, grain=grain, periods=periods)


@router.get("/{id_or_code}/benchmark")
def get_kpi_benchmark(
    id_or_code: str,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("view", "kpi")),
):
    """Returns peer port benchmark for a KPI or explicitly returns absent status."""
    service = KPIBenchmarkService(db)
    return service.get_benchmarks_for_kpi(id_or_code)


@router.put("/{id_or_code}/primary")
def swap_kpi_primary_designation(
    id_or_code: str,
    body: PrimarySwapRequest,
    db: Session = Depends(get_db),
    principal: UserPrincipal = Depends(require("configure", "kpi")),
):
    """Admin operation to designate a KPI as primary and make its counterpart the alias."""
    kpi = None
    try:
        val_uuid = UUID(id_or_code)
        kpi = db.execute(select(KPI).where(KPI.id == val_uuid)).scalar_one_or_none()
    except ValueError:
        kpi = db.execute(select(KPI).where(KPI.code == id_or_code)).scalar_one_or_none()

    if not kpi:
        raise HTTPException(status_code=404, detail=f"KPI '{id_or_code}' not found.")

    if not kpi.alias_of_id:
        # Check if another KPI has this as alias
        counterpart = db.execute(select(KPI).where(KPI.alias_of_id == kpi.id)).scalar_one_or_none()
        if not counterpart:
            raise HTTPException(status_code=400, detail="This KPI does not belong to a primary/alias pair.")
        # kpi is already primary; counterpart is alias
        if not body.make_primary:
            kpi.is_primary = False
            kpi.alias_of_id = counterpart.id
            counterpart.is_primary = True
            counterpart.alias_of_id = None
            db.commit()
    else:
        counterpart = db.execute(select(KPI).where(KPI.id == kpi.alias_of_id)).scalar_one_or_none()
        if body.make_primary and counterpart:
            kpi.is_primary = True
            kpi.alias_of_id = None
            counterpart.is_primary = False
            counterpart.alias_of_id = kpi.id
            db.commit()

    return {
        "status": "SUCCESS",
        "code": kpi.code,
        "is_primary": kpi.is_primary,
        "counterpart_code": counterpart.code if counterpart else None,
        "notice": "Primary/alias relationship updated.",
    }
