# Phase 08 — KPI engine and registry
**Model: `gemini-3.7-flash-high`**

Read `AGENTS.md`. Spec §11 is the reference. The KPI definitions were seeded in phase 01; this phase
makes the engine that executes them.

## 1. Registry

All 55 KPIs from spec §11 exist as governed registry entries with name, business definition, formula,
numerator, denominator, unit, eligible population, required fields and events, exclusions, aggregation
method, vessel applicability, target, thresholds, owner, effective dates and lineage. Formula changes
create a new `kpi_formula_version`; historical results remain attributed to the version that produced
them.

Preserve the spec's KPI numbering for traceability. Where the spec's own list duplicates a concept
(11 and 53 tug response; 14 and 51 berth occupancy), mark one primary and the other an alias, so
dashboards cannot double-count. Administrators can change which is primary.

## 2. Execution status

Every KPI result has a status:

- `COMPUTED` — calculated from available governed data
- `UNAVAILABLE` — required inputs missing for this population or period, with the specific missing
  inputs named
- `NO_SOURCE_DATA` — no connected source can ever supply the inputs in the current deployment, with
  the required source systems named

Given this fixture, expect roughly: the marine, berthing, cargo-timing, departure and turnaround KPIs
computable; the yard KPIs (31–35), gate and landside KPIs (36–40), crane-level productivity and
equipment downtime KPIs not computable. Register them all; fabricate nothing. A `NO_SOURCE_DATA` KPI
renders in the catalogue with its required-inputs list and does not appear as a zero on any dashboard.

## 3. Formula correctness traps from spec §11

The spec calls these out and they are easy to get wrong:

- **Berth Productivity (21)**: moves / crane-hours. If crane-hours are already summed across cranes,
  do not multiply by crane count again.
- **Crane Moves per Hour per Crane (30)**: total moves / summed productive crane-hours.
- **Average Vessel Call Size (2)**: never mix units. The fixture carries TEU, MT and Units in the same
  column. Segment by unit; an unqualified combined throughput total must be impossible to produce.
- **Container Traffic in TEUs (24)**: loaded + unloaded + transshipped, with restow treatment
  configured and disclosed.
- **Average Inward Towage Duration (8)**: the denominator choice (assisted vessels vs services) is
  configurable and disclosed on the result.
- **Turnaround (41)**: departure − anchorage arrival, with governed exclusions. Note this is a
  different definition from the ATA-to-ATD turnaround the oracle checks — implement both, name them
  distinctly, and do not let them collide.
- **First Container Lift Time (26)**: the reference point (Berthing vs All Fast) is configured and disclosed.

## 4. Engine

- Calculates over a filtered population with the same filter semantics the dashboards will use, so
  that dashboard, API and database totals agree by construction.
- Results persist to `analytics.kpi_result` with population definition, filters, exclusions, formula
  version, input data-quality summary and calculation timestamp.
- Recalculation is an explicit, permissioned, audited action that produces a new result rather than
  overwriting.
- Targets, thresholds and Green/Amber/Red banding with configurable tolerances.
- Period-over-period, prior month/quarter/year, and cohort comparison. Trends at daily, weekly,
  monthly, quarterly and annual grain with baseline comparison, rolling averages, and
  improving/deteriorating/stable classification.
- Benchmark model and admin UI exist; peer-port benchmark data is absent and recorded as such with its
  source and period fields empty rather than populated with invented numbers.

## 5. Tests
Every computable KPI gets a unit test with a hand-verified small fixture of your own construction
(not the workbook) plus edge cases: empty population, single observation, zero denominator, all-null
inputs, mixed units. Every `NO_SOURCE_DATA` KPI gets a test asserting it does not produce a number.

## Done when
All 55 exist in the registry with correct status; alias/duplicate pairs cannot double-count; every
computable KPI has a passing unit test; no KPI returns a value it cannot justify; `make validate`
includes a KPI reconciliation section.
