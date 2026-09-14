with open("apps/api/services/ingestion/pipeline.py", "r") as f:
    text = f.read()

replacement = """
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
"""

text = text.replace("        batch.status = \"COMMITTED\"\n        self.db.commit()", replacement)

with open("apps/api/services/ingestion/pipeline.py", "w") as f:
    f.write(text)
