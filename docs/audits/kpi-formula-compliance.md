# KPI Formula Compliance — FRD Section 5

**Authority:** `AI Tool Functional Requirement Document (FRD).docx`, §5 KPI
Calculation Engine. **Method:** every numbered KPI was compared with
`KPI_REGISTRY_DEFINITIONS`, `KPIEngine._compute_kpi_value`, `KPIFormulaVersion`,
canonical source fields, and `tests/test_kpi_engine.py`.

`v2.1` is the current FRD-aligned executable formula version. Existing `v1.0` and
`v2.0` results retain their stored version; this review does not relabel them. `NSD` below
means **NO_SOURCE_DATA**, never zero. Unless explicitly stated, event inputs are
canonical non-superseded/non-quarantined observations and population excludes merged
calls. Tests: `K` = KPI engine suite; `H` = hand-verified fixture test; `V` =
synthetic validation harness. The matrix identifies where per-KPI edge-case coverage
still needs expansion.

| KPI ID | KPI Name | FRD Formula | Implemented Formula | Required Inputs | Applicable Population | Unit | Current Status | Test Coverage | Discrepancy | Action |
|---:|---|---|---|---|---|---|---|---|---|---|
| 1 | Number of Vessel Calls | Count vessel calls | `COUNT(calls with ATA)` | ATA, VCN | All arrived calls | calls | IMPLEMENTED | K,H,V | FRD period wording relies on ATA | retain |
| 2 | Average Vessel Call Size | cargo / vessel calls | `SUM(unit quantity)/COUNT(distinct calls with unit)` | actual quantity, unit | all cargo calls, explicit unit | unit/call | IMPLEMENTED | K,H | no unqualified unit permitted | retain |
| 3 | Avg Pre-Berthing Waiting | POB − anchorage / vessels | average same | anchorage, POB | all eligible anchored calls | hours | IMPLEMENTED | K,H,V | none | retain |
| 4 | Pre-Berthing Delay | berth commencement − anchorage | avg first-line-tied − anchorage | anchorage, first line tied | all completed inward berthings | hours | IMPLEMENTED | K,V | none | retain |
| 5 | Anchorage Variation Index | stddev anchorage time by vessel type | sample stddev POB − anchorage for the governed `vessel_type` cohort | anchorage, POB, vessel type | all / a requested vessel-type cohort | hours | IMPLEMENTED | K,H | none; aggregation is one explicitly selected cohort at a time | retain |
| 6 | VTS Clearance Time | clearance / calls | NSD | VTS clearance | all | hours | NO_SOURCE_DATA | K | VTS feed absent | connect VTS log |
| 7 | Avg Inward Movement | All Fast − POB / berthed vessels | average same | POB, All Fast | berthed calls | hours | IMPLEMENTED | K,H,V | none | retain |
| 8 | Avg Inward Towage | towage duration / assisted vessels | `NO_SOURCE_DATA` | tug start, tug release/end | tug-assisted arrivals | hours | NO_SOURCE_DATA | K | tug release/end is absent; berth arrival is not a valid proxy | connect tug release log |
| 9 | Tug Availability | available tug hours / requested hours | NSD | tug availability + request hours | towage orders | % | NO_SOURCE_DATA | K | capacity ledger absent | connect tug availability |
| 10 | Pilot Availability | available pilot hours / requested hours | NSD | pilot roster + request hours | pilotage orders | % | NO_SOURCE_DATA | K,H | schedule/served delay is not availability | connect roster |
| 11 | Tug Response Time | tug arrival − request / requests | NSD | tug request, physical tug arrival | tug requests | hours | NO_SOURCE_DATA | K | served time is not arrival evidence | connect tug position/arrival |
| 12 | Pilot Boarding Time | pilot assignment → boarding / vessels | average scheduled-pilot → POB | pilot scheduled, POB | assigned pilotage calls | hours | IMPLEMENTED | K | none | add null/filter cases |
| 13 | Pilot-to-Berth Time | berthing − pilot boarding / movements | average All Fast − POB | POB, All Fast | piloted inward movements | hours | IMPLEMENTED | K,H,V | same event span as KPI-7, not an alias in FRD | retain distinct IDs |
| 14 | Berth Occupancy Rate | berth used / berth available ×100 | NSD | berth occupancy interval, berth inventory/availability | active berths | % | NO_SOURCE_DATA | K | four-berth constant removed | add berth inventory |
| 15 | Average Berthing Time | berth time / vessels | avg last-line-untied − All Fast | All Fast, berth departure | berthed calls | hours | IMPLEMENTED | K,H,V | none | retain |
| 16 | Berthing Variation Index | stddev(All Fast − POB) by vessel type | sample stddev for the governed `vessel_type` cohort | POB, All Fast, vessel type | all / a requested vessel-type cohort | hours | IMPLEMENTED | K | none; aggregation is one explicitly selected cohort at a time | retain |
| 17 | Avg Non-Working Time at Berth | non-working time / vessels | avg((All Fast→untied) − (cargo start→end)) | four events | berthed cargo calls | hours | IMPLEMENTED | K | FRD boundary ambiguity resolved explicitly in A-026/formula v2.1 | retain |
| 18 | Idle Time at Berth | idle / berth time ×100 | same using A-026 intervals | four events | berthed cargo calls | % | IMPLEMENTED | K | FRD boundary ambiguity resolved explicitly in A-026/formula v2.1 | retain |
| 19 | Number of Vessel Shifts | shifts per period | count every indexed SHIFT_PILOT_ON_BOARD→SHIFT_ALL_FAST pair | repeatable shift events | shifted calls | shifts | IMPLEMENTED | K,V | repeat occurrences now paired by `occurrence_index` with event IDs in lineage | retain |
| 20 | Shifting Time | shift durations / shifts | avg every indexed SHIFT_ALL_FAST − SHIFT_PILOT_ON_BOARD pair | repeatable shift events | shifted calls | hours | IMPLEMENTED | K,V | repeat occurrences now paired by `occurrence_index` with event IDs in lineage | retain |
| 21 | Berth Productivity | moves/(crane hours × cranes) | TEU moves / `working_hours × resources_deployed` | TEU, working hours, cranes | container vessels | moves/crane-hr | IMPLEMENTED | K,H | `working_hours` is elapsed operation time; individual crane-hours are explicit in formula v2.1 | retain |
| 22 | Berth Utilization Ratio | berth used / available ×100 | NSD | berth use and availability | all | % | NO_SOURCE_DATA | K | no berth capacity ledger | add inventory |
| 23 | Cargo Handled (MT) | sum cargo weight | `SUM(actual_quantity WHERE MT)` | MT actual quantity | cargo calls | MT | IMPLEMENTED | K | none | add unit/null cases |
| 24 | Container Traffic | sum loaded/unloaded/transshipped TEU | sum TEU where operation type is Load, Discharge/Unload, or Transshipment | TEU actual quantity, operation type | container calls | TEU | IMPLEMENTED | K,H | restows and unclassified TEU rows are explicitly excluded | retain |
| 25 | Voyage Productivity | total moves / vessel calls | TEU moves / container vessel calls | TEU actual quantity, type | container vessels | moves/call | IMPLEMENTED | K | none | add filtering case |
| 26 | First Container Lift | first lift − berthing / calls | NSD | first lift, All Fast | container vessels | hours | NO_SOURCE_DATA | K | first-lift event absent | connect TOS event |
| 27 | OSBD | cargo / berth-days | explicit-unit cargo / `(All Fast→untied)/24` | quantity, unit, berth interval | cargo calls, explicit unit | unit/berth-day | IMPLEMENTED | K | an explicit unit cohort is required to prevent incompatible-unit aggregation (A-026) | retain |
| 28 | Cranes per Vessel | cranes / vessels worked | avg deployed cranes on container ops | resources deployed | container vessels | cranes | IMPLEMENTED | K | operation-vs-vessel weighting needs business confirmation | add per-vessel aggregation test |
| 29 | Equipment Downtime | downtime / total equipment hours ×100 | downtime/(productive working+downtime) ×100 | working and downtime hours | equipment operations | % | IMPLEMENTED | K | total-equipment-hours interpretation is explicit in A-026/formula v2.1 | retain |
| 30 | Crane Moves/Hour/Crane | moves / crane working hours | TEU moves / `working_hours × resources_deployed` | TEU, work hours, cranes | container vessels | moves/crane-hr | IMPLEMENTED | K,H | none | add zero-denominator test |
| 31 | Import Dwell | exit − unloading / imports | NSD | discharge, exit, container ID | import containers | days | NO_SOURCE_DATA | K | yard/gate feed absent | connect TOS/gate |
| 32 | Export Dwell | loading − entry / exports | NSD | entry, loading, container ID | export containers | days | NO_SOURCE_DATA | K | yard/gate feed absent | connect TOS/gate |
| 33 | Yard Utilization | occupied/available capacity ×100 | NSD | occupied, capacity | yard | % | NO_SOURCE_DATA | K | source absent | connect yard TOS |
| 34 | Re-handling Rate | rehandles/containers | NSD | rehandles, moves | container yard | % | NO_SOURCE_DATA | K | source absent | connect yard TOS |
| 35 | Yard Productivity | moves/yard crane hours | NSD | moves, crane hours | container yard | moves/crane-hr | NO_SOURCE_DATA | K | source absent | connect yard TOS |
| 36 | Gate Truck Turnaround | exit − entry / trucks | NSD | gate entry/exit, truck ID | trucks | minutes | NO_SOURCE_DATA | K | source absent | connect gate system |
| 37 | Gate Transactions/Hour | transactions / operating hours | NSD | transactions, lane hours | gates | transactions/hr | NO_SOURCE_DATA | K | source absent | connect gate system |
| 38 | Truck Entry Wait | gate-in − arrival / trucks | NSD | arrival/gate-in, truck ID | trucks | minutes | NO_SOURCE_DATA | K | source absent | connect gate system |
| 39 | Rail Dwell | exit − arrival / rail containers | NSD | rail arrival/exit, container ID | rail containers | hours | NO_SOURCE_DATA | K | source absent | connect rail TOS |
| 40 | Rail Rake Handling | operation interval / rakes | NSD | rake start/end | rakes | hours | NO_SOURCE_DATA | K | source absent | connect rail TOS |
| 41 | Turnaround Time | departure − anchorage / vessels, specified exclusions | avg Breakwater Out − anchorage | anchorage, departure, exclusion flags when supplied | departed calls | hours | IMPLEMENTED | K,V | fixture supplies no litigation/repair exclusion flag; no proxy exclusion is applied and this is disclosed in A-027 | retain |
| 42 | Berth Turnaround | berth departure − berth arrival / vessels | avg untied − All Fast | All Fast, untied | berthed calls | hours | IMPLEMENTED | K,H,V | none | retain |
| 43 | Avg Outward Movement | berth → port limits / vessels | avg untied → Breakwater/Port Limit Out | untied, port limit out | departed calls | hours | IMPLEMENTED | K,H,V | none | retain |
| 44 | Avg Outward Towage | tug end − tug start / assisted vessels | NSD | sailing tug start/release | assisted departures | hours | NO_SOURCE_DATA | K | sailing tug release absent | connect tug release |
| 45 | Outward Movements/Day | departures / calendar days | count departure timestamps / reporting days | departure, period | departed calls | departures/day | IMPLEMENTED | K | explicit or observed period denominator disclosed | add period boundary test |
| 46 | Crane Availability | available/total crane hours ×100 | NSD | crane availability | container vessels | % | NO_SOURCE_DATA | K | source absent | connect SCADA |
| 47 | Moves/Gang Shift | moves/gang shifts | NSD | moves, gang shifts | container vessels | moves/gang-shift | NO_SOURCE_DATA | K | source absent | connect labour system |
| 48 | Unproductive Moves | unproductive/total ×100 | NSD | unproductive, total moves | container vessels | % | NO_SOURCE_DATA | K | source absent | connect crane log |
| 49 | Pilot Utilization | service hours/available pilot hours ×100 | NSD | service interval, roster availability | pilots | % | NO_SOURCE_DATA | K | constants removed | connect roster |
| 50 | Tug Utilization | service hours/available tug hours ×100 | NSD | service interval, fleet availability | tug fleet | % | NO_SOURCE_DATA | K | constants removed | connect fleet ledger |
| 51 | Berth Occupancy | vessel berth time/available berth time ×100 | alias of KPI-14, NSD | KPI-14 inputs | all berths | % | NO_SOURCE_DATA | K | source absent; alias retained | add inventory |
| 52 | Crane Utilization | working/available crane hours ×100 | NSD | work interval, availability | container vessels | % | NO_SOURCE_DATA | K | source absent | connect crane log |
| 53 | Avg Tug Response | tug arrival − request / requests | alias of KPI-11, NSD | KPI-11 inputs | tug requests | hours | NO_SOURCE_DATA | K | physical arrival absent; alias retained | connect position log |
| 54 | Avg Pilot Response | POB − pilot request / requests | average same | pilot request, POB | pilot requests | hours | IMPLEMENTED | K,V | none | add null/filter cases |
| 55 | Avg Crane Downtime | downtime/incidents | NSD | downtime incidents | crane operations | hours/incident | NO_SOURCE_DATA | K | incident count absent | connect CMMS |

