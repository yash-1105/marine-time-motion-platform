import sys
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import VesselCall, EventOccurrence
from apps.api.models.config import EventDefinition
from apps.api.services.quality.engine import DataQualityEngine

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

vc = db.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600045")).scalar_one_or_none()
if vc:
    dq_engine = DataQualityEngine(db)
    
    events = db.execute(select(EventOccurrence).where(EventOccurrence.vessel_call_id == vc.id)).scalars().all()
    event_map = {}
    for ev in events:
        name = dq_engine.event_defs.get(ev.event_definition_id)
        if name not in event_map: event_map[name] = []
        event_map[name].append(ev)
        
    anchor = event_map.get("ANCHORAGE_ARRIVAL")
    pob = event_map.get("PILOT_ON_BOARD_ARRIVAL")
    print("Anchor:", anchor)
    print("POB:", pob)
    if anchor and pob:
        print("Anchor UTC:", anchor[0].utc_value)
        print("POB UTC:", pob[0].utc_value)
        dur = (pob[0].utc_value - anchor[0].utc_value).total_seconds()
        print("Dur:", dur)
        if dur < 0:
            print("Should create DQ-006 issue!")
            dq_engine._create_issue("DQ-006", vc.id, f"EventOccurrence:{pob[0].id}", "CRITICAL")
            db.commit()
            print("Committed.")
