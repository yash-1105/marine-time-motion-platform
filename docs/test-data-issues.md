# Governed synthetic test-data issues

The synthetic workbook is immutable test evidence. This register documents source
defects; it is not consumed by production ingestion or analytics code.

## TDI-001 — Excel date formatting in expected turnaround oracle

`ExpectedOutputs.Expected_Turnaround_Hours_ATA_to_ATD` is stored in Excel as a
date-formatted serial rather than a numeric hour value. A naïve reader can return
`1900-01-14 21:36:00` instead of `14.90` hours.

The `testkit` loader alone decodes the serial with the Excel 1900 leap-year
correction:

```python
serial = (cell_datetime - datetime(1899, 12, 30)).total_seconds() / 86400
hours = serial if serial > 60 else serial - 1
```

This reconciles `ATD − ATA` for 70 of 71 eligible calls within ±0.02h. The
exception, `SYNVCN2600063`, is the documented deliberate DQ-008 720-hour outlier.
The workbook and ExpectedOutputs are never altered to accommodate this issue.
