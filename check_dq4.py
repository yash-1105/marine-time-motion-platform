from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import VesselCall, EventOccurrence
from apps.api.models.config import EventDefinition

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

vc = db.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600027")).scalar_one_or_none()
if vc:
    events = db.execute(select(EventOccurrence).where(EventOccurrence.vessel_call_id == vc.id)).scalars().all()
    eta, ata = None, None
    for e in events:
        ed = db.execute(select(EventDefinition).where(EventDefinition.id == e.event_definition_id)).scalar_one()
        if ed.name == "ETA": eta = e.utc_value
        if ed.name == "ATA": ata = e.utc_value
    print(f"ETA: {eta}, ATA: {ata}")
