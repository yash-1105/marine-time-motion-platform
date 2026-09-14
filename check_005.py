from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import VesselCall, ServiceRequest, ServiceAssignment

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

vc = db.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600036")).scalar_one_or_none()
if vc:
    reqs = db.execute(select(ServiceRequest).where(ServiceRequest.vessel_call_id == vc.id)).scalars().all()
    for req in reqs:
        ass = db.execute(select(ServiceAssignment).where(ServiceAssignment.service_request_id == req.id)).scalar_one_or_none()
        print(f"Req: {req.service_type}, req_time: {req.requested_time}")
        if ass:
            print(f"  Assigned: {ass.scheduled_time}")
