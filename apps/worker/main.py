import dramatiq
from dramatiq.brokers.redis import RedisBroker

redis_broker = RedisBroker(url="redis://localhost:6379/0")
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
