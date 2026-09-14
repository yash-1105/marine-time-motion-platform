with open("apps/api/services/ingestion/pipeline.py", "r") as f:
    text = f.read()

text = text.replace("row_map[r.row_number][\"data\"][str(r.column_name)] = r.original_value", "row_map[r.row_number][\"data\"][str(r.column_name)] = r.original_value  # type: ignore")

with open("apps/api/services/ingestion/pipeline.py", "w") as f:
    f.write(text)
