from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.quality import QualityIssue, QualityRule
from apps.api.models.canonical import VesselCall

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

issues = db.execute(select(QualityIssue)).scalars().all()
for i in issues:
    rule = db.execute(select(QualityRule).where(QualityRule.id == i.rule_id)).scalar_one()
    vc = db.execute(select(VesselCall).where(VesselCall.id == i.vessel_call_id)).scalar_one()
    print(f"VCN: {vc.vcn}, Rule: {rule.rule_id}")
