import yaml
with open("apps/api/services/quality/engine.py", "r") as f:
    text = f.read()

replacement = """
    def __init__(self, db: Session):
        self.db = db
        # Load rules from DB
        self.rules = {r.rule_id: r for r in self.db.execute(select(QualityRule)).scalars().all()}
        # Load event definitions
        self.event_defs = {e.id: e.name for e in self.db.execute(select(EventDefinition)).scalars().all()}
        
        # Load journey templates for DAG chronology
        import yaml
        try:
            with open("config/journey_templates.yaml", "r") as yf:
                self.journey_templates = yaml.safe_load(yf)
        except Exception:
            self.journey_templates = {}
"""

import re
text = re.sub(r"    def __init__\(self, db: Session\):.*?self\.event_defs = \{e\.id: e\.name for e in self\.db\.execute\(select\(EventDefinition\)\)\.scalars\(\)\.all\(\)\}", replacement, text, flags=re.DOTALL)

with open("apps/api/services/quality/engine.py", "w") as f:
    f.write(text)
