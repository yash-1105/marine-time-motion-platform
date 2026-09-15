# Requirements Traceability Matrix

| REQ-ID | Spec section | Requirement (one line) | Planned module | Planned test | Status |
|---|---|---|---|---|---|
| REQ-001 | 1. PRODUCT MISSION | Ingests fragmented data from port and terminal systems, files, APIs, databases, ... | ingestion | test_req_001 | NOT_STARTED |
| REQ-002 | 1. PRODUCT MISSION | Standardises vessel, cargo, berth, resource, incident, and event records into a ... | Core | test_req_002 | NOT_STARTED |
| REQ-003 | 1. PRODUCT MISSION | validates completeness, timestamp accuracy, chronology, operational logic, dupli... | Core | test_req_003 | NOT_STARTED |
| REQ-004 | 1. PRODUCT MISSION | Resolves identities and consolidates source records into one governed vessel-cal... | identity | test_identity_engine | IMPLEMENTED |
| REQ-005 | 1. PRODUCT MISSION | Reconstructs each vessel's end-to-end journey from pre-arrival through regulator... | journey | test_req_005 | NOT_STARTED |
| REQ-006 | 1. PRODUCT MISSION | Separates elapsed lead time, waiting time, service time, planning gaps, schedule... | analytics | test_all_9_duration_semantics_concepts | IMPLEMENTED |
| REQ-007 | 1. PRODUCT MISSION | Calculates marine, berth, terminal, cargo, yard, gate, rail, departure, coordina... | kpi | test_req_007 | BACKLOG |
| REQ-008 | 1. PRODUCT MISSION | Identifies delays, bottlenecks, process deviations, stage contribution, instabil... | Core | test_req_008 | NOT_STARTED |
| REQ-009 | 1. PRODUCT MISSION | Provides role-specific dashboards, drill-downs, vessel journey replay, automated... | reporting | test_req_009 | NOT_STARTED |
| REQ-010 | 1. PRODUCT MISSION | Maintains lineage, confidence, provenance, correction history, approval state, a... | Core | test_req_010 | NOT_STARTED |
| REQ-011 | 4. USERS, ROLES, AND AUTHORISATION | Platform Administrator: tenants/ports, users, roles, configuration, integrations... | Core | test_req_011 | NOT_STARTED |
| REQ-012 | 4. USERS, ROLES, AND AUTHORISATION | Data Steward: mappings, aliases, quality rules, exceptions, merge/unmerge, corre... | quality | test_req_012 | NOT_STARTED |
| REQ-013 | 4. USERS, ROLES, AND AUTHORISATION | Marine Operations Controller: live movements, resources, alerts, operational upd... | Core | test_req_013 | NOT_STARTED |
| REQ-014 | 4. USERS, ROLES, AND AUTHORISATION | Analyst: exploratory time-motion analysis, custom event pairs, statistical analy... | analytics | test_custom_builder_handles_event_pairs_and_repeated_occurrences | IMPLEMENTED |
| REQ-015 | 4. USERS, ROLES, AND AUTHORISATION | Department Head: KPI, delay, resource, and operational dashboards; comments and ... | kpi | test_req_015 | NOT_STARTED |
| REQ-016 | 4. USERS, ROLES, AND AUTHORISATION | Executive: read-only executive dashboard, management reports, critical risks, tr... | reporting | test_req_016 | NOT_STARTED |
| REQ-017 | 4. USERS, ROLES, AND AUTHORISATION | Report Manager: templates, schedules, distribution lists, publication workflow.... | Core | test_req_017 | NOT_STARTED |
| REQ-018 | 4. USERS, ROLES, AND AUTHORISATION | Auditor: read-only lineage, version history, calculation evidence, access and co... | Core | test_req_018 | NOT_STARTED |
| REQ-019 | 4. USERS, ROLES, AND AUTHORISATION | Integration Service Account: scoped machine access with rotated credentials.... | Core | test_req_019 | NOT_STARTED |
| REQ-020 | 7. MODULE 1: DATA INGESTION | Connector catalogue and connection test.... | Core | test_req_020 | NOT_STARTED |
| REQ-021 | 7. MODULE 1: DATA INGESTION | Drag-and-drop file import with preview.... | Core | test_req_021 | NOT_STARTED |
| REQ-022 | 7. MODULE 1: DATA INGESTION | Sheet/table selection.... | Core | test_req_022 | NOT_STARTED |
| REQ-023 | 7. MODULE 1: DATA INGESTION | Encoding, delimiter, header-row, decimal, date-format, and timezone detection.... | Core | test_req_023 | NOT_STARTED |
| REQ-024 | 7. MODULE 1: DATA INGESTION | Source-field-to-canonical mapping UI.... | Core | test_req_024 | NOT_STARTED |
| REQ-025 | 7. MODULE 1: DATA INGESTION | Reusable import templates and version history.... | Core | test_req_025 | NOT_STARTED |
| REQ-026 | 7. MODULE 1: DATA INGESTION | Dry-run validation before commit.... | Core | test_req_026 | NOT_STARTED |
| REQ-027 | 7. MODULE 1: DATA INGESTION | Batch progress, row counts, accepted/rejected/quarantined records, and error dow... | Core | test_req_027 | NOT_STARTED |
| REQ-028 | 7. MODULE 1: DATA INGESTION | Idempotency and replay without duplicate creation.... | Core | test_req_028 | NOT_STARTED |
| REQ-029 | 7. MODULE 1: DATA INGESTION | Incremental and full refresh modes.... | Core | test_req_029 | NOT_STARTED |
| REQ-030 | 7. MODULE 1: DATA INGESTION | Schema-drift detection and approval workflow.... | Core | test_req_030 | NOT_STARTED |
| REQ-031 | 7. MODULE 1: DATA INGESTION | Original file preservation and checksum.... | Core | test_req_031 | NOT_STARTED |
| REQ-032 | 7. MODULE 1: DATA INGESTION | OCR image segmentation, extracted value, confidence, bounding box, human verific... | Core | test_req_032 | BACKLOG |
| REQ-033 | 7. MODULE 1: DATA INGESTION | API/webhook ingestion with authentication, throttling, retries, dead-letter queu... | ingestion | test_req_033 | NOT_STARTED |
| REQ-034 | Pre-arrival and anchorage | Number of Vessel Calls: count unique vessel arrivals per period.... | Core | test_req_034 | NOT_STARTED |
| REQ-035 | Pre-arrival and anchorage | Average Vessel Call Size: total cargo in TEU or tonnes / vessel calls; never mix... | Core | test_req_035 | NOT_STARTED |
| REQ-036 | Pre-arrival and anchorage | Average Pre-Berthing Waiting Time: total pre-berthing wait / eligible vessels.... | Core | test_req_036 | NOT_STARTED |
| REQ-037 | Pre-arrival and anchorage | Pre-Berthing Delay: Berth Commencement - Anchorage Arrival.... | Core | test_req_037 | NOT_STARTED |
| REQ-038 | Pre-arrival and anchorage | Anchorage Time Variation Index: standard deviation of Pilot Boarding - Anchorage... | Core | test_req_038 | NOT_STARTED |
| REQ-039 | Pre-arrival and anchorage | VTS Clearance Time: average Anchorage Arrival to VTS Clearance.... | Core | test_req_039 | NOT_STARTED |
| REQ-040 | Inward movement | Average Inward Movement Time: Pilot On Board at anchorage to All Fast.... | Core | test_req_040 | NOT_STARTED |
| REQ-041 | Inward movement | Average Inward Towage Duration: tug service duration / assisted vessels or servi... | Core | test_req_041 | NOT_STARTED |
| REQ-042 | Inward movement | Tug Availability: available tug hours / requested tug hours * 100.... | Core | test_req_042 | NOT_STARTED |
| REQ-043 | Inward movement | Pilot Availability: available pilot hours / requested pilot hours * 100.... | Core | test_req_043 | NOT_STARTED |
| REQ-044 | Inward movement | Tug Response Time: average Tug Arrival - Tug Request.... | Core | test_req_044 | NOT_STARTED |
| REQ-045 | Inward movement | Pilot Boarding Time: average Pilot On Board - Pilot Assigned.... | Core | test_req_045 | NOT_STARTED |
| REQ-046 | Inward movement | Pilot-to-Berth Time: average All Fast/Berthing - Pilot On Board.... | Core | test_req_046 | NOT_STARTED |
| REQ-047 | Berthing and at berth | Berth Occupancy Rate: occupied berth hours / available berth hours * 100.... | Core | test_req_047 | NOT_STARTED |
| REQ-048 | Berthing and at berth | Average Berthing Time: total berth stay / vessel count.... | Core | test_req_048 | NOT_STARTED |
| REQ-049 | Berthing and at berth | Berthing Time Variation Index: standard deviation of All Fast - Pilot On Board, ... | Core | test_req_049 | NOT_STARTED |
| REQ-050 | Berthing and at berth | Average Non-Working Time at Berth: total non-working berth time / vessels.... | Core | test_req_050 | NOT_STARTED |
| REQ-051 | Berthing and at berth | Idle Time at Berth: idle time / total berth time * 100.... | Core | test_req_051 | NOT_STARTED |
| REQ-052 | Berthing and at berth | Number of Vessel Shifts.... | Core | test_req_052 | NOT_STARTED |
| REQ-053 | Berthing and at berth | Shifting Time: shift durations / completed shifts.... | Core | test_req_053 | NOT_STARTED |
| REQ-054 | Berthing and at berth | Berth Productivity: container moves / crane-hours, ensuring the formula does not... | Core | test_req_054 | NOT_STARTED |
| REQ-055 | Berthing and at berth | Berth Utilisation Ratio: used berth hours / available berth hours * 100.... | Core | test_req_055 | NOT_STARTED |
| REQ-056 | Cargo handling | Cargo Handled in MT.... | Core | test_req_056 | NOT_STARTED |
| REQ-057 | Cargo handling | Container Traffic in TEUs: loaded + unloaded + transshipped, with configured tre... | Core | test_req_057 | NOT_STARTED |
| REQ-058 | Cargo handling | Voyage Productivity: total moves / vessel calls.... | Core | test_req_058 | NOT_STARTED |
| REQ-059 | Cargo handling | First Container Lift Time: average First Container Lift - Berthing/All Fast, con... | Core | test_req_059 | NOT_STARTED |
| REQ-060 | Cargo handling | Average Ship Berth-Day Output: cargo handled / berth-days.... | Core | test_req_060 | NOT_STARTED |
| REQ-061 | Cargo handling | Number of Cranes per Vessel.... | Core | test_req_061 | NOT_STARTED |
| REQ-062 | Cargo handling | Equipment Downtime: downtime / total equipment time * 100.... | Core | test_req_062 | NOT_STARTED |
| REQ-063 | Cargo handling | Crane Moves per Hour per Crane: total moves / summed productive crane-hours.... | Core | test_req_063 | NOT_STARTED |
| REQ-064 | Yard operations | Import Container Dwell Time: exit - unloading.... | Core | test_req_064 | NOT_STARTED |
| REQ-065 | Yard operations | Export Container Dwell Time: loading - entry.... | Core | test_req_065 | NOT_STARTED |
| REQ-066 | Yard operations | Yard Utilisation Rate: occupied capacity / total capacity * 100.... | Core | test_req_066 | BACKLOG |
| REQ-067 | Yard operations | Container Re-handling Rate: re-handles / handled containers.... | Core | test_req_067 | NOT_STARTED |
| REQ-068 | Yard operations | Yard Productivity: yard moves / yard crane-hours.... | Core | test_req_068 | BACKLOG |
| REQ-069 | Gate and landside | Truck Gate Turnaround: exit - entry.... | Core | test_req_069 | NOT_STARTED |
| REQ-070 | Gate and landside | Gate Transactions per Hour.... | Core | test_req_070 | NOT_STARTED |
| REQ-071 | Gate and landside | Truck Waiting at Entry: gate-in - gate-arrival.... | Core | test_req_071 | NOT_STARTED |
| REQ-072 | Gate and landside | Rail Dwell Time.... | Core | test_req_072 | NOT_STARTED |
| REQ-073 | Gate and landside | Rail Rake Handling Time.... | Core | test_req_073 | NOT_STARTED |
| REQ-074 | Departure and turnaround | Turnaround Time: departure - anchorage arrival, with governed exclusions such as... | Core | test_req_074 | NOT_STARTED |
| REQ-075 | Departure and turnaround | Berth Turnaround: berth departure - berth arrival/all fast.... | Core | test_req_075 | NOT_STARTED |
| REQ-076 | Departure and turnaround | Average Outward Movement: berth departure to Port Limit Out.... | Core | test_req_076 | NOT_STARTED |
| REQ-077 | Departure and turnaround | Average Outward Towage Duration.... | Core | test_req_077 | NOT_STARTED |
| REQ-078 | Departure and turnaround | Outward Movements per Day.... | Core | test_req_078 | NOT_STARTED |
| REQ-079 | Operational efficiency and coordination | Crane Availability Ratio.... | Core | test_req_079 | NOT_STARTED |
| REQ-080 | Operational efficiency and coordination | Average Moves per Gang Shift.... | Core | test_req_080 | NOT_STARTED |
| REQ-081 | Operational efficiency and coordination | Unproductive Moves Ratio.... | Core | test_req_081 | NOT_STARTED |
| REQ-082 | Resource utilisation | Pilot Utilisation: pilot service hours / available scheduled pilot hours * 100.... | Core | test_req_082 | NOT_STARTED |
| REQ-083 | Resource utilisation | Tug Utilisation: tug service hours / available tug operational hours * 100.... | Core | test_req_083 | NOT_STARTED |
| REQ-084 | Resource utilisation | Berth Occupancy: vessel berth time / available berth time * 100.... | Core | test_req_084 | NOT_STARTED |
| REQ-085 | Resource utilisation | Crane Utilisation: productive crane working hours / available crane hours * 100,... | Core | test_req_085 | NOT_STARTED |
| REQ-086 | Resource utilisation | Average Tug Response: average Tug Arrival - Request.... | Core | test_req_086 | NOT_STARTED |
| REQ-087 | Resource utilisation | Average Pilot Response: average Pilot On Board - Request.... | Core | test_req_087 | NOT_STARTED |
| REQ-088 | Resource utilisation | Average Crane Downtime: total downtime / incidents, with optional vessel-level t... | Core | test_req_088 | NOT_STARTED |
| REQ-089 | 13. AI-POWERED REPORTING | Daily Operations: movements, anchorage, pilotage, towage, berth, cargo progress,... | reporting | test_reporting_daily_operations | IMPLEMENTED |
| REQ-090 | 13. AI-POWERED REPORTING | Weekly Marine Performance: turnaround, pilot/tug, berth, delays, resources, bott... | reporting | test_reporting_templates_registered | DEFERRED |
| REQ-091 | 13. AI-POWERED REPORTING | Monthly Management Review: KPIs, throughput, turnaround, delays, utilisation, cr... | kpi | test_req_091 | NOT_STARTED |
| REQ-092 | 13. AI-POWERED REPORTING | Quarterly KPI Review: full scorecards, targets, trends, variance, rankings, bott... | kpi | test_req_092 | NOT_STARTED |
| REQ-093 | 13. AI-POWERED REPORTING | Benchmark Performance: internal/historical/peer comparison where available, gaps... | Core | test_req_093 | NOT_STARTED |
| REQ-094 | 20. ACCEPTANCE CRITERIA | At least one file-based and one API/database ingestion path work end to end.... | ingestion | test_req_094 | NOT_STARTED |
| REQ-095 | 20. ACCEPTANCE CRITERIA | Source fields can be mapped and reused through versioned templates.... | Core | test_req_095 | NOT_STARTED |
| REQ-096 | 20. ACCEPTANCE CRITERIA | Raw evidence is immutable and every canonical value is traceable.... | Core | test_req_096 | NOT_STARTED |
| REQ-097 | 20. ACCEPTANCE CRITERIA | Duplicate vessel-call candidates are explainable and merge/unmerge is auditable.... | identity | test_identity_engine | IMPLEMENTED |
| REQ-098 | 20. ACCEPTANCE CRITERIA | Required chronology and logical rules flag seeded violations correctly without t... | Core | test_req_098 | NOT_STARTED |
| REQ-099 | 20. ACCEPTANCE CRITERIA | A vessel call can be reconstructed across pre-arrival, arrival, berth/cargo, shi... | Core | test_req_099 | NOT_STARTED |
| REQ-100 | 20. ACCEPTANCE CRITERIA | Custom lead time between any two eligible events works per call and aggregated c... | Core | test_req_100 | NOT_STARTED |
| REQ-101 | 20. ACCEPTANCE CRITERIA | Statistical metrics and P75/P90 are correct against golden data.... | Core | test_req_101 | NOT_STARTED |
| REQ-102 | 20. ACCEPTANCE CRITERIA | Negative execution delay is shown as early service.... | Core | test_req_102 | NOT_STARTED |
| REQ-103 | 20. ACCEPTANCE CRITERIA | Delay causes distinguish confirmed and inferred.... | Core | test_req_103 | NOT_STARTED |
| REQ-104 | 20. ACCEPTANCE CRITERIA | Bottleneck and criticality calculations expose component scores.... | Core | test_req_104 | NOT_STARTED |
| REQ-105 | 20. ACCEPTANCE CRITERIA | All 55 source KPIs exist in a governed registry, including duplicate/alias treat... | kpi | test_req_105 | NOT_STARTED |
| REQ-106 | 20. ACCEPTANCE CRITERIA | Executive, Operations, KPI, Delay, Vessel Journey, and Data Quality dashboards f... | kpi | test_req_106 | NOT_STARTED |
| REQ-107 | 20. ACCEPTANCE CRITERIA | Word, Excel, PowerPoint, and PDF reporting works for at least one report templat... | reporting | test_reporting_daily_operations | IMPLEMENTED |
| REQ-108 | 20. ACCEPTANCE CRITERIA | Copilot answers are grounded, scoped, reproducible, caveated, and linked to supp... | copilot | test_copilot_core | IMPLEMENTED |
| REQ-109 | 20. ACCEPTANCE CRITERIA | Role permissions, audit logs, accessibility, test suite, migrations, backups, ob... | security | test_security_hardening | PARTIALLY_IMPLEMENTED |
| REQ-110 | 20. ACCEPTANCE CRITERIA | There are no placeholder controls, fabricated production metrics, or unlabelled ... | Core | test_req_110 | NOT_STARTED |
| REQ-111 | 21A.1 Dataset files and expected package handling | Require an authorised administrator or developer role.... | Core | test_req_111 | NOT_STARTED |
| REQ-112 | 21A.1 Dataset files and expected package handling | Label the data as synthetic in all environments and screens.... | Core | test_req_112 | NOT_STARTED |
| REQ-113 | 21A.1 Dataset files and expected package handling | Prevent synthetic data from being confused or combined with production data.... | Core | test_req_113 | NOT_STARTED |
| REQ-114 | 21A.1 Dataset files and expected package handling | Import using the same ingestion, mapping, validation, lineage, journey reconstru... | kpi | test_req_114 | NOT_STARTED |
| REQ-115 | 21A.1 Dataset files and expected package handling | Be idempotent. Re-importing the same workbook must not unintentionally multiply ... | Core | test_req_115 | NOT_STARTED |
| REQ-116 | 21A.1 Dataset files and expected package handling | Allow complete removal/reset of the synthetic dataset without affecting other da... | Core | test_req_116 | NOT_STARTED |
| REQ-117 | 21A.1 Dataset files and expected package handling | Display an import summary with accepted, rejected, quarantined, duplicate, merge... | identity | test_identity_engine | IMPLEMENTED |
| REQ-118 | 21A.1 Dataset files and expected package handling | Preserve workbook name, worksheet name, row number, ingestion batch, checksum, a... | ingestion | test_req_118 | NOT_STARTED |
| REQ-119 | DQ_Cases | `DQ-001`: exact duplicate vessel-call record. Expect duplicate detection and pre... | identity | test_fixture_consolidation_reconciles_to_72 | IMPLEMENTED |
| REQ-120 | DQ_Cases | `DQ-002`: probable duplicate identity with punctuation variation and the same VC... | identity | test_fixture_consolidation_reconciles_to_72 | IMPLEMENTED |
| REQ-121 | DQ_Cases | `DQ-003`: missing ATA. Expect a missing-mandatory-timestamp issue and dependent ... | Core | test_req_121 | NOT_STARTED |
| REQ-122 | DQ_Cases | `DQ-004`: ETA after ATA. Expect an `ETA before ATA` chronology violation.... | Core | test_req_122 | NOT_STARTED |
| REQ-123 | DQ_Cases | `DQ-005`: pilot request exists but pilot scheduled event is absent. Expect a mis... | Core | test_req_123 | NOT_STARTED |
| REQ-124 | DQ_Cases | `DQ-006`: pilot on board occurs before scheduled time by an intentionally invali... | Core | test_req_124 | NOT_STARTED |
| REQ-125 | DQ_Cases | `DQ-007`: positive delay with missing reason/category. Expect mandatory delay-re... | Core | test_req_125 | NOT_STARTED |
| REQ-126 | DQ_Cases | `DQ-008`: extreme 720-hour expected turnaround outlier. Expect extreme-delay/out... | Core | test_req_126 | NOT_STARTED |
| REQ-127 | DQ_Cases | `DQ-009`: orphan event with `VCN = SYNVCN-NOTFOUND`. Expect referential-integrit... | Core | test_req_127 | NOT_STARTED |
| REQ-128 | DQ_Cases | `DQ-010`: two conflicting ATA values separated by five hours. Expect conflict de... | Core | test_req_128 | NOT_STARTED |
| REQ-129 | 21A.3 Required automated dataset test harness | Reset or create an isolated synthetic test tenant/dataset.... | Core | test_req_129 | NOT_STARTED |
| REQ-130 | 21A.3 Required automated dataset test harness | Ingest `VesselCalls`, `Events`, `Services`, `CargoOps`, and `Delays` through the... | ingestion | test_req_130 | NOT_STARTED |
| REQ-131 | 21A.3 Required automated dataset test harness | Load `ExpectedOutputs`, `DQ_Cases`, and `ValidationSummary` into the isolated te... | Core | test_req_131 | NOT_STARTED |
| REQ-132 | 21A.3 Required automated dataset test harness | Execute mapping, standardisation, identity matching, duplicate detection, chrono... | kpi | test_req_132 | NOT_STARTED |
| REQ-133 | 21A.3 Required automated dataset test harness | Produce a machine-readable reconciliation result and a human-readable test repor... | Core | test_req_133 | NOT_STARTED |
| REQ-134 | 21A.3 Required automated dataset test harness | Compare actual and expected outputs by VCN and metric.... | Core | test_req_134 | NOT_STARTED |
| REQ-135 | 21A.3 Required automated dataset test harness | List passed, failed, unavailable, excluded, and tolerance-exceeded comparisons.... | Core | test_req_135 | NOT_STARTED |
| REQ-136 | 21A.3 Required automated dataset test harness | Verify every DQ case produced the expected rule, severity, disposition, and work... | Core | test_req_136 | NOT_STARTED |
| REQ-137 | 21A.3 Required automated dataset test harness | Confirm valid negative delays remain negative and are labelled early service.... | Core | test_req_137 | NOT_STARTED |
| REQ-138 | 21A.3 Required automated dataset test harness | Confirm duplicate and variant rows do not inflate vessel-call, throughput, delay... | kpi | test_req_138 | NOT_STARTED |
| REQ-139 | 21A.3 Required automated dataset test harness | Confirm quarantined critical records are excluded by default and disclosed if in... | Core | test_req_139 | NOT_STARTED |
| REQ-140 | 21A.3 Required automated dataset test harness | Retain execution time, application version, formula version, rule version, datas... | Core | test_req_140 | NOT_STARTED |
| REQ-141 | 21A.5 Dataset-specific acceptance criteria | The workbook imports through the normal ingestion UI/API without manual database... | ingestion | test_req_141 | NOT_STARTED |
| REQ-142 | 21A.5 Dataset-specific acceptance criteria | Every transactional worksheet has a reusable source mapping.... | Core | test_req_142 | NOT_STARTED |
| REQ-143 | 21A.5 Dataset-specific acceptance criteria | The base valid population is reconstructed without duplicate inflation.... | Core | test_req_143 | NOT_STARTED |
| REQ-144 | 21A.5 Dataset-specific acceptance criteria | All ten documented DQ scenarios produce the expected system outcome.... | Core | test_req_144 | NOT_STARTED |
| REQ-145 | 21A.5 Dataset-specific acceptance criteria | Vessel-level calculated metrics match `ExpectedOutputs` within tolerance for eli... | Core | test_req_145 | NOT_STARTED |
| REQ-146 | 21A.5 Dataset-specific acceptance criteria | Negative execution delays remain negative and appear as early service.... | Core | test_req_146 | NOT_STARTED |
| REQ-147 | 21A.5 Dataset-specific acceptance criteria | Missing or invalid required events make dependent outputs unavailable, rather th... | Core | test_req_147 | NOT_STARTED |
| REQ-148 | 21A.5 Dataset-specific acceptance criteria | The orphan event is rejected or quarantined.... | Core | test_req_148 | NOT_STARTED |
| REQ-149 | 21A.5 Dataset-specific acceptance criteria | Conflicting ATA observations remain traceable and require governed resolution.... | Core | test_req_149 | NOT_STARTED |
| REQ-150 | 21A.5 Dataset-specific acceptance criteria | The dashboard, API, report, and database totals reconcile under identical filter... | reporting | test_req_150 | NOT_STARTED |
| REQ-151 | 21A.5 Dataset-specific acceptance criteria | The synthetic-data flag is visible and synthetic data cannot be mistaken for pro... | Core | test_req_151 | NOT_STARTED |
| REQ-152 | 21A.5 Dataset-specific acceptance criteria | A validation report can be rerun after any code, rule, mapping, or KPI formula c... | kpi | test_req_152 | NOT_STARTED |
| REQ-153 | 22. AUTONOMOUS BUILD SEQUENCE | Parse this specification into a requirements traceability matrix.... | Core | test_req_153 | NOT_STARTED |
| REQ-154 | 22. AUTONOMOUS BUILD SEQUENCE | Create assumptions and decisions register.... | Core | test_req_154 | NOT_STARTED |
| REQ-155 | 22. AUTONOMOUS BUILD SEQUENCE | Define architecture, boundaries, data model, event catalogue, quality rules, and... | kpi | test_req_155 | NOT_STARTED |
| REQ-156 | 22. AUTONOMOUS BUILD SEQUENCE | Scaffold repository, authentication, authorisation, configuration, database, log... | Core | test_req_156 | NOT_STARTED |
| REQ-157 | 22. AUTONOMOUS BUILD SEQUENCE | Build ingestion and lineage first.... | ingestion | test_req_157 | NOT_STARTED |
| REQ-158 | 22. AUTONOMOUS BUILD SEQUENCE | Build mapping, quality, exception, and consolidation workflows.... | quality | test_req_158 | NOT_STARTED |
| REQ-159 | 22. AUTONOMOUS BUILD SEQUENCE | Build journey reconstruction and event timeline.... | journey | test_req_159 | NOT_STARTED |
| REQ-160 | 22. AUTONOMOUS BUILD SEQUENCE | Build analytics, KPI, benchmark, trend, bottleneck, outlier, and criticality eng... | kpi | test_req_160 | NOT_STARTED |
| REQ-161 | 22. AUTONOMOUS BUILD SEQUENCE | Build dashboards and drill-through.... | reporting | test_req_161 | NOT_STARTED |
| REQ-162 | 22. AUTONOMOUS BUILD SEQUENCE | Build reporting and copilot using the governed services.... | Core | test_req_162 | NOT_STARTED |
| REQ-163 | 22. AUTONOMOUS BUILD SEQUENCE | Load and use `Synthetic_Marine_Time_Motion_Test_Data.xlsx` as the primary synthe... | Core | test_req_163 | NOT_STARTED |
| REQ-164 | 22. AUTONOMOUS BUILD SEQUENCE | Run the synthetic validation harness, reconcile calculated results against `Expe... | Core | test_req_164 | NOT_STARTED |
| REQ-165 | 22. AUTONOMOUS BUILD SEQUENCE | Provide a final implementation report containing completed items, test evidence,... | Core | test_req_165 | NOT_STARTED |
