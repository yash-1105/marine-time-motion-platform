with open("apps/api/services/quality/engine.py", "r") as f:
    text = f.read()

text = text.replace("dur = d.parsed_data.get(\"Duration_Hours\")", "dur = d.parsed_data.get(\"Delay_Hours\")")
# Also check if it's "Delay_Reason" or "Delay_Category"
# Both exist, so getting Delay_Reason is fine.

with open("apps/api/services/quality/engine.py", "w") as f:
    f.write(text)
