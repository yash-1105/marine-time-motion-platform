# FRD Requirements Compliance Audit

> **Release-remediation note (2026-09-23):** The KPI observations below are the
> Phase-0 baseline and are superseded for FRD §5 by
> [`kpi-formula-compliance.md`](kpi-formula-compliance.md). The active governed
> registry is exactly the 55 numbered FRD definitions at formula version `2.1`;
> each KPI has a terminal status of `IMPLEMENTED`, `NO_SOURCE_DATA`, or runtime
> `UNAVAILABLE`. Capacity, roster, and tug-release metrics are explicitly
> `NO_SOURCE_DATA`, rather than being calculated from service timestamps or
> constants. The baseline findings for non-KPI sections remain evidence, not a
> claim of final compliance.

**Audit date:** 2026-09-22  
**Authority:** `AI Tool Functional Requirement Document (FRD).docx`, with
`docs/spec/LEVEL_100_SPEC.md` used as the repository's more detailed controlling
specification where it does not conflict.  
**Scope:** source/configuration/schema/API/frontend/tests in the checked-out `main`
branch. This is a source audit, not a claim that a documented feature exists.

## Method and status legend

The FRD and the required repository documents were read in full. Evidence below is
from executable source, migrations/models, configuration, API routes, frontend route
components, and named tests. A planned document, README statement, or comment is not
treated as implementation evidence.

| Status | Meaning |
|---|---|
| **IMPLEMENTED** | Code, exposure where required, and meaningful test evidence agree with the FRD. |
| **PARTIALLY_IMPLEMENTED** | A material subset exists, but a required behavior, scope, protection, or evidence is missing. |
| **IMPLEMENTED_DIFFERENTLY** | Code produces a behavior/formula different from the numbered FRD requirement. |
| **NOT_IMPLEMENTED** | No executable implementation was found. |
| **NO_SOURCE_DATA** | Correctly registered unavailable because the supplied governed workbook cannot provide the required input. |

## Executive summary

The platform has a substantial working vertical slice: authenticated Excel upload,
raw/staging/canonical persistence, asynchronous downstream processing, identity
resolution, versioned journey reconstruction, Polars lead-time statistics (including
P75/P90), delay records/allocations, bottleneck persistence, an executive dashboard,
and frontend routes for the principal user workflows.

It is **not FRD-compliant as a whole**. The most serious finding is a governed-KPI
integrity defect: `apps/api/services/kpi/registry.py` correctly describes the 55 FRD
KPIs, but `apps/api/services/kpi/engine.py::_compute_kpi_value` maps many of those
same KPI numbers to different calculations. The engine also embeds non-governed
constants (four berths, four pilots/tugs, 720 hours and average resource durations).
Consequently registry/API metadata cannot be relied upon as a statement of the value
actually calculated.

Other material gaps are: staging validation is literally unimplemented; only XLSX/CSV
are accepted and originals are not persisted in configured object storage; DQ is
incomplete and several quality endpoints are unauthenticated/unscoped; external source
connectors/OCR/master-data administration are absent; dashboard/filter and operational
views cover only a subset of the FRD; and reporting/Copilot are narrow compared with
the specified role and evidence requirements. `docs/test-data-issues.md`, which both
`AGENTS.md` and the README reference, is absent from this checkout.

## Cross-cutting traceability matrix

