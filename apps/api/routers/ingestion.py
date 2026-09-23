import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc, select, text
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.auth.tenant import resolve_principal_tenant
from apps.api.core.config import settings
from apps.api.core.database import get_db
from apps.api.models.ingestion import IngestionBatch, IngestionFile
from apps.api.services.ingestion.pipeline import IngestionPipeline
from apps.api.services.ingestion.synthetic import reset_tenant_dataset
from apps.api.services.pipeline_runner import run_full_analytics_pipeline
from apps.worker.main import process_ingestion_analytics_task

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _resolve_tenant(principal) -> str:
    return resolve_principal_tenant(principal)


def _file_result(manifest: IngestionFile) -> dict:
    """Serialize the persisted per-file handling result consistently."""
    return {
        "filename": manifest.original_filename,
        "checksum": manifest.file_checksum,
        "byte_size": manifest.byte_size,
        "parse_status": manifest.parse_status,
        "validation_status": manifest.validation_status,
        "error_message": manifest.error_message,
    }


@router.post("/upload", status_code=202)
def upload_file(
    background_tasks: BackgroundTasks,
    # Backwards-compatible singular field for existing clients.
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    principal=Depends(require("create", "vessel_call")),
    files: list[UploadFile] | None = File(None),
):
    """Accept a governed 1–15 workbook dataset group and queue atomic processing."""
    tenant_id = _resolve_tenant(principal)
    # Direct service tests call this function without FastAPI dependency
    # resolution, in which case the default is a `File` marker rather than a
    # Python list. Requests received through FastAPI always provide a list.
    uploads = files if isinstance(files, list) else ([] if file is None else [file])
    if not 1 <= len(uploads) <= 15:
        raise HTTPException(status_code=400, detail="Upload between 1 and 15 Excel workbooks per dataset group")
    os.makedirs("/tmp/uploads", exist_ok=True)
    temp_files: list[tuple[str, str]] = []
    try:
        for upload in uploads:
            safe_name = Path(upload.filename or "").name
            if not safe_name.lower().endswith(".xlsx"):
                raise HTTPException(status_code=415, detail="Only .xlsx workbooks are accepted for governed dataset groups")
            temp_path = f"/tmp/uploads/{uuid.uuid4()}_{safe_name}"
            temp_files.append((temp_path, safe_name))
            with open(temp_path, "wb") as buffer:
                written = 0
                while chunk := upload.file.read(1024 * 1024):
                    written += len(chunk)
                    if written > settings.upload_max_bytes:
                        raise HTTPException(status_code=413, detail=f"{safe_name} exceeds configured file size limit")
                    buffer.write(chunk)
            if open(temp_path, "rb").read(4) != b"PK\x03\x04":
                raise HTTPException(status_code=415, detail=f"{safe_name} is not a valid OOXML XLSX container")

        pipeline = IngestionPipeline(db, tenant_id=tenant_id)
        checksums = [pipeline.calculate_checksum(path) for path, _ in temp_files]
        checksum = __import__("hashlib").sha256("".join(sorted(checksums)).encode()).hexdigest()

        # Parse/map/validate before replacing an active dataset.  A malformed workbook
        # therefore cannot erase a currently usable dataset.
        batch_id = pipeline.process_files(temp_files, force_new=True, commit_canonical=False)

        # Do not delete the active canonical dataset in the request.  A prior worker
        # may still be calculating it; replacement is serialized by the worker so a
        # newer upload cannot race a running analytics transaction.
        new_batch = db.query(IngestionBatch).filter(IngestionBatch.batch_id == batch_id).first()
        if not new_batch:
            raise RuntimeError("Accepted ingestion batch could not be found")
        new_batch.status = "PROCESSING"
        new_batch.is_active = False
        db.commit()

        # Redis/Dramatiq is the durable execution boundary shared with the worker.
        process_ingestion_analytics_task.send(batch_id, tenant_id, checksum)

        manifests = (
            db.execute(
                select(IngestionFile)
                .where(IngestionFile.group_batch_id == batch_id)
                .order_by(IngestionFile.created_at, IngestionFile.id)
            )
            .scalars()
            .all()
        )
        skipped_count = sum(manifest.parse_status == "SKIPPED" for manifest in manifests)
        return {
            "batch_id": batch_id,
            "file_count": len(temp_files),
            "files": [name for _, name in temp_files],
            "file_results": [
                {
                    "filename": manifest.original_filename,
                    "byte_size": manifest.byte_size,
                    "parse_status": manifest.parse_status,
                    "validation_status": manifest.validation_status,
                    "message": manifest.error_message,
                }
                for manifest in manifests
            ],
            "governed_file_count": len(manifests) - skipped_count,
            "skipped_file_count": skipped_count,
            "status": "PROCESSING",
        }
    except HTTPException:
        if db is not None:
            db.rollback()
        raise
    except Exception as e:
        if db is not None:
            db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        for temp_path, _ in temp_files:
            if os.path.exists(temp_path):
                os.remove(temp_path)


