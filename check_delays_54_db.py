from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import VesselCall, Delay

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

vc = db.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600054")).scalar_one_or_none()
if vc:
    delays = db.execute(select(Delay).where(Delay.vessel_call_id == vc.id)).scalars().all()
    print(f"Delays: {len(delays)}")
