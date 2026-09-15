import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.core.database import get_db
from apps.api.models.ingestion import IngestionBatch
from apps.api.services.ingestion.pipeline import IngestionPipeline
from apps.api.services.ingestion.synthetic import reset_tenant_dataset
from apps.api.services.pipeline_runner import run_full_analytics_pipeline
from apps.api.core.config import settings

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _resolve_tenant(principal) -> str:
    if principal.data_scope.tenant_id in ("*", "tenant-synthetic-01"):
        return "synthetic-tenant"
    return principal.data_scope.tenant_id


@router.post("/upload")
def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal = Depends(require("create", "vessel_call"))
):
    """Uploads a vessel operations workbook, executes ingestion, runs analytical engines once,

    and persists the calculated executive snapshot into PostgreSQL.
    """
    tenant_id = _resolve_tenant(principal)
    safe_name = Path(file.filename or "").name
    if not safe_name.lower().endswith((".xlsx", ".csv")):
        raise HTTPException(status_code=415, detail="Only .xlsx and .csv uploads are accepted")
    os.makedirs("/tmp/uploads", exist_ok=True)
    temp_path = f"/tmp/uploads/{uuid.uuid4()}_{safe_name}"
    with open(temp_path, "wb") as buffer:
        written = 0
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > settings.upload_max_bytes:
                buffer.close(); os.remove(temp_path)
                raise HTTPException(status_code=413, detail="Upload exceeds configured size limit")
            buffer.write(chunk)
    if safe_name.lower().endswith(".xlsx") and open(temp_path, "rb").read(4) != b"PK\x03\x04":
        os.remove(temp_path)
        raise HTTPException(status_code=415, detail="XLSX upload is not a valid OOXML container")

    try:
        pipeline = IngestionPipeline(db, tenant_id=tenant_id)
        checksum = pipeline.calculate_checksum(temp_path)

        # 1. Reset previous active dataset records for tenant (Dataset Replacement)
        reset_tenant_dataset(db, tenant_id, keep_batches=True)

        # 2. Ingest workbook to canonical schema
        batch_id = pipeline.process_file(temp_path, file.filename, force_new=True)

        # 3. Supersede older batches and mark new batch as active
        db.query(IngestionBatch).filter(
            IngestionBatch.tenant_id == tenant_id,
            IngestionBatch.batch_id != batch_id,
        ).update({"is_active": False, "status": "SUPERSEDED"})

        new_batch = db.query(IngestionBatch).filter(IngestionBatch.batch_id == batch_id).first()
        if new_batch:
            new_batch.is_active = True
            db.commit()

        # 4. Run full analytical pipeline and persist executive dashboard snapshot
        run_full_analytics_pipeline(db, tenant_id=tenant_id, batch_id=batch_id, file_checksum=checksum)

        # Clean up temporary disk file
        if os.path.exists(temp_path):
            os.remove(temp_path)

        return {"batch_id": batch_id, "file_name": safe_name, "status": "COMMITTED"}
    except Exception as e:
        db.rollback()
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/dataset")
def clear_dataset(
    db: Session = Depends(get_db),
    principal = Depends(require("create", "vessel_call"))
):
    """Removes the tenant's currently loaded dataset (all ingested and derived

    data), returning it to a clean, no-dataset-loaded state.
    """
    tenant_id = _resolve_tenant(principal)
    try:
        reset_tenant_dataset(db, tenant_id)
        # Also remove persisted snapshots and batch records for tenant
        db.execute(text("DELETE FROM analytics.dashboard_snapshot WHERE tenant_id = :t"), {"t": tenant_id})
        db.execute(text("DELETE FROM raw.batch WHERE tenant_id = :t"), {"t": tenant_id})
        db.commit()
        return {"status": "CLEARED", "tenant_id": tenant_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active")
def get_active_dataset(
    db: Session = Depends(get_db),
    principal = Depends(require("view", "vessel_call"))
):
    """Returns the currently active dataset batch for the tenant, or reports that no dataset is loaded."""
    tenant_id = _resolve_tenant(principal)
    batch = db.execute(
        select(IngestionBatch)
        .where(
            IngestionBatch.tenant_id == tenant_id,
            IngestionBatch.is_active == True,
            IngestionBatch.status == "COMMITTED",
        )
        .order_by(desc(IngestionBatch.created_at))
    ).scalars().first()

    if not batch:
        return {"has_active_dataset": False, "batch": None}

    return {
        "has_active_dataset": True,
        "batch": {
            "batch_id": batch.batch_id,
            "file_name": batch.file_name,
            "file_checksum": batch.file_checksum,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "status": batch.status,
            "is_active": batch.is_active,
        },
    }


@router.get("/batches")
def list_batches(
    db: Session = Depends(get_db),
    principal = Depends(require("view", "vessel_call"))
):
    tenant_id = _resolve_tenant(principal)
    batches = db.execute(
        select(IngestionBatch)
        .where(IngestionBatch.tenant_id == tenant_id)
        .order_by(desc(IngestionBatch.created_at))
    ).scalars().all()
    return [
        {
            "batch_id": b.batch_id,
            "file_name": b.file_name,
            "status": b.status,
            "is_active": getattr(b, "is_active", True),
            "file_checksum": b.file_checksum,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "error_message": b.error_message,
        }
        for b in batches
    ]


@router.post("/reprocess")
def reprocess_active_dataset(
    db: Session = Depends(get_db),
    principal=Depends(require("administer", "tenant")),
):
    """Re-runs canonical commit and full analytics from existing staging records.

    Use this to recover from silent event-occurrence drops caused by missing EventDefinition
    records (e.g. after the event-definitions seed migration) without requiring a file re-upload.
    """
    from apps.api.services.ingestion.synthetic import reset_tenant_dataset

    tenant_id = _resolve_tenant(principal)

    active_batch = db.execute(
        select(IngestionBatch)
        .where(
            IngestionBatch.tenant_id == tenant_id,
            IngestionBatch.is_active == True,
        )
        .order_by(desc(IngestionBatch.created_at))
    ).scalars().first()

    if not active_batch:
        raise HTTPException(status_code=404, detail="No active dataset found for this tenant")

    batch_id = active_batch.batch_id
    checksum = active_batch.file_checksum

    try:
        # 1. Wipe canonical + derived data while keeping raw/staging records intact
        reset_tenant_dataset(db, tenant_id, keep_batches=True)

        # 2. Re-commit from existing staging records (auto-creates missing EventDefinition rows)
        pipeline = IngestionPipeline(db, tenant_id=tenant_id)
        pipeline._commit_to_canonical(active_batch)

        # 3. Re-mark batch as active and COMMITTED
        active_batch.is_active = True
        active_batch.status = "COMMITTED"
        db.commit()

        # 4. Re-run full analytics pipeline and persist snapshot
        run_full_analytics_pipeline(db, tenant_id=tenant_id, batch_id=batch_id, file_checksum=checksum)

        return {
            "status": "REPROCESSED",
            "batch_id": batch_id,
            "file_name": active_batch.file_name,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
