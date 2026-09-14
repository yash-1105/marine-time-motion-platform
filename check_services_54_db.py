from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import VesselCall, ServiceRequest, ServiceAssignment, ServiceExecution

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

vc = db.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600054")).scalar_one_or_none()
if vc:
    services = db.execute(select(ServiceRequest).where(ServiceRequest.vessel_call_id == vc.id)).scalars().all()
    print(f"ServiceRequests: {len(services)}")
    for req in services:
        ass = db.execute(select(ServiceAssignment).where(ServiceAssignment.service_request_id == req.id)).scalar_one_or_none()
        if ass:
            exe = db.execute(select(ServiceExecution).where(ServiceExecution.service_assignment_id == ass.id)).scalar_one_or_none()
            if exe:
                print(f"Scheduled: {ass.scheduled_time}, Served: {exe.served_time}")
                if ass.scheduled_time and exe.served_time:
                    delay_seconds = (exe.served_time - ass.scheduled_time).total_seconds()
                    print(f"Delay: {delay_seconds}")
