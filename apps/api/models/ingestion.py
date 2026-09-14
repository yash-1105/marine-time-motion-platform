from sqlalchemy import Column, String, Integer, JSON, Boolean
from .base import BaseModel

class RawRecord(BaseModel):
    __tablename__ = "record"
    __table_args__ = {"schema": "raw"}
    
    file_checksum = Column(String, nullable=False)
    worksheet_name = Column(String, nullable=False)
    row_number = Column(Integer, nullable=False)
    column_name = Column(String, nullable=False)
    original_value = Column(String, nullable=True)
    ingestion_batch_id = Column(String, nullable=False)
    source_record_id = Column(String, nullable=True)

class StagingRecord(BaseModel):
    __tablename__ = "record"
    __table_args__ = {"schema": "staging"}
    
    file_checksum = Column(String, nullable=False)
    worksheet_name = Column(String, nullable=False)
    row_number = Column(Integer, nullable=False)
    parsed_data = Column(JSON, nullable=False)
    errors = Column(JSON, nullable=True)
    ingestion_batch_id = Column(String, nullable=False)
    validation_status = Column(String, nullable=False, default="PENDING")
    source_record_id = Column(String, nullable=True)
    canonical_table = Column(String, nullable=False) # e.g., 'vessel_call', 'event_occurrence'

class IngestionBatch(BaseModel):
    __tablename__ = "batch"
    __table_args__ = {"schema": "raw"}
    
    batch_id = Column(String, nullable=False, unique=True)
    file_name = Column(String, nullable=False)
    file_checksum = Column(String, nullable=False)
    status = Column(String, nullable=False, default="UPLOADED") # UPLOADED, PARSED, MAPPED, VALIDATED, COMMITTED, FAILED
    error_message = Column(String, nullable=True)
    tenant_id = Column(String, nullable=False)
    is_synthetic = Column(Boolean, default=False)
