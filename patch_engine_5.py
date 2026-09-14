with open("apps/api/services/quality/engine.py", "r") as f:
    text = f.read()

replacement = """
        # DQ-007: positive execution delay, but reason missing
        services = self.db.execute(select(ServiceRequest).where(ServiceRequest.vessel_call_id == vc.id)).scalars().all()
"""

text = text.replace("        # DQ-007: positive execution delay, but reason missing", replacement)

with open("apps/api/services/quality/engine.py", "w") as f:
    f.write(text)
