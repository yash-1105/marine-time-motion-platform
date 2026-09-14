with open("apps/api/services/ingestion/synthetic.py", "r") as f:
    text = f.read()

replacement = """
    db.execute(text("DELETE FROM quality.quality_issue WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
    db.execute(text("DELETE FROM canonical.event_occurrence WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = 'synthetic-tenant')"))
"""

import re
text = re.sub(r"    db\.execute\(text\(\"DELETE FROM canonical\.event_occurrence WHERE vessel_call_id IN \(SELECT id FROM canonical\.vessel_call WHERE tenant_id = 'synthetic-tenant'\)\"\)\)", replacement, text)

with open("apps/api/services/ingestion/synthetic.py", "w") as f:
    f.write(text)
