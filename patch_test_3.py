with open("tests/test_dq_engine.py", "r") as f:
    text = f.read()

import re
text = re.sub(r"id=str\(uuid\.uuid4\(\)\), ", "", text)
with open("tests/test_dq_engine.py", "w") as f:
    f.write(text)
