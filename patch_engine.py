with open("apps/api/services/quality/engine.py", "r") as f:
    text = f.read()

import re
replacement = """
    def evaluate_vessel_call(self, vc: VesselCall):
        # We can also check the staging record for the vessel call to catch missing VesselCalls sheet fields
        from apps.api.models.ingestion import StagingRecord
        staging = self.db.execute(select(StagingRecord).where(StagingRecord.canonical_table == 'vessel_call')).scalars().all()
        # Find the staging record for this VCN
        vc_staging = next((s for s in staging if s.parsed_data.get("VCN") == vc.vcn), None)
        
        # DQ-003: ATA blank in VesselCalls sheet
        if vc_staging and (not vc_staging.parsed_data.get("ATA") or str(vc_staging.parsed_data.get("ATA")).strip() == ""):
            self._create_issue("DQ-003", vc.id, f"VesselCall:{vc.id}", "HIGH")
            
        events = self.db.execute(select(EventOccurrence).where(EventOccurrence.vessel_call_id == vc.id)).scalars().all()
        event_map = {}
        for ev in events:
            name = self.event_defs.get(ev.event_definition_id)
            if name not in event_map: event_map[name] = []
            event_map[name].append(ev)
            
        # DQ-004: ETA after ATA
        # We check staging record ETA/ATA too because Events sheet ETA/ATA might not reflect the injected error
        eta_staging = vc_staging.parsed_data.get("ETA") if vc_staging else None
        ata_staging = vc_staging.parsed_data.get("ATA") if vc_staging else None
        
        if eta_staging and ata_staging:
            from dateutil import parser
            import pytz
            try:
                eta_dt = parser.parse(eta_staging)
                ata_dt = parser.parse(ata_staging)
                if eta_dt > ata_dt:
                    self._create_issue("DQ-004", vc.id, f"VesselCall:{vc.id}", "HIGH")
            except: pass
            
        # Or if it's in the events
        eta_evs = event_map.get("ETA")
        ata_evs = event_map.get("ATA")
        if eta_evs and ata_evs:
            if eta_evs[0].utc_value and ata_evs[0].utc_value and eta_evs[0].utc_value > ata_evs[0].utc_value:
                self._create_issue("DQ-004", vc.id, f"EventOccurrence:{eta_evs[0].id}", "HIGH")
                
        # DQ-010: Conflicting ATA values
        if ata_evs and len(ata_evs) > 1:
            # check if they differ by 5 hours
            dur = abs((ata_evs[0].utc_value - ata_evs[1].utc_value).total_seconds()) / 3600
            if dur >= 5:
                self._create_issue("DQ-010", vc.id, f"EventOccurrence:{ata_evs[0].id}", "HIGH")
"""
text = re.sub(r"    def evaluate_vessel_call.*?# DQ-005 & DQ-006: Services", replacement + "\n        # DQ-005 & DQ-006: Services", text, flags=re.DOTALL)

with open("apps/api/services/quality/engine.py", "w") as f:
    f.write(text)
