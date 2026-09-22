# Marine Time & Motion Platform

Governed port-operation ingestion, time-and-motion analytics, dashboards, reporting, and scoped Copilot for marine operations teams.

The platform preserves source lineage from uploaded workbooks through raw, staging, canonical, and analytics data. Metrics are governed by configured formulas, data-quality rules, cohort filters, and persisted statistical results; unavailable source data is reported as unavailable rather than fabricated.

## Platform architecture

- **Web:** Next.js 15 App Router, TypeScript, TanStack Query/Table, Radix primitives, and Lucide icons.
- **API:** FastAPI, Pydantic v2, and OpenAPI 3.1.
- **Data:** PostgreSQL 16 with `raw`, `staging`, `canonical`, `analytics`, `audit`, `config`, and `testkit` schemas.
- **Processing:** Polars service-layer analytics with SQL projections.
- **Async work:** Redis and Dramatiq. Railway runs the API and the separate worker service.
- **Storage:** GCS in production; MinIO is available through Docker Compose for local development.
- **Deployment:** Vercel serves `apps/web`; Railway hosts the API, worker, PostgreSQL, and Redis.

## Core workflows

### Excel ingestion

An authorised administrator uploads a governed dataset group of **1–15** validated Excel/OOXML workbooks through the Data Ingestion screen. Each file retains an immutable original, checksum, byte size, storage reference, parse/validation status, and file/sheet/row lineage under one parent batch. The API preserves raw and staging evidence, then returns `202 PROCESSING`; a durable Dramatiq worker performs analytics and KPI/dashboard persistence. The group becomes active only after downstream processing succeeds.

Extraction is deterministic and rule-based (Polars/fastexcel where compatible, with openpyxl retained for OOXML compatibility). No AI, LLM, OCR, embedding, or model-assisted mapping is called by the governed Excel ingestion or DQ path. The web application polls persisted group/file status and reports `PROCESSING`, `COMMITTED`, or a useful failure state. Re-upload remains idempotent, and replacement batches isolate stale staging records until the new dataset is ready. Quarantine, validation, duplicate handling, and data-scope controls remain part of the normal pipeline.

### Governed delays and data quality

Service timing preserves four independent concepts: Planning Lead Time = `Requested − Submission`; Scheduling Gap = `Scheduled − Requested`; Execution Delay = `Served − Scheduled`; and Service/Stage Duration, which is never substituted for delay. Positive execution delay is late, zero is on time, and negative execution delay is retained as early service. Arrival/Inward, Sailing/Outward, and SHIFTING are separate movement scopes.

DQ validates deterministic format, completeness, duplicate, conflict, configured-DAG sequence, and request/schedule/served chronology rules before activation. `Scheduled < Requested` is a review issue; timestamps are never swapped or absolute-valued. An authorised analyst can logically exclude selected source rows from active analysis with an actor/reason/before/after audit trail. Raw evidence remains immutable, and a governed rebuild recalculates journeys, statistics, delays, KPIs, bottlenecks, and dashboards. Statistical outliers remain reviewable and are never automatically deleted.

### Governed statistics and KPIs

The governed statistical engine calculates count, missing count, mean, median, standard deviation, coefficient of variation, minimum/maximum, P25, P75, P90, configured P95, fastest/slowest observations, and outliers. Percentiles use the configured persisted calculation path (currently linear interpolation); the API is the sole calculator and Time & Motion Explorer/KPI UI expose the method, units, and sample availability.

The active governed KPI registry contains exactly the 55 numbered FRD definitions. Formula version `2.1` is the current executable release version; older results retain their own version attribution. Legacy unnumbered KPI definitions are retained only for historical lineage, marked inactive, and cannot enter current scorecards or calculations. The Governed KPIs experience surfaces persisted P75/P90 statistics and retains KPI formula versions, targets, variance, status, source lineage, and `UNAVAILABLE`/`NO_SOURCE_DATA` semantics. Refresh actions invalidate and reload the scorecard from persisted analytics.

### Service Line interpretation

The specification does not define a KPI literally named “Service Line.” The supported implementation represents that request through the real source-backed **Service Type** dimension (`ServiceRequest`/`ServiceAssignment`/`ServiceExecution` and `Services.Service_Type`). It reports governed execution-delay performance by service type and movement, including cohort filters, record lineage, and drill-through. Shipping Line remains a separate vessel-call filter and aggregation dimension.

