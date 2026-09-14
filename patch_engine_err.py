with open("apps/api/services/quality/engine.py", "r") as f:
    text = f.read()

replacement = """
    def run_all(self):
        vessel_calls = self.db.execute(select(VesselCall)).scalars().all()
        for vc in vessel_calls:
            try:
                self.evaluate_vessel_call(vc)
            except Exception as e:
                print(f"Error evaluating {vc.vcn}: {e}")
                import traceback; traceback.print_exc()
        self.db.commit()
"""

import re
text = re.sub(r"    def run_all\(self\):.*?self\.db\.commit\(\)", replacement, text, flags=re.DOTALL)

with open("apps/api/services/quality/engine.py", "w") as f:
    f.write(text)
