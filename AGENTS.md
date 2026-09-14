# AGENTS.md — Marine Time & Motion Platform

This file is read by the coding agent on every session. It holds the rules that never change.
Individual phase prompts assume everything here is already understood. Do not restate it back to me.

---

## 1. What this project is

A Port Marine Operations Time Release / Time-and-Motion Analytics Platform. It ingests fragmented
port data, standardises it into a governed canonical model, reconstructs each vessel call's journey,
calculates durations/delays/KPIs, and exposes dashboards, reports and a grounded copilot.

The controlling specification is `docs/spec/LEVEL_100_SPEC.md`. It is the source of truth. When this
file and the spec disagree, the spec wins and you must log the conflict in the Assumptions Register.

## 2. Stack (do not substitute without an ADR)

| Layer | Choice |
|---|---|
| Frontend | Next.js 15 (App Router), TypeScript, TanStack Query, TanStack Table, visx or Recharts, Radix primitives |
| API | Python 3.12, FastAPI, Pydantic v2, OpenAPI 3.1 |
| DB | PostgreSQL 16 — schemas: `raw`, `staging`, `canonical`, `analytics`, `audit`, `config`, `testkit` |
| Migrations | Alembic. Every schema change is a migration. Never `create_all` in app code. |
| Queue | Redis + Dramatiq (durable, retries, dead-letter) |
| Object storage | GCS (dev: MinIO via docker-compose) for original uploads, OCR artifacts, generated reports |
| Analytics compute | Polars in the service layer; SQL views for projections |
| AI | Gemini API via Google AI/Vertex. Model name comes from config, never hard-coded in business logic. |
| Deploy | Frontend → Vercel. API + worker + Postgres + Redis → Railway. CI → GitHub Actions. |
| Local | `docker compose up` must bring the whole system up from a clean clone |

Repo layout:

```
/apps/web          Next.js app
/apps/api          FastAPI app (modular monolith)
/apps/worker       Dramatiq workers (shares /apps/api domain code)
/packages/contracts OpenAPI-generated TS client
/db/migrations     Alembic
/config            Seed YAML: events, aliases, rules, KPIs, thresholds, roles
/fixtures          Synthetic workbook + checksum manifest
/docs              Spec, ADRs, RTM, assumptions register, runbooks, user guides
/tests             unit / integration / e2e / harness
```

API module boundaries (keep these clean enough to extract later):
`ingestion`, `quality`, `identity`, `journey`, `analytics`, `kpi`, `reporting`, `copilot`,
`admin`, `auth`, `audit`.

## 3. Non-negotiable behaviours

These come from the spec's §2 and they are the things most likely to be quietly violated. Treat any
violation as a build failure.

1. **No placeholders.** No dead buttons, empty cards, hard-coded KPI numbers, fake charts, or screens
   that are not wired to a working service. If a feature is not built yet, do not render an entry
   point for it.
2. **Traceability.** Every displayed metric resolves to: formula + formula version + source records +
   filters applied + exclusions + data-quality status. Build this into the response shape, not as a
   bolt-on.
3. **Timestamp envelope.** Every timestamp persists: original string, parsed value, source timezone,
   UTC value, capture method, confidence, source system, source record id, ingestion batch id,
   correction history. Store UTC; retain `Africa/Johannesburg` (or the port's tz) for display semantics.
   Use `timestamptz` everywhere. Never a naive datetime.
4. **Negative is not invalid.** A negative *execution delay* (`Served − Scheduled < 0`) is **early
   service** and must be preserved with its sign. A negative *duration* between two events that must
   be ordered (e.g. All Fast before Last Line Untied) is a **sequence violation**. These are different
   things, handled by different code paths, and both must exist.
5. **Inference is labelled.** AI-derived events, delay causes, and mappings are never stored as
   verified facts. They carry `inference_status`, confidence, supporting evidence, opposing evidence,
   and a human review state. The UI shows the label.
6. **Merges are evidenced.** Never merge vessel calls on name similarity alone. Deterministic keys
   first, then probabilistic scoring with visible evidence. Conflicting IMO or VCN blocks auto-merge
   unconditionally.
7. **Quarantine is respected.** Records with unresolved Critical quality issues are excluded from
   downstream KPIs by default. Inclusion requires an authorised action and is disclosed on every
   affected figure.
8. **Unavailable, not fabricated.** If a required input is missing, the metric's status is
   `UNAVAILABLE` with a reason. Never substitute zero, null-as-zero, a default, or an interpolation.
9. **Corrections never overwrite raw.** A steward correction creates a new canonical observation with
   reason, actor, timestamp and approval state. `raw.*` is append-only and immutable.
10. **Every list is a real list.** Filter, sort, paginate, search, saved views, column selection,
    export, and URL-encoded deep links. Filter context survives drill-down.

## 4. Fixture rules

The synthetic workbook lives at `/fixtures/`. It is a governed test fixture, not application data.

- **Never** alter the workbook to make a failing implementation pass.
- **Never** hard-code synthetic VCNs, expected values, or `Intentional_Flag` handling into
  application logic. The anomalies must be caught by the ordinary rule engine.
- `ExpectedOutputs`, `DQ_Cases` and `ValidationSummary` load **only** into the `testkit` schema.
  They are oracles. Application code must not be able to read them.
- The workbook filename varies (`..._Test_Data.xlsx`, `..._Test_Data_1.xlsx`). Resolve it by glob +
  checksum manifest, never by literal filename.
- A genuine fixture defect is recorded in `docs/test-data-issues.md`, with the original retained.
  See the known one in §6 below.

## 5. Working method

- Work in complete vertical slices. At the end of every phase `docker compose up` must produce a
  running application and `make test` must be green. A phase that leaves the app broken is not done.
- Before writing code for a phase, write the phase's entry in `docs/RTM.md` (requirement → module →
  test) and append any ambiguity to `docs/assumptions.md` with the configurable default you chose.