## Web experience

The application includes:

- Executive Dashboard with vessel-call quality, cargo throughput, lead times, delay causes, bottlenecks, and KPI health.
- Vessel Calls and Vessel Journey reconstruction views.
- Data Ingestion with persisted asynchronous batch polling and dataset replacement controls.
- Time & Motion Explorer with governed catalogue, statistics, per-call lineage, and recalculation controls.
- Governed KPIs with persisted P75/P90 statistics and Service Type performance.
- Delays & Bottlenecks, Reports, Data Quality, Identity & Merges, and grounded Copilot workflows.

The current interface uses a shared maritime enterprise design system: teal maritime branding, Lucide outline icons, semantic status badges, consistent cards/tables/controls, compact route headers, and responsive dashboard layouts. Sidebar routes expose one primary page heading in the application shell; route metadata and actions remain in compact toolbars. Login branding is aligned to the same 42/58 split as its background so copy remains inside the teal panel at desktop widths.

## Local development

Copy `.env.example` to `.env` and set development-only values. Start the infrastructure and services from a clean checkout:

```bash
docker compose up -d
source .venv/bin/activate
alembic upgrade head
```

For the API, worker, and web development servers:

```bash
make dev
```

The API exposes `/live`, `/ready`, and `/health`; `/ready` verifies PostgreSQL and Redis. The web application is served from `apps/web`.

## Verification

Focused frontend checks:

```bash
cd apps/web
npm ci
npm run lint
npx tsc --noEmit
npm run build
```

Backend and integration tests:

```bash
DATABASE_URL='postgresql://admin:password@localhost:5434/marine_platform' \
REDIS_URL='redis://localhost:6379/0' make test
```

The synthetic validation harness runs the governed workbook through the real ingestion and analytics path:

```bash
make validate
```

The fixture is governed test data. Do not modify the workbook, expected outputs, or application logic to special-case fixture values. See [AGENTS.md](AGENTS.md), the [Level 100 specification](docs/spec/LEVEL_100_SPEC.md), [assumptions and decisions](docs/assumptions.md), and [test-data issues](docs/test-data-issues.md).

## Production deployment

The existing production targets are:

- **Frontend:** Vercel project `marine-time-motion-platform`, root directory `apps/web`, production branch `main`.
- **API and worker:** Railway services using the same PostgreSQL and Redis configuration. The worker must be deployed separately and run the Dramatiq process required by asynchronous ingestion.
- **Production URL:** https://marine-time-motion-platform.vercel.app/

Before a release, run migrations, verify `/live`, `/ready`, and `/health`, confirm Redis worker connectivity, and exercise login → authorised upload → `PROCESSING` → `COMMITTED` → dashboard/KPIs → reporting/Copilot/audit. See the [deployment runbook](docs/runbooks/deployment.md) for environment, proxy, storage, backup, and incident requirements.

Production secrets belong only in Railway/Vercel secret stores. `SARVAM_API_KEY`, JWT/OIDC secrets, database URLs, storage credentials, and Redis credentials must never be exposed as `NEXT_PUBLIC_*` variables.

## Recent shipped changes

- `daa541a`, `751198c`, `2030b9c`: asynchronous Excel ingestion, persisted batch polling, downstream analytics queuing, replacement staging isolation, governed P75 exposure, Service Type performance, and upload error handling.
- `835aae6`: batched governed KPI persistence to reduce ingestion and scorecard latency.
- `237122c`, `dd15f0c`, `81a1ff9`: serialized dataset replacement workers and Railway worker-role deployment support.
- `e48b8f0`: maritime enterprise visual redesign across the application, including shared tokens, professional icons, cards, tables, status treatments, and the logo mark.
- `cee40b7`: removed duplicated route headings and refined the Executive Dashboard hierarchy and responsive density.
- `3a65611`: aligned the login content grid with the teal background boundary so branding copy cannot cross into the form panel.

See the full [deployment runbook](docs/runbooks/deployment.md), [security threat model](docs/threat-model.md), and [known limitations](docs/known-limitations.md) for operational details.
