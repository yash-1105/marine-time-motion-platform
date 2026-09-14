import polars as pl
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import text
from apps.api.models.testkit import ExpectedOutput, DQCase

def load_testkit_oracles(db: Session, file_path: str):
    workbook = pl.read_excel(file_path, sheet_id=0)
    
    # 1. ExpectedOutputs
    df_expected = workbook["ExpectedOutputs"]
    records = []
    for row in df_expected.iter_rows(named=True):
        vcn = row.get("VCN")
        for col_name, val in row.items():
            if col_name in ["VCN", "Vessel_Name"]:
                continue
            
            # Decoder for Expected_Turnaround_Hours_ATA_to_ATD
            if col_name == "Expected_Turnaround_Hours_ATA_to_ATD" and val is not None:
                if isinstance(val, datetime):
                    # decode excel date formatted cell
                    # serial = (cell_datetime - datetime(1899,12,30)).total_seconds() / 86400
                    serial = (val - datetime(1899, 12, 30)).total_seconds() / 86400.0
                    hours = serial if serial > 60 else serial - 1
                    val = hours
                else:
                    try:
                        val = float(val)
                    except:
                        val = None
            elif val is not None:
                 try:
                     val = float(val)
                 except:
                     val = None
                     
            if val is not None:
                records.append(ExpectedOutput(
                    vcn=vcn,
                    metric_name=col_name,
                    expected_value=val
                ))
    
    db.execute(text("TRUNCATE TABLE testkit.expected_output CASCADE"))
    db.add_all(records)
    
    # 2. DQ_Cases
    df_dq = workbook["DQ_Cases"]
    dq_records = []
    for row in df_dq.iter_rows(named=True):
        dq_records.append(DQCase(
            case_id=row.get("Case_ID", ""),
            description=row.get("Description", ""),
            expected_outcome=row.get("Expected_Outcome", "")
        ))
    db.execute(text("TRUNCATE TABLE testkit.dq_case CASCADE"))
    db.add_all(dq_records)
    
    db.commit()


from .pipeline import IngestionPipeline

def load_synthetic_dataset(db: Session, file_path: str):
    # Reset synthetic tenant
    
    db.execute(text("DELETE FROM raw.record WHERE ingestion_batch_id IN (SELECT batch_id FROM raw.batch WHERE tenant_id = 'synthetic-tenant')"))
    db.execute(text("DELETE FROM staging.record WHERE ingestion_batch_id IN (SELECT batch_id FROM raw.batch WHERE tenant_id = 'synthetic-tenant')"))
    db.execute(text("DELETE FROM raw.batch WHERE tenant_id = 'synthetic-tenant'"))

    
    db.execute(text("DELETE FROM canonical.event_occurrence WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
    db.execute(text("DELETE FROM canonical.service_request WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
    db.execute(text("DELETE FROM canonical.delay WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
    db.execute(text("DELETE FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant'"))

    db.commit()
    
    pipeline = IngestionPipeline(db, tenant_id="synthetic-tenant")
    batch_id = pipeline.process_file(file_path, "Synthetic_Marine_Time_Motion_Test_Data.xlsx", is_synthetic=True)
    
    load_testkit_oracles(db, file_path)
    
    return batch_id

