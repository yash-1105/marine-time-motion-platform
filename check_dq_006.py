from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.quality import QualityIssue, QualityRule
from apps.api.models.canonical import VesselCall

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

vc = db.execute(select(VesselCall).where(VesselCall.vcn == "SYNVCN2600045")).scalar_one_or_none()
if vc:
    issues = db.execute(select(QualityIssue).where(QualityIssue.vessel_call_id == vc.id)).scalars().all()
    for i in issues:
        rule = db.execute(select(QualityRule).where(QualityRule.id == i.rule_id)).scalar_one()
        print(f"Issue: {rule.rule_id}")