| FRD section | Requirement / expected behavior | Current implementation and evidence | API / UI / tests | Status and action |
|---|---|---|---|---|
| Data ingestion; data model | Ingest PMS/VTS/TOS/tug/pilot/berth/incident sources through Excel, CSV, PDF, APIs, databases and OCR. | `routers/ingestion.py` accepts only `.xlsx` and `.csv`; `pipeline.py` uses `polars.read_excel` and hard-coded sheets `VesselCalls`, `Events`, `Services`, `CargoOps`, `Delays`. No PDF/OCR/API/database connector implementation found. | `POST /ingestion/upload`; `/ingestion` UI; `test_ingestion.py`. | **PARTIALLY_IMPLEMENTED** — retain governed workbook route; add adapters/connectors and source contracts before claiming source breadth. |
| Data ingestion; validation | Validate file/container, schema, mandatory fields, type/range/sequence and preserve row errors/quarantine. | Size and XLSX ZIP magic checks in `routers/ingestion.py`; raw and staging records retain cells. `IngestionPipeline._validate_staging` is `pass` (`pipeline.py:194`), so no staging schema/field/type validation occurs. | Upload errors and batch polling exist; no tests of staging validation. | **PARTIALLY_IMPLEMENTED** — implement rule-driven staging validation and persist per-row errors/statuses. |
| Data ingestion; lineage/idempotency | Immutable original, checksum, batch ID, raw-to-canonical lineage, idempotent re-upload and safe replacement. | SHA-256, `raw.batch`, raw cells, staging rows, canonical ingestion batch IDs and worker serialization exist. Upload writes temporary `/tmp/uploads` then deletes it; no GCS/MinIO upload-original adapter. `force_new=True` creates a new batch for re-upload rather than checksum idempotency. | `GET /ingestion/{active,batches}`, dataset polling UI; `test_dataset_upload_queues_analytics_and_worker_commits_batch`, `test_reset_removes_staging_rows_before_batch_rows`. | **PARTIALLY_IMPLEMENTED** — persist original in object storage and define/implement idempotency semantics for normal re-upload. |
| Security / tenancy | RBAC, tenant/port/terminal scope and audit all sensitive actions. | `require()` is used on ingestion, journey, analytics, KPI and identity routes. `routers/quality.py` has no auth dependency and no tenant filter; several services (`DelayService`, bottleneck queries) do not constrain tenant. | Auth tests: `test_auth_rbac.py`; audit tests: `test_audit.py`. | **PARTIALLY_IMPLEMENTED** — protect and scope every router/query; test cross-tenant denial. |
| Canonical data model | Persist timestamp envelope, source IDs, corrections and canonical entities. | `EventOccurrence` stores original string, parsed/timezone/UTC, capture method, confidence, source system/record and batch; corrections and canonical selection are modelled. `pipeline.py` silently drops unparsable event timestamps rather than persisting a validation record. | `/journey/{id}/events`, corrections route; `test_traceability_envelope_present`, journey correction tests. | **PARTIALLY_IMPLEMENTED** — preserve parsing failures as DQ/lineage records, not silent omission. |
| Data quality | Required DQ rules, severity/workflow/remediation, critical quarantine excluded downstream. | Quality engine implements portions of DQ-003/004/005/006/007/010; duplicate cases are generated by identity. Critical quarantine only sets `EventOccurrence.is_quarantined`, while critical issue on a vessel call does not make `VesselCall` quarantined. Re-runs can create duplicate issues. | `/quality/*`, `/data-quality`; only two focused `test_dq_engine.py` tests. | **PARTIALLY_IMPLEMENTED** — implement the full configured rule set, idempotency, record/call quarantine propagation and workflow/audit. |
| Identity / merge | Deterministic keys first, probabilistic evidence, conflicts block merge, survivorship/audit/unmerge. | Pairwise matcher/evidence, conflict detection, merge decision/audit and survivorship exist (`services/identity/*`). `auto_merge_candidates` runs in the pipeline. | `/identity/*`, `/identity`; `test_identity_engine.py`, journey conflict tests. | **PARTIALLY_IMPLEMENTED** — performance/scoped queries and complete conflict governance require review; core rule exists. |
| Journey reconstruction | Configurable DAG, stages, repeatable shifts, missing vs inferred, no double count, handovers/history. | `JourneyReconstructionEngine` and template loader persist stages, decomposition, handovers and history. It excludes quarantined events and preserves conflict resolution. | `/journey/*`, `/vessel-journey`; ten journey tests including all 72 calls and decomposition. | **IMPLEMENTED** for the governed workbook journey path; validate each production template/source mapping before broad rollout. |
| Statistical performance | Count/missing/mean/median/std/CV/min/max/P25/P75/P90/P95/outliers, explicit percentile method and unavailable semantics. | `AnalyticsEngine.compute_statistics` uses Polars linear interpolation and persists all listed fields; no observations produces `None`, not zero. | `/analytics/metrics/{id}/stats`; Time & Motion and KPI P75/P90 UI; `test_statistics_percentile_method_is_linear_interpolation`, `test_governed_statistics_expose_p75_and_p90`. | **IMPLEMENTED** for all-cohort persisted lead-time aggregates. Cohort filters are recorded but not applied in `compute_statistics`; add cohort computation before claiming segmented stats. |
| Delay analysis | Retain stated/recalculated delay, early service sign, reconciliation and allocation/unallocated remainder. | Ingestion maps delays, recalculates from schedule/served, preserves negative duration and maps categories; `DelayService` exposes allocation/reconciliation/Pareto. | `/delays/*`, `/delays`; tests for mapping, allocations, DQ-007 and endpoints. | **PARTIALLY_IMPLEMENTED** — service and summary queries lack tenant scoping; reasons/categories are largely source-driven rather than validated workflow. |
| Delay cause analysis | Controlled taxonomy, confirmed/inferred labels, confidence/evidence/opposing evidence, human review and multi-cause allocation. | Canonical category mapping and allocation fields exist; source values are copied and generic confidence is synthesized in `pipeline.py`. No actual inference model/opposing evidence was found. | Delay detail/UI, inference-isolation tests. | **PARTIALLY_IMPLEMENTED** — add governed inference producer/reviewer and evidence model; do not label source defaults as verified. |
| Bottlenecks | Score duration, frequency, variability, tail, turnaround contribution, target breach and business criticality; do not rank longest duration alone. | `BottleneckEngine` computes weighted multi-factor scores and persists `BottleneckRecord`; stage target/criticality constants are in code. | `/bottlenecks`, dashboard `/`; `test_non_duration_only_bottleneck_ranking`, `test_criticality_three_component_scores_always_exposed`. | **PARTIALLY_IMPLEMENTED** — move thresholds/criticality to governed configuration and tenant-scope queries. |
| Dashboard / UI | Executive, operations, KPI, delay, journey views with governed filter context and drill-through. | Routes exist for executive, calls, journey, ingestion, time-motion, KPIs, delays, reports, quality, identity, Copilot. `AppShell` only renders global scope filters on `/`, `/vessel-calls`, `/time-and-motion`; no dedicated Operations Live dashboard or master data/config/admin/lineage navigation route exists. | Dashboard API/UI and `test_dashboard_reconciliation.py`. | **PARTIALLY_IMPLEMENTED** — add required operational/admin/lineage surfaces and apply filters consistently. |
| Reporting | Daily/weekly/monthly/quarterly/benchmark reports, scheduling, output formats, storage/access controls. | Report templates/runs/artifacts and a local filesystem artifact service exist. Storage defaults to `/tmp`; no verified GCS/MinIO adapter or benchmark reporting breadth. | `/reports`, `/reports`; `test_reporting.py`. | **PARTIALLY_IMPLEMENTED** — use durable object storage, scope every artifact, implement remaining report types. |
| Copilot | Grounded questions across operational domains with citations, caveats and action recommendations. | Copilot router/service and UI exist; core tests cover retrieval/guarding. No evidence that all FRD question classes and cross-domain evidence requirements are implemented. | `/copilot`, floating panel; `test_copilot_core.py`. | **PARTIALLY_IMPLEMENTED** — create an FRD question-to-tool/evidence test matrix and implement gaps. |
| Configuration / governance | Configurable events, aliases, rules, thresholds, KPIs and assumptions/ADR controls. | YAML configs and DB config models exist. `config/kpis.yaml` is generic placeholder text (`KPI_1`, `Numerator / Denominator`) and is not the runtime registry; runtime registry is hard-coded Python. | Registry endpoint; tests only registry presence/arithmetic spot checks. | **IMPLEMENTED_DIFFERENTLY** — make one governed, versioned formula source; remove/replace misleading unused placeholder config. |

