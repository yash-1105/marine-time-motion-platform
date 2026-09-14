with open("apps/api/services/quality/engine.py", "r") as f:
    text = f.read()

dq_006 = """
        # DQ-006: ANCHORAGE_ARRIVAL -> PILOT_ON_BOARD_ARRIVAL must be > 0 (sequence violation)
        anchor = event_map.get("ANCHORAGE_ARRIVAL")
        pob = event_map.get("PILOT_ON_BOARD_ARRIVAL")
        if anchor and pob:
            if anchor[0].utc_value and pob[0].utc_value:
                dur = (pob[0].utc_value - anchor[0].utc_value).total_seconds()
                if dur < 0:
                    self._create_issue("DQ-006", vc.id, f"EventOccurrence:{pob[0].id}", "CRITICAL")
"""

text = text.replace("        # DQ-007: positive execution delay, but reason missing", dq_006 + "\n        # DQ-007: positive execution delay, but reason missing")

with open("apps/api/services/quality/engine.py", "w") as f:
    f.write(text)
