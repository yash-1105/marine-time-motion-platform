# Deployment and operations runbook

## Railway and Vercel

The API deployment uses `railway.json`; Railway must provide `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, OIDC configuration, `CORS_ORIGINS` containing the exact Vercel production domain, report/GCS storage settings, and optional Sarvam credentials. The worker uses the same Redis URL and must be deployed separately from `apps/worker`. Vercel receives only `NEXT_PUBLIC_API_URL`; it must not receive backend secrets.

Before release: run migrations, confirm `/live`, `/ready`, and `/health`, verify Redis worker connectivity, then exercise login → authorised upload → ingestion status → dashboard → Vessel Calls/Journey → approved report artifact → Copilot tool call → audit event. Confirm report delivery failure/retry in a non-production recipient.

The repository cannot verify the live Vercel/Railway domain, GCS IAM policy, mail/notification adapter, or scheduler deployment without those environment credentials. Do not mark a release ready until those checks are recorded.

## Backup, restore, and incident response

Schedule encrypted PostgreSQL backups and object-storage versioning; test restore into an isolated tenant before each release. Preserve `raw` and `audit` schemas. On incident: revoke affected OIDC/service account/Sarvam keys, stop workers if artifacts may expose data, retain audit logs, restore only after root-cause review, and document the event.
