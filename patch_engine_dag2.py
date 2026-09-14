with open("apps/api/services/quality/engine.py", "r") as f:
    text = f.read()

text = text.replace("seq_rules = tpl.get(\"sequence_rules\", [])", "seq_rules = tpl.get(\"dag\", {}).get(\"sequence_rules\", [])")

with open("apps/api/services/quality/engine.py", "w") as f:
    f.write(text)
