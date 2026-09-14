import re
with open("apps/api/services/quality/engine.py", "r") as f:
    text = f.read()

replacement = """
        # DQ-005: Pilot request present, scheduled absent (check events)
        pilot_req = event_map.get("PILOT_REQUEST_ARRIVAL")
        pilot_sched = event_map.get("PILOT_SCHEDULED_ARRIVAL")
        if pilot_req and not pilot_sched:
            self._create_issue("DQ-005", vc.id, f"EventOccurrence:{pilot_req[0].id}", "HIGH")
            
        # DQ-007: positive delay, reason blank (check Delays sheet via StagingRecord)
        delay_staging = self.db.execute(select(StagingRecord).where(StagingRecord.canonical_table == 'delay')).scalars().all()
        vc_delays = [d for d in delay_staging if d.parsed_data.get("VCN") == vc.vcn]
        for d in vc_delays:
            dur = d.parsed_data.get("Duration_Hours")
            reason = d.parsed_data.get("Delay_Reason")
            try:
                dur_val = float(dur) if dur else 0
                if dur_val > 0 and (not reason or str(reason).strip() == ""):
                    self._create_issue("DQ-007", vc.id, f"VesselCall:{vc.id}", "MEDIUM")
            except: pass
"""

text = re.sub(r"        # DQ-005 & DQ-006: Services.*?# DQ-007: positive delay, reason blank", replacement + "\n        # DQ-007: positive delay, reason blank", text, flags=re.DOTALL)

with open("apps/api/services/quality/engine.py", "w") as f:
    f.write(text)
