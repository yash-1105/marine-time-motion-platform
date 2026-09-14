from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import VesselCall, EventOccurrence
from apps.api.models.config import EventDefinition

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

vc = db.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600045")).scalar_one_or_none()
if vc:
    events = db.execute(select(EventOccurrence).where(EventOccurrence.vessel_call_id == vc.id)).scalars().all()
    for e in events:
        ed = db.execute(select(EventDefinition).where(EventDefinition.id == e.event_definition_id)).scalar_one()
        print(f"{ed.name}: {e.utc_value}")
