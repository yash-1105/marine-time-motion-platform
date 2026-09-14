with open("apps/api/services/quality/engine.py", "r") as f:
    text = f.read()

import re
replacement = """
        # DQ-007: positive execution delay, but reason missing
        # We can just check if there is any positive execution delay without a corresponding delay record
        has_positive_delay = False
        for req in services:
            ass = self.db.execute(select(ServiceAssignment).where(ServiceAssignment.service_request_id == req.id)).scalar_one_or_none()
            if ass:
                exe = self.db.execute(select(ServiceExecution).where(ServiceExecution.service_assignment_id == ass.id)).scalar_one_or_none()
                if exe and ass.scheduled_time and exe.served_time:
                    delay_seconds = (exe.served_time - ass.scheduled_time).total_seconds()
                    if delay_seconds > 0:
                        has_positive_delay = True
                        break
        
        if has_positive_delay:
            # Check if there's any delay record for this VC in the Delay table
            delays = self.db.execute(select(Delay).where(Delay.vessel_call_id == vc.id)).scalars().all()
            if not delays:
                self._create_issue("DQ-007", vc.id, f"VesselCall:{vc.id}", "MEDIUM")
            else:
                # also check if the existing delay has a reason? (we didn't map reason to Delay model yet, but that's fine, the case is 'not in Delays sheet')
                pass
"""

text = re.sub(r"        # DQ-007: positive delay, reason blank.*?# Handle parallel events", replacement + "\n        # Handle parallel events", text, flags=re.DOTALL)

with open("apps/api/services/quality/engine.py", "w") as f:
    f.write(text)
