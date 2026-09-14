import polars as pl
wb = pl.read_excel("fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx", sheet_id=0)
dl = wb["Delays"]
print(dl)
