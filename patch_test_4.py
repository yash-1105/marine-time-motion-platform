with open("tests/test_dq_engine.py", "r") as f:
    text = f.read()

text = text.replace("db_session.add_all([req, ass, exe])", "db_session.add(req)\n    db_session.flush()\n    ass = ServiceAssignment(service_request_id=req.id, scheduled_time=datetime.datetime(2026, 1, 1, 10, 0, tzinfo=datetime.timezone.utc))\n    db_session.add(ass)\n    db_session.flush()\n    exe = ServiceExecution(service_assignment_id=ass.id, served_time=datetime.datetime(2026, 1, 1, 9, 30, tzinfo=datetime.timezone.utc))\n    db_session.add(exe)")

text = text.replace("ass = ServiceAssignment(service_request_id=req.id", "# ass = ...")
text = text.replace("exe = ServiceExecution(service_assignment_id=ass.id", "# exe = ...")
with open("tests/test_dq_engine.py", "w") as f:
    f.write(text)