## KPI Calculation Engine — all 55 numbered requirements

The table distinguishes **registry metadata** from executable behavior. Registry source is
`apps/api/services/kpi/registry.py`; executable source is
`apps/api/services/kpi/engine.py::_compute_kpi_value`. API is `GET /kpis` and
`GET /kpis/scorecard`; UI is `/kpis`. The existing KPI test suite proves registration,
alias handling, no-source behavior and a limited hand-verified arithmetic subset; it
does **not** provide one formula conformance test per numbered FRD KPI.

| KPI | FRD formula / intent | Runtime evidence | Status / action |
|---:|---|---|---|
| 1 | Count distinct vessel calls | Counts eligible unmerged vessel calls. | **IMPLEMENTED** |
| 2 | Cargo quantity / calls, segregated by unit | Segments by unit but counts cargo-operation rows, not distinct vessel calls, in denominator. | **IMPLEMENTED_DIFFERENTLY** — `COUNT(DISTINCT vessel_call_id)`. |
| 3 | Anchorage arrival → pilot on board average | Event duration average. | **IMPLEMENTED** |
| 4 | Anchorage arrival → berth commencement/first line tied | Event duration average. | **IMPLEMENTED** |
| 5 | Stddev anchorage wait by vessel type | Calculates one pooled sample; no vessel-type grouping. | **IMPLEMENTED_DIFFERENTLY** |
| 6 | VTS clearance time | Registry `NO_SOURCE_DATA`; no dispatcher branch. | **NO_SOURCE_DATA** |
| 7 | POB → All Fast inward movement | Dispatcher labels it towage and permits `TUG_ATTACH` as start. | **IMPLEMENTED_DIFFERENTLY** |
| 8 | Inward towage duration / assisted vessels or services | Event proxy plus selectable denominator; no actual tug-duration event requirement. | **PARTIALLY_IMPLEMENTED** |
| 9 | Available tug hours / requested tug hours | Calculates outward towage duration. | **IMPLEMENTED_DIFFERENTLY** |
| 10 | Available pilot hours / requested pilot hours | Calculates arrival pilot schedule-to-served delay. | **IMPLEMENTED_DIFFERENTLY** |
| 11 | Tug request → tug arrival | Uses scheduled-to-served service delay, not request-to-arrival. | **IMPLEMENTED_DIFFERENTLY** |
| 12 | Pilot scheduled/assigned → on board | Calculates mooring/berthing service delay. | **IMPLEMENTED_DIFFERENTLY** |
| 13 | Pilot-to-berth transit | Calculates a 1-hour anchorage-wait threshold “berth availability” rate. | **IMPLEMENTED_DIFFERENTLY** |
| 14 | Berth occupancy | Computes berth stay/capacity but hard-codes four berths. | **PARTIALLY_IMPLEMENTED** — governed berth inventory/config required. |
| 15 | Average berthing time | Calculates first-line/all-fast → last-line-untied berth turnaround. | **IMPLEMENTED_DIFFERENTLY** |
| 16 | Berthing-time variation | Calculates cargo / berth stay productivity. | **IMPLEMENTED_DIFFERENTLY** |
| 17 | Non-working time at berth | Calculates a working-time ratio. | **IMPLEMENTED_DIFFERENTLY** |
| 18 | Berth idle percentage | Calculates cargo / working-hours rate. | **IMPLEMENTED_DIFFERENTLY** |
| 19 | Number of shifts | Calculates berth idle time. | **IMPLEMENTED_DIFFERENTLY** |
| 20 | Average shifting time | Calculates berth dwell. | **IMPLEMENTED_DIFFERENTLY** |
| 21 | Berth productivity | Implements TEU moves / crane-hours, not the FRD’s berth productivity definition. | **IMPLEMENTED_DIFFERENTLY** |
| 22 | Berth utilization | Calculates gross crane productivity. | **IMPLEMENTED_DIFFERENTLY** |
| 23 | Cargo throughput MT | Calculates net crane productivity. | **IMPLEMENTED_DIFFERENTLY** |
| 24 | Container throughput TEU | Sums TEU actual quantities; restow treatment is only a disclosure. | **PARTIALLY_IMPLEMENTED** |
| 25 | Voyage productivity | Calculates cargo handling duration. | **IMPLEMENTED_DIFFERENTLY** |
| 26 | First lift time | No dispatcher branch. | **NOT_IMPLEMENTED** |
| 27 | OSBD / operational separation before departure | Calculates cargo-end → departure duration under a different name. | **IMPLEMENTED_DIFFERENTLY** |
| 28 | Cranes per vessel | Calculates cargo downtime/idle time. | **IMPLEMENTED_DIFFERENTLY** |
| 29 | Equipment downtime | Sums cargo working hours. | **IMPLEMENTED_DIFFERENTLY** |
| 30 | Crane moves/hour/crane | Calculates moves / summed working-hours × deployed resources. | **IMPLEMENTED** |
| 31–35 | Yard dwell, productivity, capacity/yard KPIs | Registry declares unavailable; source workbook has no yard data. | **NO_SOURCE_DATA** |
| 36–40 | Gate/rail/modal KPIs | Registry declares unavailable; source workbook has no gate/rail data. | **NO_SOURCE_DATA** |
| 41 | Anchorage arrival → departure turnaround | Computes anchorage → `BREAKWATER_OUT`/fallback. | **IMPLEMENTED** |
| 42 | Berth turnaround | Calculates anchorage duration. | **IMPLEMENTED_DIFFERENTLY** |
| 43 | Outward movement | Calculates working-hours / turnaround efficiency. | **IMPLEMENTED_DIFFERENTLY** |
| 44 | Outward towage | Calculates ATA → ATD port time. | **IMPLEMENTED_DIFFERENTLY** |
| 45 | Outward moves/day | Calculates total delay hours. | **IMPLEMENTED_DIFFERENTLY** |
| 46 | Crane availability | No dispatcher branch / no required source. | **NO_SOURCE_DATA** |
| 47 | Gang shift efficiency | No dispatcher branch / no required source. | **NO_SOURCE_DATA** |
| 48 | Unproductive moves | No dispatcher branch / no required source. | **NO_SOURCE_DATA** |
| 49 | Pilot utilization | Uses `2h × pilot services` and `4 × 720h` hard-coded capacity. | **IMPLEMENTED_DIFFERENTLY** |
| 50 | Tug utilization | Uses `1.5h × tug services` and `4 × 720h` hard-coded capacity. | **IMPLEMENTED_DIFFERENTLY** |
| 51 | Berth occupancy alias | Registry aliases KPI-14; therefore inherits KPI-14 hard-coded berth issue. | **PARTIALLY_IMPLEMENTED** |
| 52 | Crane utilization | No dispatcher branch / no required source. | **NO_SOURCE_DATA** |
| 53 | Tug response-time alias | Registry aliases KPI-11; inherits schedule-to-served mismatch. | **IMPLEMENTED_DIFFERENTLY** |
| 54 | Pilot response time | Calculates on-time sailing-departure rate with 30-minute hard-coded grace. | **IMPLEMENTED_DIFFERENTLY** |
| 55 | Average crane downtime | No dispatcher branch / no required source. | **NO_SOURCE_DATA** |

