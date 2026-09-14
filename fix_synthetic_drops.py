import re
with open("apps/api/services/ingestion/synthetic.py", "r") as f:
    text = f.read()

replacement = """
    db.execute(text("DELETE FROM quality.quality_issue WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
    db.execute(text("DELETE FROM canonical.event_occurrence WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
    db.execute(text("DELETE FROM canonical.service_execution WHERE service_assignment_id IN (SELECT id FROM canonical.service_assignment WHERE service_request_id IN (SELECT id FROM canonical.service_request WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')))"))
    db.execute(text("DELETE FROM canonical.service_assignment WHERE service_request_id IN (SELECT id FROM canonical.service_request WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant'))"))
    db.execute(text("DELETE FROM canonical.service_request WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
    db.execute(text("DELETE FROM canonical.delay WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
    db.execute(text("DELETE FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant'"))
"""

text = re.sub(r"    db\.execute\(text\(\"DELETE FROM quality\.quality_issue.*?tenant'\)\"\)\)", replacement, text, flags=re.DOTALL)

with open("apps/api/services/ingestion/synthetic.py", "w") as f:
    f.write(text)
