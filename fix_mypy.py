with open("apps/api/services/ingestion/pipeline.py", "r") as f:
    text = f.read()

text = text.replace("return existing.batch_id", "return str(existing.batch_id)")
text = text.replace("return batch.batch_id", "return str(batch.batch_id)")
text = text.replace("row_map[r.row_number][\"data\"][r.column_name] = r.original_value", "if isinstance(row_map[r.row_number], dict) and isinstance(row_map[r.row_number].get(\"data\"), dict):\n                    row_map[r.row_number][\"data\"][str(r.column_name)] = r.original_value")

with open("apps/api/services/ingestion/pipeline.py", "w") as f:
    f.write(text)
