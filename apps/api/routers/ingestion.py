import os
import shutil
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.auth.dependencies import require
from apps.api.core.database import get_db
from apps.api.models.ingestion import IngestionBatch
from apps.api.services.ingestion.pipeline import IngestionPipeline
from apps.api.services.ingestion.synthetic import load_synthetic_dataset

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
    # Save to temp disk as object storage substitute
    os.makedirs("/tmp/uploads", exist_ok=True)
    temp_path = f"/tmp/uploads/{uuid.uuid4()}_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    pipeline = IngestionPipeline(db, tenant_id=_resolve_tenant(principal))
    
    # Normally we would queue this using Dramatiq, but for synchronous return we do it here or via background task
    try:
        batch_id = pipeline.process_file(temp_path, file.filename)
        return {"batch_id": batch_id, "status": "PROCESSING"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/synthetic")
def load_synthetic(
    db: Session = Depends(get_db),
    principal = Depends(require("administer", "tenant"))
):
    try:
        batch_id = load_synthetic_dataset(db, "fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx")
        return {"batch_id": batch_id, "status": "COMPLETED"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        {"batch_id": b.batch_id, "file_name": b.file_name, "status": b.status, "error_message": b.error_message}
        for b in batches
    ]

