import re

with open('docs/spec/LEVEL_100_SPEC.md', 'r') as f:
    lines = f.readlines()

out = ["# Requirements Traceability Matrix\n"]
out.append("| REQ-ID | Spec section | Requirement (one line) | Planned module | Planned test | Status |")
out.append("|---|---|---|---|---|---|")

req_id = 1
current_section = "Unknown"

for line in lines:
    header_match = re.match(r'^#+\s+(.+)$', line)
    if header_match:
        current_section = header_match.group(1).strip()
    
    req_match = re.match(r'^(\d+\.)\s+(.+)$', line.strip())
    if req_match and not current_section.lower().startswith('level 100'):
        req_text = req_match.group(2).strip()
        if len(req_text) > 10: # simple filter
            # simple mapping
            module = "Core"
            if "KPI" in req_text: module = "kpi"
            elif "dashboard" in req_text.lower(): module = "reporting"
            elif "ingest" in req_text.lower(): module = "ingestion"
            elif "quality" in req_text.lower(): module = "quality"
            elif "identity" in req_text.lower() or "merge" in req_text.lower(): module = "identity"
            elif "journey" in req_text.lower(): module = "journey"
            
            status = "NOT_STARTED"
            if "OCR" in req_text or "live AIS" in req_text.lower() or "yard" in req_text.lower():
                status = "BACKLOG"
                
            out.append(f"| REQ-{req_id:03d} | {current_section} | {req_text[:80]}... | {module} | test_req_{req_id:03d} | {status} |")
            req_id += 1

with open('docs/RTM.md', 'w') as f:
    f.write("\n".join(out))

print("RTM generated.")
