from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from dateutil import parser
import pytz
from apps.api.models.ingestion import StagingRecord
from apps.api.models.canonical import ServiceRequest, ServiceAssignment, ServiceExecution, Delay, VesselCall

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def dt_parse(dt_str):
    if not dt_str: return None
    try:
        dt = parser.parse(dt_str)
        if dt.tzinfo is None:
            dt = pytz.timezone("Africa/Johannesburg").localize(dt)
        return dt.astimezone(pytz.utc)
    except:
        return None

def float_val(val_str):
    if not val_str: return None
    try: return float(val_str)
    except: return None

# We can query all staging records
vessels = {v.vcn: v.id for v in db.execute(select(VesselCall)).scalars().all()}

service_records = db.execute(select(StagingRecord).where(StagingRecord.canonical_table == 'service_request')).scalars().all()
for r in service_records:
    pd = r.parsed_data
    vcn = pd.get("VCN")
    vc_id = vessels.get(vcn)
    if not vc_id: continue
    
    # create ServiceRequest
    req = ServiceRequest(
        vessel_call_id=vc_id,
        service_type=pd.get("Service_Type", "Unknown"),
        requested_time=dt_parse(pd.get("Requested_Time"))
    )
    db.add(req)
    db.flush()
    
    # assignment
    ass = ServiceAssignment(
        service_request_id=req.id,
        scheduled_time=dt_parse(pd.get("Scheduled_Time")),
        assigned_resource_id=pd.get("Resource_Assigned"),
        resource_type=pd.get("Service_Type")
    )
    db.add(ass)
    db.flush()
    
    # execution
    exe = ServiceExecution(
        service_assignment_id=ass.id,
        served_time=dt_parse(pd.get("Served_Time")),
        execution_status=pd.get("Data_Status")
    )
    db.add(exe)

delay_records = db.execute(select(StagingRecord).where(StagingRecord.canonical_table == 'delay')).scalars().all()
for r in delay_records:
    pd = r.parsed_data
    vcn = pd.get("VCN")
    vc_id = vessels.get(vcn)
    if not vc_id: continue
    
    val = float_val(pd.get("Duration_Hours"))
    d = Delay(
        vessel_call_id=vc_id,
        movement_stage=pd.get("Movement", "Unknown"),
        total_duration_hours=val if val is not None else 0.0,
        is_early_service=False # we'll flag this properly in engine or here?
    )
    db.add(d)

db.commit()
print("Services and Delays added.")
