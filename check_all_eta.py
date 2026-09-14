from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import VesselCall, EventOccurrence
from apps.api.models.config import EventDefinition

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

vcs = db.execute(select(VesselCall)).scalars().all()
for vc in vcs:
    events = db.execute(select(EventOccurrence).where(EventOccurrence.vessel_call_id == vc.id)).scalars().all()
    eta, ata = None, None
    for e in events:
        ed = db.execute(select(EventDefinition).where(EventDefinition.id == e.event_definition_id)).scalar_one()
        if ed.name == "ETA": eta = e.utc_value
        if ed.name == "ATA": ata = e.utc_value
    if eta and ata and eta > ata:
        print(f"VCN with ETA > ATA: {vc.vcn}, ETA: {eta}, ATA: {ata}")
