with open("apps/api/services/ingestion/pipeline.py", "r") as f:
    text = f.read()

text = text.replace("def get_val(key):", "def get_val(pd_dict, key):")
text = text.replace("val = pd.get(key)", "val = pd_dict.get(key)")

text = text.replace("def get_float(key):", "def get_float(pd_dict, key):")
text = text.replace("val = get_val(key)", "val = get_val(pd_dict, key)")

text = text.replace("get_val(\"Vessel_Name\")", "get_val(pd, \"Vessel_Name\")")
text = text.replace("get_val(\"IMO_Number\")", "get_val(pd, \"IMO_Number\")")
text = text.replace("get_val(\"Vessel_Type\")", "get_val(pd, \"Vessel_Type\")")
text = text.replace("get_float(\"Vessel_Size_TEU\")", "get_float(pd, \"Vessel_Size_TEU\")")
text = text.replace("get_val(\"Flag\")", "get_val(pd, \"Flag\")")
text = text.replace("get_val(\"Last_Port_Of_Call\")", "get_val(pd, \"Last_Port_Of_Call\")")
text = text.replace("get_val(\"Next_Port_Of_Call\")", "get_val(pd, \"Next_Port_Of_Call\")")
text = text.replace("get_val(\"Reason_For_Visit\")", "get_val(pd, \"Reason_For_Visit\")")
text = text.replace("get_val(\"Cargo_Type\")", "get_val(pd, \"Cargo_Type\")")
text = text.replace("get_float(\"Planned_Quantity\")", "get_float(pd, \"Planned_Quantity\")")
text = text.replace("get_float(\"GRT\")", "get_float(pd, \"GRT\")")
text = text.replace("get_float(\"LOA_Value\")", "get_float(pd, \"LOA_Value\")")
text = text.replace("get_float(\"DWT\")", "get_float(pd, \"DWT\")")

with open("apps/api/services/ingestion/pipeline.py", "w") as f:
    f.write(text)
