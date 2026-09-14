import polars as pl
wb = pl.read_excel("fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx", sheet_id=0)
vc = wb["VesselCalls"].filter(pl.col("ATA").is_null())
print("VesselCalls with blank ATA:")
print(vc["VCN"].to_list())

ev = wb["Events"].filter(pl.col("Event_Name") == "ATA").filter(pl.col("Event_Timestamp").is_null() | (pl.col("Event_Timestamp") == ""))
print("\nEvents with blank ATA timestamp:")
print(ev["VCN"].to_list())