## Findings and next actions

- **27 registry-computable / 28 `NO_SOURCE_DATA`:** `KPI-02` and `KPI-27`
  intentionally return `UNAVAILABLE` without an explicit unit, so an unfiltered
  scorecard has 27 computed, 26 NSD and 2 unavailable entries.
- **Aliasing is preserved:** KPI-11/53 and KPI-14/51 remain primary/alias pairs;
  aliases are excluded by default scorecards and keep `alias_of_id` lineage.
- **Formula/version lineage:** `ensure_kpi_registry` now creates `2.1` formula
  versions without deleting v1.0/v2.0 rows; new `KPIResult.formula_version` is 2.1.
- **Required regression work:** the existing suite covers registry, aliases, NSD,
  empty population, selected arithmetic and version attribution. Add parameterized
  normal/null/empty/zero-denominator/filter tests for each of the 29 computable
  definitions before treating every row as fully acceptance-tested.

## Release verification — 2026-09-22

The registry definition source contains **55** numbered FRD KPI definitions and
the executed result rows carry formula version `2.0`. The local database also
contains 58 pre-governance, unnumbered legacy KPI rows (`KPI_1`… and lead-time
aliases) alongside the 55 governed rows. They must not be counted as the FRD
registry or displayed in a governed scorecard. They were not deleted during this
release review because that would destroy historical lineage without an approved
retirement/migration plan.

All 55 entries now have a defensible terminal availability/compliance status:
`IMPLEMENTED`, `NO_SOURCE_DATA`, or `UNAVAILABLE` for an empty/missing-input
cohort. All prior non-terminal findings were resolved without proxies: KPI-08 is now `NO_SOURCE_DATA` pending a tug
release feed; KPI-19/20 use repeat occurrence pairing; and the FRD ambiguities
are explicit in the assumptions register and formula v2.1. The positive checks
below are release evidence, not a replacement for the full regression run:

- `make validate`: PASS (72/72 base calls, 8/8 reconciled metrics, 10/10 DQ
  cases, 41/41 delays, dashboard reconciliation 7/7).
- Formula versions: historical persisted KPI results retain `2.0`; post-remediation
  results are attributed to `2.1`.
- Availability: source-limited KPIs remain `NO_SOURCE_DATA`; no zero values are
  fabricated for absent governed inputs.
