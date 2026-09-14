from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import EventOccurrence, VesselCall

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

events = db.execute(select(EventOccurrence).where(EventOccurrence.utc_value == None)).scalars().all()
for e in events:
    vc = db.execute(select(VesselCall).where(VesselCall.id == e.vessel_call_id)).scalar_one()
    print(vc.vcn, e.id)
