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
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.principal import UserPrincipal
from apps.api.core.database import get_db
from apps.api.models.analytics import KPI, KPIFormulaVersion, KPIResult
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
    stmt = select(KPI).where(KPI.code.isnot(None)).order_by(KPI.kpi_number.asc())

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
    persisted_rows = db.execute(
        select(KPIResult)
        .where(
            KPIResult.period_start.is_(None),
            KPIResult.period_end.is_(None),
            KPIResult.grain == "ALL",
            KPIResult.cohort_key == "all",
            KPIResult.cohort_filters.is_(None),
            KPIResult.is_recalculation == False,
            KPIResult.kpi_id.in_([k.id for k in kpi_map.values()]),
        )
        .order_by(KPIResult.calculated_at.desc())
    ).scalars().all()
    latest_by_kpi: dict[Any, KPIResult] = {}
    for row in persisted_rows:
        latest_by_kpi.setdefault(row.kpi_id, row)

    active_batch = db.execute(
        select(IngestionBatch)
        .where(IngestionBatch.tenant_id == target_tenant, IngestionBatch.is_active == True, IngestionBatch.status == "COMMITTED")
        .order_by(IngestionBatch.created_at.desc())
    ).scalars().first()
    snapshot_is_current = bool(latest_by_kpi) and len(latest_by_kpi) == len(kpi_map) and (
        not active_batch
        or all(row.calculated_at is not None and row.calculated_at >= active_batch.created_at for row in latest_by_kpi.values())
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
    kpi_objs = db.execute(select(KPI).order_by(KPI.kpi_number.asc())).scalars().all()
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

        categories[cat].append({
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
        })

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

    formula_versions = db.execute(
        select(KPIFormulaVersion).where(KPIFormulaVersion.kpi_id == kpi.id)
    ).scalars().all()

    latest_result = db.execute(
        select(KPIResult)
        .where(KPIResult.kpi_id == kpi.id)
        .order_by(desc(KPIResult.calculated_at))
    ).scalars().first()

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
        "formula_versions": [
            {"version": fv.version, "expression": fv.expression}
            for fv in formula_versions
        ],
        "latest_result": {
            "value": latest_result.value if latest_result else None,
            "status": latest_result.status if latest_result else None,
            "band": latest_result.band if latest_result else None,
            "calculated_at": latest_result.calculated_at.isoformat() if latest_result and latest_result.calculated_at else None,
            "is_recalculation": latest_result.is_recalculation if latest_result else False,
            "data_quality_summary": latest_result.data_quality_summary if latest_result else None,
        } if latest_result else None,
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

    results = db.execute(
        select(KPIResult)
        .where(KPIResult.kpi_id == kpi.id)
        .order_by(desc(KPIResult.calculated_at))
        .limit(limit)
    ).scalars().all()

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
