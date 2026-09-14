with open("tests/test_dq_engine.py", "r") as f:
    text = f.read()

text = text.replace("capture_method=\"SYSTEM\", is_quarantined=False)", "movement_scope=\"ARRIVAL\", capture_method=\"SYSTEM\", is_quarantined=False)")
with open("tests/test_dq_engine.py", "w") as f:
    f.write(text)
