from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from apps.api.models.canonical import VesselCall
from apps.api.models.quality import QualityIssue, QualityRule
from apps.api.services.quality.engine import DataQualityEngine

engine = create_engine("postgresql://admin:password@localhost:5434/marine_platform")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

engine = DataQualityEngine(db)
engine.run_all()

# Check issues
issues = db.execute(select(QualityIssue, QualityRule).join(QualityRule)).all()
print(f"Total issues: {len(issues)}")

for issue, rule in issues:
    vc = db.execute(select(VesselCall).where(VesselCall.id == issue.vessel_call_id)).scalar_one_or_none()
    vcn = vc.vcn if vc else "Unknown"
    print(f"VCN: {vcn}, Rule: {rule.rule_id}, Severity: {rule.severity}")

# Validate specifically for the VCNs:
cases = {
    "SYNVCN2600018": "DQ-003",
    "SYNVCN2600027": "DQ-004",
    "SYNVCN2600036": "DQ-005",
    "SYNVCN2600045": "DQ-006",
    "SYNVCN2600054": "DQ-007"
}

for vcn, expected_rule in cases.items():
    found = False
    for issue, rule in issues:
        vc = db.execute(select(VesselCall).where(VesselCall.id == issue.vessel_call_id)).scalar_one_or_none()
        if vc and vc.vcn == vcn and rule.rule_id == expected_rule:
            found = True
            break
    print(f"Case {expected_rule} for {vcn}: {'PASS' if found else 'FAIL'}")

