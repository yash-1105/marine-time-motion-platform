# Phase 13 — Reporting and distribution
**Model: `gemini-3.7-flash-medium`**
*(Straightforward implementation work against settled services. Escalate to `-high` only if the
document generation libraries fight you.)*

Read `AGENTS.md`. Spec §13 is the reference.

## 1. Generation

Four formats from the same governed report definition: PDF, Excel, PowerPoint, Word. Every figure in
every format comes from the analytics and KPI services — never from a separate reporting query, or
the report will drift from the dashboard and fail the reconciliation requirement.

Build **one report template completely**: **Daily Operations** (spec §13.1) covering movements,
anchorage, pilotage, towage, berth, cargo progress, delays, incidents, resources, exceptions and an
attention list. Register the other four (Weekly Marine Performance, Monthly Management Review,
Quarterly KPI Review, Benchmark Performance) as template definitions with their section structures, so
the architecture is proven and the backlog is explicit. Note this in `docs/scope-decisions.md`.

Each generated report carries: template id and version, port branding, reporting period, filters
applied, author/system, generation timestamp, application version, formula versions used, and a
synthetic-data label when produced from the synthetic tenant.

## 2. Distribution and workflow
Approval workflow before publication. Distribution by email, in-app notification and document
repository. Retry on failure with a delivery log. Access control on the published artifact. Generation
runs as an async job with progress and cancellation, per spec §18.

Scheduling: build the schedule model, the schedule management UI, and the job that a scheduler would
invoke, and expose a manual "run now". Actual cron execution in production is a deployment concern —
document it in the runbook rather than faking a scheduler that is not running.

## 3. AI narrative
Generated only from calculated facts. Cites metric ids and vessel-call evidence internally. States
period and filters. Distinguishes correlation from causation. Discloses weak data. Fabricates no
explanations. Reuse the grounding layer from phase 12, do not write a second one.

Add a test that generates a report over a population with a quarantined record included and asserts
the disclosure appears in the output.

## Done when
The Daily Operations report generates in all four formats from real fixture data; figures in the
report match the dashboard and API under identical filters (add this to the reconciliation test);
approval and distribution work with a delivery log; the four other templates are registered with
their structures; the synthetic label appears on every artifact from the synthetic tenant.
