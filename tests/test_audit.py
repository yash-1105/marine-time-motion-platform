import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import InternalError
from sqlalchemy.orm import sessionmaker

from apps.api.main import settings
from apps.api.models import KPI, AuditEvent, Base


@pytest.fixture(scope="module")
def engine():
    return create_engine(settings.database_url)


@pytest.fixture(scope="module")
def session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def test_audit_append_only(session):
    # Add an event
    event = AuditEvent(entity_name="test", entity_id="123", action="CREATE", changes={})
    session.add(event)
    session.commit()

    # Try to update
    event.action = "UPDATE"
    with pytest.raises(InternalError) as exc:
        session.commit()
    assert "audit_event is append-only" in str(exc.value)
    session.rollback()

    # Try to delete
    with pytest.raises(InternalError) as exc:
        session.delete(event)
        session.commit()
    assert "audit_event is append-only" in str(exc.value)
    session.rollback()


def test_testkit_schema_exists(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'testkit'"))
        assert result.fetchone() is not None


def test_testkit_isolation():
    # Ensure no models in testkit schema except those explicitly in testkit module
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        schema = getattr(cls.__table__, "schema", None)
        if schema == "testkit":
            assert cls.__module__ == "testkit.models"


def test_kpi_count(session):
    kpis = session.query(KPI).all()
    assert len(kpis) >= 55