### KPI-specific evidence and required remediation

`ensure_kpi_registry` correctly registers all 55 and marks source-limited items as
`NO_SOURCE_DATA`. That is not sufficient compliance when a code branch for a numbered
KPI calculates a different concept. First replace the dispatcher with a formula map
whose key, numerator, denominator, required source fields, availability and version
come from one governed configuration/registry source; then add a fixture- and
hand-calculated conformance test for every computable KPI. Do not expose values for
31–40/46–48/52/55 until their source data contracts exist.

## API and UI exposure inventory

| FRD experience | Code/API evidence | Finding |
|---|---|---|
| Executive dashboard | `GET /dashboard/executive`, `src/app/page.tsx`, persisted `DashboardSnapshot` | Present; filters are more limited than FRD global scope and reconciliation is only seven programmed combinations. |
| Time & motion explorer | `/analytics/*`, `src/app/time-and-motion/page.tsx` | Present for catalogue/results/stats/custom event pairs and traceability. |
| Governed KPIs / percentile view | `/kpis/*`, `src/app/kpis/page.tsx` | P75/P90 and Service Type performance are surfaced. “Service Line” is interpreted as Service Type; FRD does not define a literal Service Line KPI. This is a UI exposure, not a new FRD KPI. |
| Delays / bottlenecks | `/delays/*`, `/bottlenecks`, `src/app/delays/page.tsx` | Present but not consistently tenant-scoped. |
| Vessel calls / journey | operations/journey routers, corresponding pages | Present; journey route is strong. |
| Data quality / identity | `/quality/*`, `/identity/*`, corresponding pages | Present; quality access controls are missing. |
| Ingestion lifecycle | `/ingestion/*`, `src/app/ingestion/page.tsx`, Dramatiq worker | 202 plus persisted batch polling works architecturally; original-file persistence and staging validation do not. |
| Reports / Copilot | `/reports`, `/copilot`, route pages and floating panel | Present as limited vertical slices; broad FRD capability needs testable coverage. |
| Admin/config/master data/audit-and-lineage | Models/config/audit route fragments only; no sidebar route | **NOT_IMPLEMENTED** as a complete end-user FRD experience. |