- Tests are written in the same phase as the code, not deferred. Aim for behaviour tests over
  coverage percentages.
- Do not ask me for approval mid-phase. Make the call, log it in the assumptions register, move on.
- Commit in logical units with conventional commit messages. Never commit secrets; use `.env.example`.
- When you finish a phase, output: what was built, what the tests prove, what you assumed, what you
  deliberately deferred, and the exact command to verify.

## 6. Verified facts about the fixture

I reverse-engineered these from the workbook. They are correct — use them, do not re-derive.

**Shape:** 9 sheets. `VesselCalls` 74 rows (72 base + 1 exact duplicate + 1 punctuation variant),
`Events` 1745 rows across 26 distinct event names, `Services` 432 rows, `CargoOps` 72, `Delays` 41,
`ExpectedOutputs` 72, `DQ_Cases` 10, `ValidationSummary` 11. Join key `VCN`. Timezone
`Africa/Johannesburg`. Timestamp format `yyyy-MM-dd HH:mm`.

**FIXTURE DEFECT — `Expected_Turnaround_Hours_ATA_to_ATD`.** This column is stored as Excel
*date-formatted* cells, not numbers. A naive reader returns `1900-01-14 21:36:00` instead of `14.90`.
Decode it as an Excel serial and correct for the Excel 1900 leap-year bug:

```python
serial = (cell_datetime - datetime(1899,12,30)).total_seconds() / 86400
hours  = serial if serial > 60 else serial - 1
```

Verified: this reproduces `ATD − ATA` for 70 of 71 calls within ±0.02h. The one exception is
`SYNVCN2600063`, the deliberate DQ-008 720-hour outlier. Record this in `docs/test-data-issues.md`;
do not edit the workbook. Put the decoder in the `testkit` loader only.

**Verified metric definitions** (each reproduces `ExpectedOutputs` within ±0.02h):

| Expected column | Definition |
|---|---|
| Turnaround | `VesselCalls.ATD − VesselCalls.ATA` |
| Anchorage Wait | `ANCHORAGE_ARRIVAL → PILOT_ON_BOARD_ARRIVAL` |
| Inward Movement | `PILOT_ON_BOARD_ARRIVAL → ALL_FAST_ARRIVAL` |
| Berth Stay | `ALL_FAST_ARRIVAL → LAST_LINE_UNTIED_SAILING` |
| Cargo Working | `CARGO_START → CARGO_END` |
| Outward Movement | `PILOT_ON_BOARD_SAILING → BREAKWATER_OUT` |
| Arrival Execution Delay | `Served_Time − Scheduled_Time` on `Services` rows where Movement=Arrival, Type=Pilotage Service |
| Sailing Execution Delay | same, Movement=Sailing |

**Expected population facts:** 72 base calls; 6 calls over 120h turnaround; 7 negative arrival
execution delays; 10 negative sailing execution delays; 8 calls with an optional shift (every 9th);
1 orphan event (`EV-ORPHAN-001`, VCN `SYNVCN-NOTFOUND`); 1 conflicting ATA pair on `SYNVCN2600070`
(`EV-0070-005` AIS 15:22 Verified vs `EV-CONFLICT-001` Manual Log 20:22 Conflicting, 5h apart).

**Tolerance trap:** several rows sit *exactly* on the ±0.02h boundary. Compare with
`round(abs(actual - expected), 6) <= tolerance`, not raw float subtraction, or you will get spurious
failures.

**Data coverage limit:** the fixture contains no yard, gate, rail, crane-level or downtime-event data.
KPIs 31–40 and several equipment KPIs are therefore **not computable** from it. They must still exist
in the KPI registry with status `NO_SOURCE_DATA` and a stated required-input list. Never invent values
for them.

## 7. Definition of done for the whole build

The build is acceptable when `make validate` runs the synthetic harness end to end and produces a
report in which: the workbook imports through the real ingestion UI/API; all 72 base calls reconstruct;
all 8 vessel-level metrics reconcile against `ExpectedOutputs` within tolerance for every eligible
call; all 10 DQ cases produce their documented outcome; negative delays survive as early service;
duplicates do not inflate any count; quarantined records are excluded and disclosed; and dashboard,
API and database totals agree under identical filters.
