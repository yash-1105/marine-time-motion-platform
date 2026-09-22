# Governed data-quality workflow

The ingestion path is deterministic: workbook extraction → raw/staging lineage →
schema and duplicate validation → canonical candidate → DQ → identity/journey →
analytics/KPIs. No AI, OCR, embedding, or LLM is called for any DQ decision.

## Timestamp and chronology rules

Raw timestamp strings, declared timezone, parsed value, UTC value, and source
lineage are retained. UI formatting is presentation-only (`YYYY-MM-DD HH:mm`);
it does not change stored precision. The engine validates configured DAG edges,
not an invented total order, so legitimate parallel activities are unaffected.

For a service, `Requested <= Scheduled` is a DQ chronology requirement.
`Served - Scheduled < 0` remains a valid early-service execution delay. Missing
requested, scheduled, served, mandatory fields, and invalid timestamp strings are
reviewable issues; they are never repaired or replaced with zero.

## Excluding an analytical row

An authorised administrator may exclude one, several, or all filtered quality
issues. The API records `EXCLUDED` on the matching staging record with the reason
and writes an audit event containing actor, issue IDs, source record IDs and
before/after state. The raw workbook and raw records are unchanged.

The active dataset is rebuilt from the same staging batch, excluding only rows
marked `EXCLUDED`, then re-runs DQ, identity, journey reconstruction, statistics,
outlier detection, bottlenecks, KPIs and the dashboard snapshot. If lineage is
missing, the action is refused rather than guessing a source row. Statistical
outliers remain a separate review class and are not automatically excluded.
