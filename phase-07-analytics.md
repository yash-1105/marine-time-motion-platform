# Phase 07 — Time and motion analytics engine
**Model: `gemini-3.1-pro-high`**

Read `AGENTS.md`, especially §6 (verified metric definitions). Spec §10 is the reference. This phase
produces the numbers that phase 10 reconciles against the oracle, so precision matters more than breadth.

## 1. Duration semantics (spec §10.1)

Implement each of these as a distinct, named, separately tested concept. Conflating any two of them
is the failure mode this section exists to prevent.

| Concept | Definition |
|---|---|
| Lead Time | end actual − start actual |
| Planning Lead Time | requested service time − request submission time |
| Scheduling Gap | scheduled time − requested time |
| Execution Delay | actual service time − scheduled time |
| Target Variance | actual − target |
| Waiting Time | inactive interval awaiting a prerequisite, resource or clearance |
| Service Time | interval during which the service is actively executed |
| Delay Frequency | delayed eligible events / total eligible events |
| Early Delivery | negative execution delay |

Every formula carries: eligibility criteria, null handling, unit, timezone, exclusions, and a version.
A result is `AVAILABLE` with a value, or `UNAVAILABLE` with a reason — never a fabricated zero.

The fixture's `Services` sheet gives you `Submission_Time`, `Requested_Time`, `Scheduled_Time`,
`Served_Time` on every row precisely so that Planning Lead Time, Scheduling Gap and Execution Delay
are all independently computable. Compute all three; do not collapse them.

## 2. Lead-time catalogue (spec §10.2)

Seed every standard calculation listed in spec §10.2 as a `lead_time_definition` row. Those the
fixture can compute, compute. Those it cannot (crane movements, container movements, lashing,
unmooring, berthing end) register with `NO_SOURCE_DATA` and their required event list.

These eight are the reconciliation targets and their definitions are confirmed correct — implement
them exactly:

| Metric | Definition |
|---|---|
| Turnaround | `vessel_call.ATD − vessel_call.ATA` |
| Anchorage Wait | `ANCHORAGE_ARRIVAL → PILOT_ON_BOARD_ARRIVAL` |
| Inward Movement | `PILOT_ON_BOARD_ARRIVAL → ALL_FAST_ARRIVAL` |
| Berth Stay | `ALL_FAST_ARRIVAL → LAST_LINE_UNTIED_SAILING` |
| Cargo Working | `CARGO_START → CARGO_END` |
| Outward Movement | `PILOT_ON_BOARD_SAILING → BREAKWATER_OUT` |
| Arrival Execution Delay | `Served_Time − Scheduled_Time`, Arrival + Pilotage Service |
| Sailing Execution Delay | `Served_Time − Scheduled_Time`, Sailing + Pilotage Service |

Port Stay convention (ETA-to-ATD vs ATA-to-ATD) is configurable and the chosen convention is
disclosed on every result. Default ATA-to-ATD per the assumptions register.

**Custom lead-time builder**: authorised users select any valid start and end event and get a
per-call and aggregated result. It must handle repeated occurrences (which occurrence? first, last,
nth, or all), movement scope, missing events, aggregation method, save and share, and formula version.

Aggregation dimensions, all of them: berth, cargo volume band, crane deployment, delay category,
day/week/month/quarter/year, movement type, pilot, pilotage/towage requirement, season, shipping line,
terminal, tug, VCN, vessel, vessel size band, vessel type, cargo type, port, source quality, incident
presence.

## 3. Statistics (spec §10.3)

Per eligible metric and cohort: observation count, missing count, mean, median, standard deviation,
coefficient of variation, min, max, P25, P75, P90, P95, fastest, slowest, identified outliers.

State the percentile method explicitly in the response (use linear interpolation and say so — the
oracle comparison will not care, but a reviewer will). Attach sample-size caveats below a configurable
n. Flag right-skew when mean exceeds median by the configured threshold.

Use Polars. Compute over the eligible population only, with quarantined records excluded by default
and any inclusion disclosed in the result envelope.

## 4. Stage contribution, variability, tail risk (spec §10.7)

- Contribution = stage duration / relevant total journey duration, with explicit handling that
  prevents double-counting overlapping stages. Report residual/unclassified time rather than forcing
  the components to 100%.
- CV = σ/μ, guarded for μ near zero.
- Tail Risk Ratio = P90 / median, guarded for zero or negative median.

## 5. Traceability envelope

Every analytics response returns, alongside the value: formula id and version, the source record ids
that contributed, the filters applied, the exclusions applied, the data-quality status of the inputs,
and the calculation timestamp. Spec §2 requires this of every displayed metric — building it into the
service response now means the dashboards in phases 11–12 get it for free.

## 6. Numerical care

Compare and round in hours to at least 6 decimal places internally; round for display only. The
reconciliation tolerance is ±0.02h and several fixture rows sit exactly on that boundary, so the
harness comparison must use `round(abs(actual − expected), 6) <= tolerance`. Build the comparison
helper here and reuse it in phase 10.

## Done when
All eight reconciliation metrics compute for every eligible call; unit tests cover null handling, zero
median, overlapping stages, daylight-saving boundaries, and early service preserving its sign; the
custom builder handles repeated occurrences; every result carries the traceability envelope;
`make validate` now reconciles the vessel-level metrics.
