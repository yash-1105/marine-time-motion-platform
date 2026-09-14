import polars as pl
wb = pl.read_excel("fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx", sheet_id=0)
ev = wb["Events"].filter((pl.col("VCN") == "SYNVCN2600018") & (pl.col("Event_Name") == "ATA"))
print("Timestamp:", ev["Event_Timestamp"][0])
