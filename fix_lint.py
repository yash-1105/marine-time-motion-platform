with open("apps/api/services/ingestion/pipeline.py", "r") as f:
    text = f.read()

text = text.replace("except:", "except Exception:")
text = text.replace("if sheet == \"VesselCalls\": canonical_table = \"vessel_call\"", "if sheet == \"VesselCalls\":\n                    canonical_table = \"vessel_call\"")
text = text.replace("elif sheet == \"Events\": canonical_table = \"event_occurrence\"", "elif sheet == \"Events\":\n                    canonical_table = \"event_occurrence\"")
text = text.replace("elif sheet == \"Services\": canonical_table = \"service_request\"", "elif sheet == \"Services\":\n                    canonical_table = \"service_request\"")
text = text.replace("elif sheet == \"CargoOps\": canonical_table = \"cargo_ops\"", "elif sheet == \"CargoOps\":\n                    canonical_table = \"cargo_ops\"")
text = text.replace("elif sheet == \"Delays\": canonical_table = \"delay\"", "elif sheet == \"Delays\":\n                    canonical_table = \"delay\"")
text = text.replace("try: return float(val)", "try:\n                        return float(val)")
text = text.replace("except Exception: return None", "except Exception:\n                        return None")

with open("apps/api/services/ingestion/pipeline.py", "w") as f:
    f.write(text)

with open("apps/api/services/ingestion/synthetic.py", "r") as f:
    text = f.read()
    
text = text.replace("except:", "except Exception:")
lines = text.split("\n")
lines = [l for l in lines if l != "from .pipeline import IngestionPipeline"]
lines.insert(2, "from .pipeline import IngestionPipeline")
text = "\n".join(lines)

with open("apps/api/services/ingestion/synthetic.py", "w") as f:
    f.write(text)
