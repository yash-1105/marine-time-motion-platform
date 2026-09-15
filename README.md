# Marine Time & Motion Platform

Governed port-operation ingestion, analytics, dashboards, reporting, and scoped Copilot.

## Local verification

Copy `.env.example` to `.env`, set development-only values, then run `docker compose up` and `alembic upgrade head`. API health endpoints are `/live`, `/ready`, and `/health`; `/ready` verifies PostgreSQL and Redis. Run focused tests with `pytest tests/test_security_hardening.py tests/test_copilot_core.py`, then build the web application with `cd apps/web && npm ci && npm run build`.

Production secrets are configured only in Railway/Vercel secret stores. `SARVAM_API_KEY`, JWT/OIDC secrets, database URLs, and storage credentials must never be `NEXT_PUBLIC_*` variables.

See [deployment runbook](docs/runbooks/deployment.md), [security threat model](docs/threat-model.md), and [known limitations](docs/known-limitations.md).
