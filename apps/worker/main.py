import dramatiq
from dramatiq.brokers.redis import RedisBroker

from apps.api.core.config import settings

redis_broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(redis_broker)


@dramatiq.actor
def no_op_task():
    print("Worker is ready and running")


@dramatiq.actor(max_retries=3)
def generate_report_task(report_run_id: str, tenant_id: str):
    """Durable worker entrypoint used by the scheduler/manual Run Now integration."""
    from apps.api.core.database import SessionLocal
    from apps.api.services.reporting.service import ReportService

    db = SessionLocal()
    try:
        ReportService(db, tenant_id).generate(report_run_id)
    finally:
        db.close()


@dramatiq.actor(max_retries=3)
def process_ingestion_analytics_task(batch_id: str, tenant_id: str, file_checksum: str):
    """Durably complete downstream governed processing for an accepted upload.

    The worker owns destructive replacement, canonical commit, and analytics as one
    tenant-serialized operation.  This prevents a second upload from deleting rows
    while an earlier worker transaction is still calculating derived records.
    """
    from sqlalchemy import select, text

    from apps.api.core.database import SessionLocal
    from apps.api.models.ingestion import IngestionBatch
    from apps.api.services.ingestion.pipeline import IngestionPipeline
    from apps.api.services.ingestion.synthetic import reset_tenant_dataset
    from apps.api.services.pipeline_runner import run_full_analytics_pipeline

    db = SessionLocal()
    lock_key = f"ingestion:{tenant_id}"
    lock_acquired = False
    try:
        batch = db.execute(select(IngestionBatch).where(IngestionBatch.batch_id == batch_id)).scalar_one()
        if batch.status in {"SUPERSEDED", "FAILED"} or (batch.status == "COMMITTED" and batch.is_active):
            return

        # PostgreSQL advisory locks are session scoped and make replacement safe even
        # when multiple Dramatiq processes receive uploads for the same tenant.
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_lock(hashtext(:key))"), {"key": lock_key})
            lock_acquired = True

        db.expire_all()
        batch = db.execute(select(IngestionBatch).where(IngestionBatch.batch_id == batch_id)).scalar_one()
        newest_batch_id = db.execute(
            select(IngestionBatch.batch_id)
            .where(IngestionBatch.tenant_id == tenant_id)
            .order_by(IngestionBatch.created_at.desc())
            .limit(1)
        ).scalar_one()
        if batch.status in {"SUPERSEDED", "FAILED"} or newest_batch_id != batch_id:
            batch.status = "SUPERSEDED"
            batch.is_active = False
            db.commit()
            return

        batch.status = "PROCESSING"
        batch.error_message = None
        db.commit()

        # All writes that replace the active dataset occur while holding the same
        # tenant lock.  Parsed/staging rows remain batch-scoped for lineage.
        reset_tenant_dataset(db, tenant_id, keep_batches=True)
        batch = db.execute(select(IngestionBatch).where(IngestionBatch.batch_id == batch_id)).scalar_one()
        IngestionPipeline(db, tenant_id=tenant_id)._commit_to_canonical(batch, completion_status="PROCESSING")
        run_full_analytics_pipeline(db, tenant_id=tenant_id, batch_id=batch_id, file_checksum=file_checksum)

        batch = db.execute(select(IngestionBatch).where(IngestionBatch.batch_id == batch_id)).scalar_one()
        db.query(IngestionBatch).filter(
            IngestionBatch.tenant_id == tenant_id,
            IngestionBatch.batch_id != batch_id,
        ).update({"is_active": False, "status": "SUPERSEDED"})
        batch.status = "COMMITTED"
        batch.is_active = True
        batch.error_message = None
        db.commit()
    except Exception as exc:
        db.rollback()
        batch = db.execute(select(IngestionBatch).where(IngestionBatch.batch_id == batch_id)).scalar_one_or_none()
        if batch:
            batch.status = "FAILED"
            batch.is_active = False
            batch.error_message = str(exc)
            db.commit()
        raise
    finally:
        if lock_acquired:
            try:
                db.execute(text("SELECT pg_advisory_unlock(hashtext(:key))"), {"key": lock_key})
                db.commit()
            except Exception:
                db.rollback()
        db.close()
