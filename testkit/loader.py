"""Synthetic fixture ingestion and oracle loading for tests/harness only."""
from datetime import datetime
import polars as pl
from sqlalchemy import text
from testkit.models import DQCase, ExpectedOutput, ValidationSummary
from apps.api.services.ingestion.pipeline import IngestionPipeline
from apps.api.services.ingestion.synthetic import reset_tenant_dataset
from apps.api.core.config import settings

def load_testkit_oracles(db, file_path):
    sheets = pl.read_excel(file_path, sheet_id=0)
    rows=[]
    for row in sheets["ExpectedOutputs"].iter_rows(named=True):
        for column,value in row.items():
            if column in ("VCN","Vessel_Name") or value is None: continue
            if column == "Expected_Turnaround_Hours_ATA_to_ATD" and isinstance(value, datetime):
                serial=(value-datetime(1899,12,30)).total_seconds()/86400; value=serial if serial>60 else serial-1
            try: rows.append(ExpectedOutput(vcn=row.get("VCN"),metric_name=column,expected_value=float(value)))
            except (TypeError,ValueError): pass
    db.execute(text("TRUNCATE TABLE testkit.expected_output CASCADE")); db.add_all(rows)
    db.execute(text("TRUNCATE TABLE testkit.dq_case CASCADE")); db.add_all([DQCase(case_id=r.get("Case_ID",""),description=r.get("Description"),expected_outcome=r.get("Expected_Outcome","")) for r in sheets["DQ_Cases"].iter_rows(named=True)])
    if "ValidationSummary" in sheets:
        db.execute(text("TRUNCATE TABLE testkit.validation_summary CASCADE")); db.add_all([ValidationSummary(metric_name=str(r.get("Validation Metric") or ""),expected_value=str(r.get("Expected Value") or ""),interpretation=str(r.get("Interpretation") or "")) for r in sheets["ValidationSummary"].iter_rows(named=True)])
    db.commit()

def load_synthetic_dataset(db, file_path):
    reset_tenant_dataset(db, settings.development_tenant_id)
    batch=IngestionPipeline(db,tenant_id=settings.development_tenant_id).process_file(file_path,"synthetic-workbook.xlsx",is_synthetic=True)
    load_testkit_oracles(db,file_path)
    return batch
