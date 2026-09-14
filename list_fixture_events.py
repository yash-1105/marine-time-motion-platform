import polars as pl
workbook = pl.read_excel("fixtures/Synthetic_Marine_Time_Motion_Test_Data.xlsx", sheet_id=0)
print(workbook["Events"]["Event_Name"].unique().to_list())
