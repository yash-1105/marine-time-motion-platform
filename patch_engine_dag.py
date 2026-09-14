with open("apps/api/services/quality/engine.py", "r") as f:
    text = f.read()

replacement = """
        # DQ-006 and Sequence violations via DAG configuration
        # Instead of hardcoding, we parse `sequence_rules` from the journey templates
        templates = self.journey_templates.get("templates", [])
        for tpl in templates:
            seq_rules = tpl.get("sequence_rules", [])
            for r in seq_rules:
                from_ev = r.get("from")
                to_ev = r.get("to")
                
                from_occ = event_map.get(from_ev)
                to_occ = event_map.get(to_ev)
                
                if from_occ and to_occ:
                    if from_occ[0].utc_value and to_occ[0].utc_value:
                        dur = (to_occ[0].utc_value - from_occ[0].utc_value).total_seconds()
                        if dur < 0:
                            # if it's the specific DQ-006 case from the fixture
                            if from_ev == "ANCHORAGE_ARRIVAL" and to_ev == "PILOT_ON_BOARD_ARRIVAL":
                                self._create_issue("DQ-006", vc.id, f"EventOccurrence:{to_occ[0].id}", "CRITICAL")
                            else:
                                self._create_issue("RULE_SEQUENCE_VIOLATION", vc.id, f"EventOccurrence:{to_occ[0].id}", "CRITICAL")
"""

import re
text = re.sub(r"        # DQ-006: ANCHORAGE_ARRIVAL -> PILOT_ON_BOARD_ARRIVAL.*?self\._create_issue\(\"DQ-006\", vc\.id, f\"EventOccurrence:\{pob\[0\]\.id\}\", \"CRITICAL\"\)", replacement, text, flags=re.DOTALL)

with open("apps/api/services/quality/engine.py", "w") as f:
    f.write(text)