## Baseline verification

`DATABASE_URL=postgresql://admin:password@localhost:5434/marine_platform`
and `REDIS_URL=redis://localhost:6379/0` were supplied for the local Docker services.

| Command | Result | Audit interpretation |
|---|---|---|
| `make validate` | **PASS** in 50.16s: 72/72 base population and journeys; 8/8 target metrics; 10/10 DQ cases; 38/38 registry-computable KPIs (17 `NO_SOURCE_DATA`); 41/41 delays; dashboard reconciliation 7/7 combinations. | This establishes that the harness’s selected acceptance cases pass. It does not test each 55-KPI formula against the FRD. Generated report artifacts were restored after the run so this audit changes only this document. |
| `make test` without local DB overrides | **26 failed, 52 passed, 10 errors** in 53.44s. The failures resolve `postgres.railway.internal`, which is not DNS-reachable from this workstation; most are subsequent connection/pending-rollback failures. | Environment/configuration baseline failure, not evidence that the 26 test behaviors independently regressed. A clean isolated full local-DB run could not be captured within this tool session after the prior run had left worker processes; rerun it in one shell with the two local environment variables exported before using this audit as a release gate. |

The named tests nevertheless demonstrate meaningful coverage of ingestion queueing,
analytics reconciliation, P75/P90, journey, identity, delays/bottlenecks, reporting
and API access; they do not close the formula-conformance or broad-FRD gaps above.

