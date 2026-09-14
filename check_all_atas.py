import polars as pl
wb = pl.read_excel("fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx", sheet_id=0)
vcs = set(wb["VesselCalls"]["VCN"].to_list())
evs = set(wb["Events"].filter(pl.col("Event_Name") == "ATA")["VCN"].to_list())
print("VCNs without ATA in Events sheet:", vcs - evs)