@router.delete("/dataset")
def clear_dataset(db: Session = Depends(get_db), principal=Depends(require("create", "vessel_call"))):
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
def get_active_dataset(db: Session = Depends(get_db), principal=Depends(require("view", "vessel_call"))):
    """Returns the currently active dataset batch for the tenant, or reports that no dataset is loaded."""
    tenant_id = _resolve_tenant(principal)
    batch = (
        db.execute(
            select(IngestionBatch)
            .where(
                IngestionBatch.tenant_id == tenant_id,
                IngestionBatch.is_active.is_(True),
                IngestionBatch.status == "COMMITTED",
            )
            .order_by(desc(IngestionBatch.created_at))
        )
        .scalars()
        .first()
    )

    if not batch:
        return {"has_active_dataset": False, "batch": None}

    manifests = (
        db.execute(
            select(IngestionFile)
            .where(IngestionFile.group_batch_id == batch.batch_id)
            .order_by(IngestionFile.created_at, IngestionFile.id)
        )
        .scalars()
        .all()
    )

    return {
        "has_active_dataset": True,
        "batch": {
            "batch_id": batch.batch_id,
            "file_name": batch.file_name,
            "file_checksum": batch.file_checksum,
            "created_at": batch.created_at.isoformat() if batch.created_at else None,
            "status": batch.status,
            "is_active": batch.is_active,
            "file_count": len(manifests),
            "governed_file_count": sum(manifest.parse_status != "SKIPPED" for manifest in manifests),
            "skipped_file_count": sum(manifest.parse_status == "SKIPPED" for manifest in manifests),
            "files": [_file_result(manifest) for manifest in manifests],
        },
    }


@router.get("/batches")
def list_batches(db: Session = Depends(get_db), principal=Depends(require("view", "vessel_call"))):
    tenant_id = _resolve_tenant(principal)
    batches = (
        db.execute(
            select(IngestionBatch)
            .where(IngestionBatch.tenant_id == tenant_id)
            .order_by(desc(IngestionBatch.created_at))
        )
        .scalars()
        .all()
    )
    manifests: dict[str, list[IngestionFile]] = {}
    manifest_query = (
        select(IngestionFile)
        .where(IngestionFile.group_batch_id.in_([b.batch_id for b in batches]))
        .order_by(IngestionFile.created_at, IngestionFile.id)
    )
    for manifest in db.execute(manifest_query).scalars().all():
        manifests.setdefault(manifest.group_batch_id, []).append(manifest)
    return [
        {
            "batch_id": b.batch_id,
            "file_name": b.file_name,
            "status": b.status,
            "is_active": getattr(b, "is_active", True),
            "file_checksum": b.file_checksum,
            "created_at": b.created_at.isoformat() if b.created_at else None,
            "error_message": b.error_message,
            "file_count": len(manifests.get(b.batch_id, [])),
            "files": [_file_result(f) for f in manifests.get(b.batch_id, [])],
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

    active_batch = (
        db.execute(
            select(IngestionBatch)
            .where(
                IngestionBatch.tenant_id == tenant_id,
                IngestionBatch.is_active.is_(True),
            )
            .order_by(desc(IngestionBatch.created_at))
        )
        .scalars()
        .first()
    )

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
