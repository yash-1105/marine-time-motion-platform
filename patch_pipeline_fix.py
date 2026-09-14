with open("apps/api/services/ingestion/pipeline.py", "r") as f:
    text = f.read()

replacement = """
        # --- NEW CODE FOR SERVICES AND DELAYS ---
        batch_staging = self.db.execute(select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch.batch_id)).scalars().all()
        from apps.api.models.canonical import ServiceRequest, ServiceAssignment, ServiceExecution, Delay
"""
text = text.replace("        # --- NEW CODE FOR SERVICES AND DELAYS ---\n        from apps.api.models.canonical import ServiceRequest, ServiceAssignment, ServiceExecution, Delay", replacement)

with open("apps/api/services/ingestion/pipeline.py", "w") as f:
    f.write(text)
