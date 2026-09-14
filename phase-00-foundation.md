# Phase 00 — Foundation
**Model: `gemini-3.1-pro-high`**

Read `AGENTS.md` and `docs/spec/LEVEL_100_SPEC.md` in full before doing anything.

This phase produces no product features. It produces the scaffolding and the governance artifacts
that every later phase writes into. Do it properly; everything downstream depends on it.

## Deliverables

**1. Requirements traceability matrix — `docs/RTM.md`**
Parse the spec into a table: `REQ-ID | Spec section | Requirement (one line) | Planned module | Planned test | Status`.
Status is one of `NOT_STARTED | IN_PROGRESS | DONE | BACKLOG`. Cover every numbered requirement in
spec sections 2, 4, 6–20 and 21A. Expect roughly 250–400 rows. Mark everything `NOT_STARTED`
except items you deliberately place in `BACKLOG` — and for those, fill a `Rationale` column.

**2. Assumptions and decisions register — `docs/assumptions.md`**
Table: `ID | Spec reference | Ambiguity | Decision taken | Configurable? | Config key | Test`.
Seed it with at least these, which the spec leaves open:
- Port Stay convention (ETA-to-ATD vs ATA-to-ATD) — default ATA-to-ATD, config key `metrics.port_stay.start_event`
- Turnaround exclusions (litigation, repairs) — default none, admin-configurable exclusion list
- Restow treatment in TEU throughput — default excluded from throughput, reported separately
- Auto-merge threshold — default 0.98, review band 0.85–0.9799
- Outlier method — default robust MAD with configurable sigma; percentile method stated as linear interpolation
- Criticality weighting — default arithmetic mean of the three component scores
- Tug-before-pilot tolerance — default treated as violation, port-level override available

**3. Scope decisions — `docs/scope-decisions.md`**
Two columns: fully built, versus registered-and-backlogged with required inputs and rationale.
Anything that the fixture cannot exercise goes in column two. Be explicit that this is a governed
scoping decision under spec §6, not an omission.

**4. ADRs — `docs/adr/0001-*.md` through `0008-*.md`**
One per major choice, in the standard Context/Decision/Consequences form: modular monolith over
microservices; Postgres schema separation; event-occurrence model over wide timestamp table;
`timestamptz` + UTC storage with port-local display; Dramatiq over Celery; Polars for analytics;
Next.js App Router + server-state library; Gemini for AI features with model name in config.

**5. Repository scaffold**
Build the layout in `AGENTS.md` §2. It must actually run:
- `apps/api`: FastAPI app, settings via pydantic-settings, structured JSON logging with correlation
  IDs, `/health` `/ready` `/live`, OpenAPI 3.1 served at `/openapi.json`, error schema with
  `code`/`message`/`detail`/`correlation_id`, versioned router at `/api/v1`.
- `apps/worker`: Dramatiq worker bootstrapped against Redis, one no-op task proving round-trip.
- `apps/web`: Next.js App Router, TypeScript strict, an app shell with the spec §5 primary navigation
  rendered but with unbuilt routes returning an honest "not built yet in this phase" page — do not
  create fake dashboards.
- `db/migrations`: Alembic initialised, one migration creating the seven schemas from `AGENTS.md` §2.
- `docker-compose.yml`: api, worker, web, postgres:16, redis:7, minio. One `docker compose up` from a
  clean clone must work.
- `Makefile`: `dev`, `test`, `lint`, `migrate`, `seed`, `validate` (stub for now), `fmt`.

**6. CI — `.github/workflows/ci.yml`**
Lint (ruff + mypy + eslint + tsc), unit tests, migration up/down check, build both apps. Must pass.

**7. Fixture manifest**
Write `fixtures/MANIFEST.json` holding the workbook's filename, SHA-256, sheet names, row counts per
sheet, and a `synthetic: true` flag. Add a test asserting the checksum matches, so silent fixture
edits are caught. Resolve the workbook by glob, never by literal filename.

## Constraints
- No business logic this phase. No domain tables beyond the empty schemas.
- The nav shell must not imply working features. Honest empty states only.
- Do not add dependencies that are not in the `AGENTS.md` stack table without writing an ADR.

## Done when
`docker compose up` from a clean clone serves the web shell and a green `/health`; `make test` passes;
CI is green; and the four governance documents exist and are populated, not templated.
