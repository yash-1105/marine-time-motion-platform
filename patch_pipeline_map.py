with open("apps/api/services/ingestion/pipeline.py", "r") as f:
    text = f.read()

replacement = """
            if canonical_table == "vessel_call":
                canonical_table = "vessel_call"
            elif canonical_table == "event_occurrence":
                canonical_table = "event_occurrence"
            elif canonical_table == "service_request":
                canonical_table = "service_request"
            elif canonical_table == "delay":
                canonical_table = "delay"
            else:
                # Default mapping
                if "Event_Name" in rec: canonical_table = "event_occurrence"
                elif "Delay_ID" in rec: canonical_table = "delay"
                elif "Service_ID" in rec: canonical_table = "service_request"
                else: canonical_table = "vessel_call"
"""

import re
text = re.sub(r"            if canonical_table == \"vessel_call\":.*?else:\n                canonical_table = \"vessel_call\"", replacement, text, flags=re.DOTALL)

with open("apps/api/services/ingestion/pipeline.py", "w") as f:
    f.write(text)
