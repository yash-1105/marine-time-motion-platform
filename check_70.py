import polars as pl
wb = pl.read_excel("fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx", sheet_id=0)
vc = wb["VesselCalls"].filter(pl.col("VCN") == "SYNVCN2600070")
print("VesselCalls:", vc.select(["ATA"]))
ev = wb["Events"].filter((pl.col("VCN") == "SYNVCN2600070") & (pl.col("Event_Name") == "ATA"))
print("Events:", ev.select(["Event_Timestamp", "Source_System"]))
