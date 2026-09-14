import polars as pl
wb = pl.read_excel("fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx", sheet_id=0)
sv = wb["Services"].filter(pl.col("VCN") == "SYNVCN2600054")
print(sv.select(["Service_Type", "Execution_Delay_Hours"]))
