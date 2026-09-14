import polars as pl
wb = pl.read_excel("fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx", sheet_id=0)
vc = wb["VesselCalls"].filter(pl.col("VCN") == "SYNVCN2600027")
print(vc.columns)
