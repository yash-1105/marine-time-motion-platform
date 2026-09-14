import polars as pl
wb = pl.read_excel("fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx", sheet_id=0)
dl = wb["Delays"].filter(pl.col("VCN") == "SYNVCN2600054")
print(dl.select(["Delay_Hours", "Delay_Reason"]))
