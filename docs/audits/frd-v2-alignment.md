# FRD v2 alignment — sections 4.2.1, 4.4.3 and 4.4.6

Authoritative source: `AI Tool Functional Requirement Document (FRD) - v2.docx`.
This audit covers only the three revised sections and records unavailable inputs
instead of substituting values.

## 4.2.1 data definitions and standardisation

`config/frd_v2_data_dictionary.yaml` is the machine-readable registry. It has
all 21 vessel/cargo attributes, all 135 marine-event attributes, and all 31
berth attributes from the revised tables, including their FRD datatypes. Source
headings are normalized by `StandardizationRegistry`; movement-scoped aliases
require an explicit Arrival, Shifting, or Sailing context.

The current architecture remains intentionally extensible:

- typed vessel master fields hold the FRD master attributes; `license_number`
  was added and the already-present port, commodity, draft and call-sign fields
  are now mapped by ingestion;
- timestamp events use the governed `EventDefinition` + `EventOccurrence`
  timestamp envelope, so new event types do not need one database column each;
- operation/resource text travels in the event `attributes` envelope;
- berth/cargo extensions travel in `CargoOperation.attributes`, while the
  existing typed cargo fields remain unchanged;
- the original source file, sheet, row and cell values remain in raw/staging
  lineage irrespective of whether a canonical value is available.

The governed synthetic source currently supplies only a subset (14 vessel,
26 event and 8 berth fields). Registered fields absent from a source remain
`NO_SOURCE_DATA`; no value is generated. Ambiguous names such as Requested,
Scheduled and Served are resolved only when the movement scope is present.

## 4.4.3 service delay definitions

The canonical service model stores all four concepts independently:

| Concept | Canonical field | Formula/result |
|---|---|---|
| Request submission | `ServiceRequest.submission_time` | source only; never substituted |
| Requested | `ServiceRequest.requested_time` | source only |
| Scheduled | `ServiceAssignment.scheduled_time` | source only |
| Actual | `ServiceExecution.served_time` | source only |
| Planning Lead Time | persisted/calculated service timing | Requested − Submission |
| Scheduling Gap | persisted/calculated service timing | Scheduled − Requested |
| Execution Delay | persisted/calculated service timing | Actual − Scheduled |

Planning Lead Time is `UNAVAILABLE` when submission time is absent; Scheduling
Gap and Execution Delay remain independently computable. Negative Execution
Delay remains Early Service.

Delay Frequency is calculated independently for Arrival/Inward,
Sailing/Outward and Shifting from eligible scheduled/actual pairs. Its formula
is delayed events (`Execution Delay > 0`) divided by eligible events × 100.
Bands are exact: `<40` Acceptable/Green, `40–60` Watch/Orange, and `>60`
Critical/Red. The Delays & Bottlenecks cards always use the full active governed
dataset and are not affected by table-only filters.

`service_type` is a governed string rather than an enum, so pilotage, towage,
berthing and later port-defined services such as fresh water or garbage removal
use the same four-timestamp model without creating fake records.

## 4.4.6 outlier and exception analysis

Pre-v2 persisted turnaround outliers retain their original database row,
benchmark, exclusion decision and audit identity. The API read model exposes
those rows as `Time-based Outlier`, which is unambiguous from the governed
metric, and hydrates a human-readable issue, `Historical threshold` label,
legacy-rule reason and an explicit unavailable journey-leg label. Where the
persisted row lacks source IDs, the read model resolves them from the governed
Turnaround lead-time result. It does not relabel the legacy benchmark as P90 or
rewrite historical data. Legacy rows are regenerated with `OUT-V2-001` and its
linear P90 threshold on the next governed dataset processing run.

`config/outlier_rules.yaml` contains all 43 revised scenarios and the five FRD
categories. The evaluator is deterministic and tenant-scoped. Default high and
low thresholds are linear-interpolation P90 and P30; Anchorage Waiting uses P95
and Pilot Boarding/Mooring control limits use historical mean + three sample
standard deviations. Results expose rule ID, category, issue, vessel, metric,
observed value, benchmark, reason, movement leg, severity and source IDs.

Implemented executable definitions: **18** (13 time-based, 2 sequence,
1 data-quality and 2 operational-performance). Three repeated FRD concepts are
registered as aliases to the single evaluated signal, preventing duplicate UI
flags: OUT-V2-019→024, OUT-V2-020→012 and OUT-V2-043→015. There are currently
no executable resource-utilization rules because the required governed resource
capacity/norm/interval data is not present.

### Unsupported or unavailable inputs

| Rules | Missing governed inputs |
|---|---|
| OUT-V2-005 | First Crane Movement |
| OUT-V2-008 | configured pilot-to-berth service standard |
| OUT-V2-009, 036 | governed weather observations/normalization |
| OUT-V2-014 | departure clearance timestamp |
| OUT-V2-016 | designated pilot boundary event |
| OUT-V2-017, 018 | resource capacity, vessel-class tug norm/requirement |
| OUT-V2-021–023 | berth, pilot and tug availability history |
| OUT-V2-027 | governed channel distance/speed |
| OUT-V2-029 | marine-services-complete event |
| OUT-V2-030 | stable pilot/tug resource IDs with service intervals |
| OUT-V2-033 | unambiguous governed actual-berthing event selection |
| OUT-V2-035 | tidal window and readiness |
| OUT-V2-037 | cargo stoppage events |
| OUT-V2-038 | productive activity intervals |
| OUT-V2-040 | crane hours and terminal productivity benchmark |
| OUT-V2-041 | pilot boat start/transfer observations in the active source |

OUT-V2-003 and OUT-V2-039 have component values in some sources but remain
`UNAVAILABLE` until governed vessel-size and comparable cargo-volume cohort
bands are configured. This avoids silently inventing peer groups.

Migration `q5r6s7t8u9v0` is additive. It adds the extensible canonical envelopes
and structured, tenant-indexed outlier evidence. Existing lineage is neither
rewritten nor deleted.
