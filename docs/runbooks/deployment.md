# Deployment and operations runbook

## Railway and Vercel

The API deployment uses `railway.json`; Railway must provide `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, OIDC configuration, `CORS_ORIGINS` containing the exact Vercel production domain, report/GCS storage settings, and optional Sarvam credentials. The worker uses the same Redis URL and must be deployed separately from `apps/worker`. Vercel receives only `NEXT_PUBLIC_API_URL`; it must be the public HTTPS Railway API origin (without `/api/v1`) and must not receive backend secrets. Railway must allow the configured upload size at its proxy; the API enforces `UPLOAD_MAX_BYTES` and validates OOXML containers itself.

Before release: run migrations, confirm `/live`, `/ready`, and `/health`, verify Redis worker connectivity, then exercise login → authorised upload → `PROCESSING` batch → `COMMITTED` batch → dashboard → Vessel Calls/Journey → approved report artifact → Copilot tool call → audit event. The upload returns `202` after raw/staging/canonical processing and the worker makes the batch active only after analytics/dashboard persistence succeeds. Confirm report delivery failure/retry in a non-production recipient.

### Migration procedure and rollback

Take a verified PostgreSQL backup and record the current Alembic revision before deployment. Apply `alembic upgrade head` once from the API release image, then verify the revision and the readiness endpoint before enabling worker processing. The multi-file ingestion revision (`k9l0m1n2o3p4`) is additive: it creates `raw.file`, nullable per-file lineage columns on raw/staging records, and non-unique lineage lookup indexes. It does not rewrite or delete existing batches, raw evidence, canonical rows, or analytics history.

Its downgrade removes only those additive columns/table/indexes, so do not downgrade a production database containing new dataset-group manifests until their metadata has been archived and the API/worker have been rolled back together. The follow-on `l0m1n2o3p4q5` revision is index-only and its downgrade preserves all data. The `m1n2o3p4q5r6` legacy-KPI retirement revision is also additive: it marks unnumbered `analytics.kpi` definitions inactive, retains their IDs/results/audit lineage, and adds an optional alias to an explicitly equivalent governed definition. Its downgrade removes only the retirement metadata after the application is rolled back; it never deletes KPI definitions or results. Object-store originals remain immutable and are not deleted by a schema downgrade. Verify the `raw.file` group-batch, raw/staging source-file/sheet/row, and `analytics.kpi(is_active, kpi_number)` indexes after migration for ingestion/DQ/KPI review performance.

For this release, ensure Railway has an API service and a separate `SERVICE_ROLE=worker` service using the same deployed image, `DATABASE_URL`, and `REDIS_URL`. Do not send live uploads until the worker logs show a connected Dramatiq consumer.

The repository cannot verify the live Vercel/Railway domain, GCS IAM policy, mail/notification adapter, or scheduler deployment without those environment credentials. Do not mark a release ready until those checks are recorded.

## Backup, restore, and incident response

Schedule encrypted PostgreSQL backups and object-storage versioning; test restore into an isolated tenant before each release. Preserve `raw` and `audit` schemas. On incident: revoke affected OIDC/service account/Sarvam keys, stop workers if artifacts may expose data, retain audit logs, restore only after root-cause review, and document the event.
