import hashlib
import uuid

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.canonical import (
    EventOccurrence,
    VesselCall,
)
from apps.api.models.config import EventDefinition
from apps.api.models.ingestion import IngestionBatch, RawRecord, StagingRecord


class IngestionPipeline:
    def __init__(self, db: Session, tenant_id: str = "default-tenant"):
        self.db = db
        self.tenant_id = tenant_id

    def calculate_checksum(self, file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def process_file(self, file_path: str, filename: str, is_synthetic: bool = False, dry_run: bool = False) -> str:
        checksum = self.calculate_checksum(file_path)
        batch_id = str(uuid.uuid4())
        
        existing = self.db.execute(
            select(IngestionBatch).where(IngestionBatch.file_checksum == checksum)
        ).scalar_one_or_none()
        
        if existing and existing.status == "COMMITTED":
            return str(existing.batch_id)

        batch = IngestionBatch(
            batch_id=batch_id,
            file_name=filename,
            file_checksum=checksum,
            status="UPLOADED",
            tenant_id=self.tenant_id,
            is_synthetic=is_synthetic
        )
        self.db.add(batch)
        self.db.commit()

        try:
            self._parse_to_raw(file_path, batch)
            self._map_to_staging(batch)
            self._validate_staging(batch)
            
            if dry_run:
                try:
                    self.db.begin_nested()
                    self._commit_to_canonical(batch)
                    self.db.rollback()
                except Exception:
                    self.db.rollback()
                # Status for dry run
                batch.status = "DRY_RUN_COMPLETED"
                self.db.commit()
            else:
                self._commit_to_canonical(batch)
                
            return str(batch.batch_id)
        except Exception as e:
            batch.status = "FAILED"
            batch.error_message = str(e)
            self.db.commit()
            raise e

    def _parse_to_raw(self, file_path: str, batch: IngestionBatch):
        workbook = pl.read_excel(file_path, sheet_id=0)
        target_sheets = ["VesselCalls", "Events", "Services", "CargoOps", "Delays"]
        
        for sheet_name, df in workbook.items():
            if sheet_name not in target_sheets:
                continue
                
            records = []
            for row_idx, row in enumerate(df.iter_rows(named=True), start=2):
                for col_name, val in row.items():
                    val_str = "" if val is None else str(val)
                    record = RawRecord(
                        file_checksum=batch.file_checksum,
                        worksheet_name=sheet_name,
                        row_number=row_idx,
                        column_name=col_name,
                        original_value=val_str,
                        ingestion_batch_id=batch.batch_id,
                        source_record_id=row.get("VCN") or row.get("Source_Call_ID") or ""
                    )
                    records.append(record)
                    
                if len(records) > 5000:
                    self.db.add_all(records)
                    self.db.commit()
                    records = []
                    
            if records:
                self.db.add_all(records)
                self.db.commit()
                
        batch.status = "PARSED"
        self.db.commit()

    def _map_to_staging(self, batch: IngestionBatch):
        sheets = self.db.execute(
            select(RawRecord.worksheet_name).where(RawRecord.ingestion_batch_id == batch.batch_id).distinct()
        ).scalars().all()
        
        for sheet in sheets:
            raw_records = self.db.execute(
                select(RawRecord).where(RawRecord.ingestion_batch_id == batch.batch_id, RawRecord.worksheet_name == sheet)
            ).scalars().all()
            
            row_map = {}
            for r in raw_records:
                if r.row_number not in row_map:
                    row_map[r.row_number] = {"data": {}, "source_record_id": r.source_record_id}
                if isinstance(row_map[r.row_number], dict) and isinstance(row_map[r.row_number].get("data"), dict):
                    row_map[r.row_number]["data"][str(r.column_name)] = r.original_value  # type: ignore
                
            staging_records = []
            for row_idx, row_info in row_map.items():
                parsed_data = row_info["data"]
                canonical_table = ""
                if sheet == "VesselCalls":
                    canonical_table = "vessel_call"
                elif sheet == "Events":
                    canonical_table = "event_occurrence"
                elif sheet == "Services":
                    canonical_table = "service_request"
                elif sheet == "CargoOps":
                    canonical_table = "cargo_ops"
                elif sheet == "Delays":
                    canonical_table = "delay"
                
                staging_record = StagingRecord(
                    file_checksum=batch.file_checksum,
                    worksheet_name=sheet,
                    row_number=row_idx,
                    parsed_data=parsed_data,
                    errors={},
                    ingestion_batch_id=batch.batch_id,
                    validation_status="PENDING",
                    source_record_id=row_info["source_record_id"],
                    canonical_table=canonical_table
                )
                staging_records.append(staging_record)
                
            self.db.add_all(staging_records)
            self.db.commit()
            
        batch.status = "MAPPED"
        self.db.commit()

    def _validate_staging(self, batch: IngestionBatch):
        pass

    def _commit_to_canonical(self, batch: IngestionBatch):
        vessel_records = self.db.execute(
            select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch.batch_id, StagingRecord.canonical_table == "vessel_call")
        ).scalars().all()
        
        vcn_to_id = {}
        vessels_to_add = []
        for r in vessel_records:
            pd = r.parsed_data
            vcn = pd.get("VCN")
            
            def get_val(pd_dict, key):
                val = pd_dict.get(key)
                return val if val != "" else None
                
            def get_float(pd_dict, key):
                val = get_val(pd_dict, key)
                if val:
                    try:
                        return float(val)
                    except Exception:
                        return None
                return None
                
            vc = VesselCall(
                tenant_id=batch.tenant_id,
                vessel_name=get_val(pd, "Vessel_Name") or "UNKNOWN",
                imo_number=get_val(pd, "IMO_Number"),
                vcn=vcn,
                vessel_type=get_val(pd, "Vessel_Type"),
                vessel_size_teu=get_float(pd, "Vessel_Size_TEU"),
                flag=get_val(pd, "Flag"),
                last_port_of_call=get_val(pd, "Last_Port_Of_Call"),
                next_port_of_call=get_val(pd, "Next_Port_Of_Call"),
                reason_for_visit=get_val(pd, "Reason_For_Visit"),
                cargo_type=get_val(pd, "Cargo_Type"),
                quantity_value=get_float(pd, "Planned_Quantity"),
                grt=get_float(pd, "GRT"),
                loa_value=get_float(pd, "LOA_Value"),
                dwt=get_float(pd, "DWT")
            )
            self.db.add(vc)
            vessels_to_add.append((vcn, vc))
            
        self.db.flush()
        
        for vcn, vc in vessels_to_add:
            if vcn and vcn not in vcn_to_id:
                vcn_to_id[vcn] = vc.id
                
        event_records = self.db.execute(
            select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch.batch_id, StagingRecord.canonical_table == "event_occurrence")
        ).scalars().all()
        
        event_defs = self.db.execute(select(EventDefinition)).scalars().all()
        event_def_map = {e.name: e.id for e in event_defs}
        
        import pytz
        from dateutil import parser
        
        event_counters = {}
        for r in event_records:
            pd = r.parsed_data
            vcn = pd.get("VCN")
            vc_id = vcn_to_id.get(vcn)
            
            if not vc_id:
                r.validation_status = "QUARANTINED"
                r.errors = {"VCN": "Orphan event: VCN not found"}
                continue
                
            event_name = pd.get("Event_Name")
            event_def_id = event_def_map.get(event_name)
                
            timestamp_str = pd.get("Event_Timestamp")
            tz_str = pd.get("Timezone", "Africa/Johannesburg")
            
            parsed_tz = None
            utc_val = None
            if timestamp_str and timestamp_str != "":
                try:
                    dt = parser.parse(timestamp_str)
                    tz = pytz.timezone(tz_str)
                    if dt.tzinfo is None:
                        dt = tz.localize(dt)
                    utc_val = dt.astimezone(pytz.utc)
                    parsed_tz = dt
                except Exception:
                    pass
            
            scope = "ARRIVAL"
            if event_name and ("SAILING" in event_name or "DEPARTURE" in event_name or "OUT" in event_name):
                scope = "SAILING"
            elif event_name and "SHIFT" in event_name:
                scope = "SHIFTING"
                
            confidence_str = pd.get("Confidence_Score")
            try:
                confidence = float(confidence_str) if confidence_str and confidence_str != "" else None
            except Exception:
                confidence = None
                
            if utc_val and event_def_id:
                ev = EventOccurrence(
                    vessel_call_id=vc_id,
                    event_definition_id=event_def_id,
                    occurrence_index=(event_counters.update({(vc_id, event_def_id): event_counters.get((vc_id, event_def_id), 0) + 1}) or event_counters[(vc_id, event_def_id)]),
                    movement_scope=scope,
                    original_string=timestamp_str,
                    parsed_value=parsed_tz,
                    source_timezone=tz_str,
                    utc_value=utc_val,
                    capture_method="SYSTEM",
                    confidence=confidence,
                    source_system=pd.get("Source_System"),
                    source_record_id=pd.get("Event_ID"),
                    ingestion_batch_id=batch.batch_id,
                    is_quarantined=False
                )
                self.db.add(ev)
                

        batch_staging = self.db.execute(select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch.batch_id)).scalars().all()
        from apps.api.models.canonical import ServiceRequest, ServiceAssignment, ServiceExecution, Delay
        
        service_records = [r for r in batch_staging if r.canonical_table == 'service_request']
        for r in service_records:
            pd_data = r.parsed_data
            vcn = pd_data.get("VCN")
            vc_id = vcn_to_id.get(vcn)
            if not vc_id: continue
            
            def dt_parse(dt_str):
                from dateutil import parser
                import pytz
                if not dt_str: return None
                try:
                    dt = parser.parse(dt_str)
                    if dt.tzinfo is None:
                        dt = pytz.timezone("Africa/Johannesburg").localize(dt)
                    return dt.astimezone(pytz.utc)
                except:
                    return None
                    
            req = ServiceRequest(
                vessel_call_id=vc_id,
                service_type=pd_data.get("Service_Type", "Unknown"),
                requested_time=dt_parse(pd_data.get("Requested_Time"))
            )
            self.db.add(req)
            self.db.flush()
            
            ass = ServiceAssignment(
                service_request_id=req.id,
                scheduled_time=dt_parse(pd_data.get("Scheduled_Time")),
                assigned_resource_id=pd_data.get("Resource_Assigned"),
                resource_type=pd_data.get("Service_Type")
            )
            self.db.add(ass)
            self.db.flush()
            
            exe = ServiceExecution(
                service_assignment_id=ass.id,
                served_time=dt_parse(pd_data.get("Served_Time")),
                execution_status=pd_data.get("Data_Status")
            )
            self.db.add(exe)

        delay_records = [r for r in batch_staging if r.canonical_table == 'delay']
        for r in delay_records:
            pd_data = r.parsed_data
            vcn = pd_data.get("VCN")
            vc_id = vcn_to_id.get(vcn)
            if not vc_id: continue
            
            def float_val(val_str):
                if not val_str: return None
                try: return float(val_str)
                except: return None
                
            val = float_val(pd_data.get("Duration_Hours") or pd_data.get("Delay_Hours"))
            d = Delay(
                vessel_call_id=vc_id,
                movement_stage=pd_data.get("Movement_Type", "Unknown"),
                total_duration_hours=val if val is not None else 0.0,
                is_early_service=False
            )
            self.db.add(d)
        
        batch.status = "COMMITTED"
        self.db.commit()