## Highest-risk discrepancies

1. **KPI number/formula mismatch.** A response labelled with the registry’s KPI number
   and FRD formula can contain an unrelated runtime calculation. This is a governance,
   reporting and decision-risk issue.
2. **Hard-coded operational capacity.** KPI-14/49/50 use undeclared operational
   constants, violating configurable/governed source requirements and making results
   port-specific by accident.
3. **Missing staging validation and original upload persistence.** Invalid data can
   reach canonical processing while originals are deleted from local temporary storage.
4. **Data-scope/security gaps.** Quality endpoints and several analytical service
   queries are not consistently authorization/tenant constrained.
5. **Quarantine semantics are incomplete.** Critical quality issues do not reliably
   quarantine the vessel call/population used by every downstream calculation.

## Change classification

### Already present

- Asynchronous 202 ingestion, Dramatiq worker, persisted batch polling and serialized
  replacement.
- Persisted governed statistics with linear-interpolated P75/P90 and UI exposure.
- Service Type execution-performance view used to interpret the earlier “Service Line
  KPI” request; it retains source service request/assignment/execution records.
- Core journey, delay allocation, bottleneck and dashboard vertical slices.

### Requires backend changes

- KPI dispatcher/registry unification and formula conformance.
- Rule-driven staging validation, parsing error persistence, file/original object storage
  and production source adapters.
- DQ coverage/quarantine/workflow idempotency; tenant/RBAC enforcement in all services.
- Config-driven berth/resource capacities, bottleneck thresholds and criticality.
- Full cause-inference evidence/review capability, expanded reporting and Copilot tools.

### Requires only UI exposure (after APIs are governed)

- Admin/configuration/master-data/audit-lineage route surfaces.
- Full operational live view and consistently applied filter context.
- Additional report/benchmark and source-lineage drill-through panels where backend
  records already exist.

### Requires database migrations

- Durable original-upload object reference and validation-error/provenance fields if not
  represented by an existing storage model.
- Governed resource/berth capacity and versioned KPI formula configuration.
- Any additional source connector, inference-evidence/opposing-evidence, review
  workflow, and tenant-scoping keys required by the backend changes.

## Recommended implementation order

1. Freeze KPI publication and correct the single-source registry/dispatcher mismatch;
   add all-computable-KPI conformance tests.
2. Repair ingestion validation/original storage and enforce tenant/RBAC/quarantine
   boundaries end-to-end.
3. Make DQ rules and workflows complete/idempotent and rerun the governed harness.
4. Externalize operational capacities, bottleneck criticality/thresholds and formula
   versions with migrations and audit controls.
5. Add missing source adapters/data contracts; keep source-limited KPIs explicitly
   `NO_SOURCE_DATA` until then.
6. Complete operational/admin/lineage/report/Copilot UI exposure only on governed APIs.

## Documentation discrepancy

The missing fixture-defect register identified during the original audit has been
restored as [`docs/test-data-issues.md`](../test-data-issues.md). It records only
the documented Excel serial-date oracle defect and is not accessible to production
code.

## Final integration release gate — 2026-09-22

This audit was rechecked after the multi-file ingestion, governed delay, statistics,
and deterministic DQ/exclusion changes. The local validation harness remains green,
and the code paths retain deterministic parsing/DQ (no AI/LLM dependency), P75/min/max
API exposure, independent service timing semantics, and separate ARRIVAL/SAILING/
SHIFTING scopes.

**Release gate: BLOCKED.** The KPI formula audit still documents partial/different
FRD implementations and incomplete all-KPI edge-case coverage. The database also
contains 55 numbered governed definitions plus 58 pre-governance unnumbered legacy
rows that need a lineage-preserving retirement decision. These are governance/release
blockers, so no production deployment was performed by this verification phase.
