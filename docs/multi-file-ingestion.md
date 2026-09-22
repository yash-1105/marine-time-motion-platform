# Governed Multi-file Excel Ingestion

## Dataset-group state

`raw.batch.batch_id` is the parent dataset-group identifier. A group accepts one to fifteen `.xlsx` workbooks. `raw.file` is the immutable per-file manifest and records filename, checksum, size, storage reference, parse status, validation status, and failure detail.

Each raw and staging record carries `source_file_id`. Canonical records use the existing `source_lineage_id` envelope in the form `file-id:worksheet:row`; the exact source field/cell is resolved by the corresponding `raw.record` row, which retains the column name and original value.

## Processing and activation

1. The API validates count, type, size, and OOXML container for every submitted file.
2. Originals are copied to `INGESTION_STORAGE_PATH` before parsing. Development defaults to a local path; deployed GCS/MinIO storage must mount or provide the configured governed storage adapter at that path.
3. Polars/fastexcel reads tabular XLSX values. The governed route performs no AI, OCR, embedding, or LLM operation.
4. Each workbook is parsed, mapped, and rule-validated under one parent batch. Exact cross-file rows are marked `DUPLICATE`; raw evidence is retained.
5. A fatal container, parser, governed-sheet, or required-column error marks the group `FAILED` and prevents worker activation.
6. The bounded, retrying Dramatiq worker serializes work per tenant. Its replacement transaction converts internal service commits to flushes until all canonical, DQ, identity, analytics, KPI, and snapshot work succeeds. It then atomically promotes the new batch. Failure rolls the replacement back, retaining the prior active dataset.

## Migration

Alembic revision `k9l0m1n2o3p4` creates `raw.file` and adds `source_file_id` to `raw.record` and `staging.record`. Apply with `alembic upgrade head` before deploying the API/worker version that uses multi-file ingestion.
