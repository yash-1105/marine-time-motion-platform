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

    Raw, staging, and canonical records are already committed by the upload request.
    Keeping the expensive analytics work here prevents a reverse proxy/browser request
    from timing out while retaining retry and failed-batch visibility.
    """
    from sqlalchemy import select

    from apps.api.core.database import SessionLocal
    from apps.api.models.ingestion import IngestionBatch
    from apps.api.services.pipeline_runner import run_full_analytics_pipeline

    db = SessionLocal()
    try:
        batch = db.execute(select(IngestionBatch).where(IngestionBatch.batch_id == batch_id)).scalar_one()
        if batch.status == "COMMITTED" and batch.is_active:
            return
        batch.status = "PROCESSING"
        batch.error_message = None
        db.commit()

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
        db.close()
