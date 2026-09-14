with open("tests/test_dq_engine.py", "r") as f:
    text = f.read()

text = text.replace("db_session.execute(\"SELECT", "db_session.execute(text(\"SELECT")
text = text.replace(").scalar()", "\")).scalar()")
text = text.replace("import datetime", "import datetime\nfrom sqlalchemy import text")
with open("tests/test_dq_engine.py", "w") as f:
    f.write(text)
