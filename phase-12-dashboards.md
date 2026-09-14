# Phase 12 — Executive, KPI and Delay dashboards, and the Time & Motion Explorer
**Model: `gemini-3.7-flash-high`**

Read `AGENTS.md` and `docs/design-system.md` from phase 11. Spec §12.1, §12.3, §12.4, §12.7 are the
reference. Reuse the filter primitive, table primitive and traceability drawer from phase 11 — do not
build second versions.

## 1. Executive Dashboard (§12.1)
Vessel calls, turnaround, throughput **with an unambiguous unit** (the fixture mixes TEU, MT and Units
— segment, never sum), delays, critical risks, target status with trend arrows, top bottlenecks,
criticality heatmap, data-quality confidence, and an AI executive narrative.

Every card drills to evidence. A card with no drill-through is a placeholder and violates spec §2.

The AI narrative is generated only from calculated facts, cites metric ids and vessel-call ids
internally, states the period and filters it describes, distinguishes correlation from causation,
discloses weak data, and offers no explanation it cannot ground. Test it on a filtered population
with deliberately sparse data and assert it says so.

## 2. Live Operations (§12.2)
Active vessels, anchorage queue, berth plan and occupancy, upcoming movements, pilots and tugs
available and assigned, active incidents, overdue events, clearances, resource conflicts. Distinguish
live, delayed, stale, manually entered and inferred observations visually. Show a refresh timestamp
and a degraded-data warning when feeds are stale.

The fixture is historical, so "live" means the most recent window in the dataset. Say so on screen
rather than implying a real-time feed that does not exist.

## 3. KPI Dashboard (§12.3)
KPI catalogue, scorecards, trends, actual versus target, benchmarks, variance, period-over-period,
cohort comparison, a definition drawer showing formula and lineage, and drill-through to the
underlying calls.

`NO_SOURCE_DATA` KPIs appear in the catalogue with their required-inputs list and are visually
distinct from computed ones. They never render as a zero, a dash, or an empty chart.

## 4. Delay and Bottleneck Dashboard (§12.4)
Delay cause Pareto, stage heatmap, frequency and duration distributions, bottleneck ranking with its
component scores exposed, criticality components, P90 tail risk, resource capacity relationship, stage
contribution, trend, inferred versus confirmed causes clearly separated, and action tracking.

## 5. Time & Motion Explorer (§12.7)
Custom event-pair analysis on the phase 07 builder: pick any start and any end event, choose cohort
filters, get a distribution chart, box plot, histogram, trend, scatter plot, summary statistics and an
outlier table. Compare two cohorts side by side. Save an analysis. Export. And an "explain methodology"
panel stating percentile method, eligibility, exclusions and sample size.

## 6. Reconciliation requirement

Spec §20.13 and §21A.5.10 require dashboard, API and database totals to agree under identical filters.
Write an automated test that, for a set of filter combinations, queries the dashboard endpoint, the
analytics API and the database directly, and asserts all three agree. Wire it into `make validate` as
the "dashboard/API/database total consistency" section. This test is how you prove the dashboards are
not decorative.

## Charts
Accessible palettes, tooltips, legends, explicit units, sample-size labels, data-quality warnings on
any chart built from a population with unresolved issues, and a download of the underlying data for
every chart.

## Done when
All four dashboards run on real data; every card drills to evidence; throughput never mixes units;
`NO_SOURCE_DATA` KPIs are visible and clearly non-computed; the three-way reconciliation test passes
under multiple filter combinations; the AI narrative is grounded and caveated.
