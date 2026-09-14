with open("apps/api/services/ingestion/synthetic.py", "r") as f:
    text = f.read()

replacement = """
        db.execute(text("DELETE FROM staging.batch WHERE tenant_id = 'synthetic-tenant'"))
        db.execute(text("DELETE FROM raw.batch WHERE tenant_id = 'synthetic-tenant'"))
        
        # New models added
        db.execute(text("DELETE FROM canonical.service_execution WHERE service_assignment_id IN (SELECT id FROM canonical.service_assignment WHERE service_request_id IN (SELECT id FROM canonical.service_request WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')))"))
        db.execute(text("DELETE FROM canonical.service_assignment WHERE service_request_id IN (SELECT id FROM canonical.service_request WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant'))"))
        db.execute(text("DELETE FROM canonical.delay WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
        
        db.execute(text("DELETE FROM canonical.service_request WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
"""

import re
text = re.sub(r"        db\.execute\(text\(\"DELETE FROM staging\.batch.*?canonical\.service_request.*?tenant'\)\"\)\)", replacement, text, flags=re.DOTALL)

with open("apps/api/services/ingestion/synthetic.py", "w") as f:
    f.write(text)
