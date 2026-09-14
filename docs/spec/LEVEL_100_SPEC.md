# LEVEL 100 MASTER BUILD PROMPT
## AI-Powered Port Marine Operations Time Release / Time and Motion Analytics Platform

You are an autonomous principal software architect, marine-port domain analyst, data engineer, AI/ML engineer, UX lead, security engineer, QA lead, DevOps engineer, and technical writer. Build a production-grade, enterprise-ready web application for end-to-end marine operations time-and-motion analysis. Do not build a toy, static mock-up, dashboard-only prototype, or disconnected collection of screens. Build a coherent, secure, auditable, configurable, testable platform in which ingestion, data quality, vessel-call consolidation, journey reconstruction, duration and delay analytics, KPI calculation, dashboards, reporting, and conversational analytics operate on the same governed data model.

This prompt is the controlling implementation specification. Where a requirement is ambiguous, do not silently omit it. Record the ambiguity in an Assumptions and Decisions Register, implement a configurable default, expose the setting to administrators where appropriate, and add a test. Never invent production data. Seeded data must be clearly labelled synthetic.

---

# 1. PRODUCT MISSION

Create an AI-powered Port Marine Operations Time Release / Time and Motion Analytics Platform that:

1. Ingests fragmented data from port and terminal systems, files, APIs, databases, PDFs, scanned registers, and logbooks.
2. Standardises vessel, cargo, berth, resource, incident, and event records into a canonical schema.
3. validates completeness, timestamp accuracy, chronology, operational logic, duplicates, conflicts, and outliers.
4. Resolves identities and consolidates source records into one governed vessel-call record.
5. Reconstructs each vessel's end-to-end journey from pre-arrival through regulatory clearances, inward movement, anchorage, pilotage, towage, berthing, cargo operations, shifting, unberthing, outward movement, and departure.
6. Separates elapsed lead time, waiting time, service time, planning gaps, schedule variance, execution delay, and early service delivery.
7. Calculates marine, berth, terminal, cargo, yard, gate, rail, departure, coordination, and resource-utilisation KPIs.
8. Identifies delays, bottlenecks, process deviations, stage contribution, instability, tail risk, outliers, resource constraints, and probable root causes.
9. Provides role-specific dashboards, drill-downs, vessel journey replay, automated reports, alerts, and an evidence-grounded conversational copilot.
10. Maintains lineage, confidence, provenance, correction history, approval state, and auditability for every value used in analysis.

The product must evolve a one-off Time and Motion Study into a continuously operating Marine Operations Intelligence System and a historical digital twin of vessel movements.

---

# 2. NON-NEGOTIABLE IMPLEMENTATION BEHAVIOUR

- Do not use placeholder buttons, empty cards, fake charts, hard-coded KPI values, dead links, or screens disconnected from working services.
- Every displayed metric must be traceable to its formula, source records, filters, exclusions, data-quality status, and calculation version.
- Every timestamp must retain original value, parsed value, source timezone, standard timezone, capture method, confidence, source system, record identifier, ingestion batch, and correction history.
- Preserve negative delays as early-service signals. Do not automatically convert them to zero or classify them as invalid.
- Do not use AI-inferred events or delay causes as verified facts. Mark them visibly as AI-inferred, provide confidence and evidence, and support human confirmation or rejection.
- Do not merge potential vessel calls merely because vessel names are similar. Use deterministic and probabilistic matching with explainable confidence and configurable auto-merge thresholds.
- Do not calculate downstream KPIs from quarantined or unresolved critical-quality records unless an authorised user explicitly includes them. Disclose the inclusion.
- Design every list for filtering, sorting, pagination, search, saved views, column selection, export, and deep linking.
- Use timezone-aware date-time types. Store in UTC and retain local port timezone semantics.
- Use configurable event definitions, aliases, sequence rules, KPI formulas, thresholds, targets, benchmark sets, criticality scoring bands, roles, report schedules, and retention policies.
- Support desktop-first operational use, large control-room displays, and responsive tablet use. Mobile may be view-focused.
- Meet WCAG 2.2 AA, including keyboard navigation, focus states, semantic labels, colour-independent statuses, chart descriptions, and adequate contrast.

---

# 3. DEFAULT TECHNICAL ARCHITECTURE

If the coding environment does not impose a stack, use this modular reference architecture:

- Front end: React + TypeScript, Next.js, accessible component library, responsive CSS, server-state query library, robust table/grid, charting, and timeline visualisation.
- API: Python FastAPI with OpenAPI 3.1, Pydantic validation, asynchronous jobs, and domain-oriented service modules.
- Primary database: PostgreSQL with schemas for raw, staging, canonical, analytics, audit, and configuration data.
- Cache and job coordination: Redis.
- Workflow/background processing: Celery, Dramatiq, or equivalent durable task system.
- Object storage: S3-compatible storage for original uploads, OCR output, generated reports, and evidence artifacts.
- Analytics: SQL transformations and Python data pipelines using Polars or Pandas; use statistically sound libraries for percentiles, correlations, regressions, anomaly detection, and confidence metrics.
- Search: PostgreSQL full-text search initially; optional OpenSearch when scale requires it.
- Authentication: enterprise OIDC/OAuth2, Microsoft Entra ID compatible; local development provider only for development.
- Authorisation: RBAC plus port/terminal-level data scope.
- Observability: structured logs, metrics, traces, health checks, job telemetry, alerting, and audit events.
- Deployment: Docker containers, environment-specific configuration, infrastructure-as-code, automated migrations, CI/CD, backups, and disaster-recovery documentation.

Use a modular monolith for the initial POC unless scale or deployment constraints justify services. Keep boundaries clean enough to extract ingestion, analytics, reporting, and copilot services later. Provide an Architecture Decision Record for major choices.

---

# 4. USERS, ROLES, AND AUTHORISATION

Implement at minimum:

1. Platform Administrator: tenants/ports, users, roles, configuration, integrations, security, retention.
2. Data Steward: mappings, aliases, quality rules, exceptions, merge/unmerge, corrections, approvals.
3. Marine Operations Controller: live movements, resources, alerts, operational updates, event confirmation.
4. Analyst: exploratory time-motion analysis, custom event pairs, statistical analysis, cohorts, exports.
5. Department Head: KPI, delay, resource, and operational dashboards; comments and action tracking.
6. Executive: read-only executive dashboard, management reports, critical risks, trends.
7. Report Manager: templates, schedules, distribution lists, publication workflow.
8. Auditor: read-only lineage, version history, calculation evidence, access and correction logs.
9. Integration Service Account: scoped machine access with rotated credentials.

Permissions must be action-based and data-scoped. Include view, create, edit, approve, reject, merge, unmerge, recalculate, publish, export, configure, administer, and audit permissions. Sensitive operational exports require explicit permission and must be logged.

---

# 5. CORE INFORMATION ARCHITECTURE

Primary navigation:

- Home / Executive Overview
- Live Operations
- Vessel Calls
- Vessel Journey
- Time and Motion Analysis
- KPIs
- Delays and Bottlenecks
- Resources
- Data Quality
- Data Ingestion
- Reports
- Copilot
- Alerts and Actions
- Master Data
- Configuration
- Administration
- Audit and Lineage

Provide global date range, port, terminal, berth, vessel type, movement type, shipping line, vessel size, cargo type, and data-quality filters. Persist filter context during drill-down and encode it in the URL.

---

# 6. CANONICAL DOMAIN MODEL

Model the following entities with UUID primary keys, created/updated timestamps, source lineage, soft-delete where appropriate, and optimistic concurrency:

- Tenant, Port, Terminal, Berth, Anchorage, GeographicZone, TimezoneConfiguration.
- Vessel, VesselAlias, VesselType, ShippingLine, Flag, PortReference.
- VesselCall, Voyage, Movement, Operation, VesselCallStatus.
- CargoManifest, CargoItem, Commodity, ContainerSummary, CargoOperation.
- EventDefinition, EventAlias, EventOccurrence, EventEvidence, EventCorrection, EventConfidence.
- Stakeholder, Organisation, VesselAgent, PortControl, PFSO, MarineSafety, PHO, MRCC, MSCC, Immigration, Customs, PoliceAndPortSecurity, TerminalOperator.
- ServiceRequest, ServiceAssignment, ServiceExecution.
- Pilot, PilotShift, PilotAssignment, PilotBoat, PilotageOperation.
- Tug, TugShift, TugAssignment, TugServiceOperation.
- BerthingMaster, MooringCrew, MooringOperation.
- Crane, CraneAssignment, CraneMovementSummary, CraneDowntime.
- Incident, IncidentCategory, AffectedResource, IncidentResolution.
- Delay, DelayCategory, DelayReason, DelayInference, DelayAllocation.
- DataSource, DataOwner, Connector, SourceSchema, SourceField, CanonicalMapping.
- IngestionBatch, RawRecord, StagingRecord, ParseError, OCRArtifact.
- QualityRule, QualityIssue, QualityScore, ResolutionDecision.
- MatchCandidate, MatchEvidence, MergeDecision, ConsolidatedRecord.
- JourneyTemplate, JourneyStage, JourneyInstance, StageOccurrence, Handover.
- LeadTimeDefinition, LeadTimeResult, KPI, KPIFormulaVersion, KPIResult, Target, Benchmark.
- StatisticalAggregate, BottleneckResult, CriticalityResult, TrendResult, OutlierResult.
- DashboardPreference, SavedView, AlertRule, Alert, ActionItem.
- ReportTemplate, ReportRun, ReportSchedule, DistributionRecord.
- User, Role, Permission, DataScope, AuditEvent.

## 6.1 Vessel and cargo master attributes

The canonical model must support: License Number, IMO Number, VCN, Vessel Name, Vessel Type, Vessel Size in TEUs, Flag, Last Port of Call, Next Port of Call, Port of Lading, Port of Discharge, Reason for Visit, Cargo Type, Commodity, Quantity, GRT, LOA, DWT, Forward Draft, Aft Draft, Call Sign. Apply suitable constraints, units, decimal precision, and master-data references.

## 6.2 Canonical event catalogue

Implement configurable event definitions that cover all events below. Avoid a single wide table with hundreds of timestamp columns as the only design. Use an event-occurrence model, with typed domain projections or views where they improve query performance.

### Pre-arrival and clearance
Nomination Details Submission; ISPS Submission; ISPS Clearance; PHO Submission; PHO Issuance; IMDG Submission; IMDG Issuance; ETA; ATA; Anchorage Arrival; Anchor Drop; Anchor Aweigh; Port Limit In; Port Limit Out; Movement Type; Operation Type.

### Arrival pilotage and pilot boat
Pilot Request, Pilot Assigned, Pilot Name, Pilot Boat Assigned, Pilot Boat Start, Pilot Boat End, Pilotage Start, Pilot On Board, Breakwater In, Pilot Disembark, Return Pilot Boat Assigned, Return Pilot Boat Start, Return Pilot Boat End, Pilotage End.

### Arrival tug services
For Tug 1 and Tug 2: Request, Name, Assigned, Arrival, Service Start, Line-Up, Line-Down, Service End. The design must support an arbitrary number of tugs, even though common views show Tug 1, Tug 2, and Tug 3.

### Arrival berthing
Berth Name, Berthing Master Name, Planned Berthing Time, First Line Tied, Stern Line Tied, Last Line Tied, All Fast.

### Shifting
Pilot Request, Pilot Assigned, Pilot Name, Pilot Boat Assigned/Start/End, Pilotage Start, Pilot On Board, From Location, To Location; an arbitrary number of tug request/assignment/arrival/start/line-up/line-down/end records; berth, berthing master, planned berthing time, first/stern/last line tied, all fast, pilot disembark, return pilot boat details, pilotage end.

### Sailing and outward movement
ETD; pilot request, assignment, name, pilot boat assignment/start/end, pilotage start, pilot on board; Tug 1/Tug 2 and optional Tug 3 request/assignment/arrival/name/service start/line-up/line-down/service end; First Line Untied; Last Line Untied; departure from berth; Breakwater Out; pilot disembark; return pilot boat details; pilotage end; Port Limit Out; ATD.

### Berth and cargo events
Customs Inspection Start/End; Stevedores Onboard/Offboard; Unlashing Start/End; Cargo Operations Start/End; First/Last Crane Movement; First/Last Container Movement Loaded; First/Last Container Movement Unloaded; crane downtime start/end; Lashing Start/End; number of cranes deployed; crane identifiers; total container moves; total crane moves; TEUs loaded/unloaded/transshipped/restowed; Stowaway Search Start/End; Immigration Inspection Start/End; Berthing End.

### Incident events
Incident Reporting/Start; Incident Type; affected equipment, asset, or manpower; response time; resolution time; status; impact; linked vessel call, berth, service, and resource.

## 6.3 Source-to-canonical aliases

Seed an editable mapping dictionary, including:

- Nomination Details Submission: Nomination Date, Submission Date.
- Pilot Request/Assigned/Start/On Board/Off Board/End for arrival, shifting, and sailing: map numbered variants such as Pilot Request Time 1/2/3, Pilot Assigned Time 1/2/3, Pilotage Start Time 1/2/3, Pilot On-Board 1/2/3, Pilot Off-Board 1/2/3, Pilotage End Time 1/2/3, plus Requested Time, Scheduled Time, Actual Scheduled Date/Time, Served Date and Time as appropriate.
- From Location: From Loc. To Location: To Loc.
- Port Limit In: Port Limits.
- Last Port of Call: Last Port. Next Port of Call: Next Port.
- ETA: Expected Time of Arrival. ATA: Actual Time of Arrival. ETD: Expected Time of Departure. ATD: Actual Time of Departure.

Support exact, case-insensitive, normalised, regex, and AI-assisted mapping suggestions. AI suggestions require confirmation before becoming production mappings.

---

# 7. MODULE 1: DATA INGESTION

Build connectors and import workflows for:

- Port Management System (PMS)
- Vessel Traffic System / Vessel Traffic Management System (VTS/VTMS), including AIS/geofence events where available
- Terminal Operating System (TOS), including systems such as Navis N4 where applicable
- Tug Management System
- Pilot Management System
- Berth Planning System
- Incident Management System
- Excel, CSV, PDF, REST/SOAP API, database, SFTP, email attachment, and manual upload
- Scanned hard-copy registers/logbooks through OCR and human verification

Hard-copy templates must cover Pilot Blue Book times for pilot boarding/disembarking during arrival, shifting, and sailing; Tug Master Logbook line-up and line-down during arrival, shifting, and sailing; Berthing Logbook first/last line tied or untied; and Marine Incident Register start, type, affected resource, and resolution.

For each source configure system name, data owner, connection type, upload frequency, file format, mandatory and optional fields, source unique identifier, timestamp format, source timezone, refresh frequency, credentials reference, schema version, expected volume, data sensitivity, and SLA.

Create:

1. Connector catalogue and connection test.
2. Drag-and-drop file import with preview.
3. Sheet/table selection.
4. Encoding, delimiter, header-row, decimal, date-format, and timezone detection.
5. Source-field-to-canonical mapping UI.
6. Reusable import templates and version history.
7. Dry-run validation before commit.
8. Batch progress, row counts, accepted/rejected/quarantined records, and error download.
9. Idempotency and replay without duplicate creation.
10. Incremental and full refresh modes.
11. Schema-drift detection and approval workflow.
12. Original file preservation and checksum.
13. OCR image segmentation, extracted value, confidence, bounding box, human verification, and attachment to evidence.
14. API/webhook ingestion with authentication, throttling, retries, dead-letter queue, and replay.

---

# 8. MODULE 2: DATA QUALITY, VALIDATION, AND CLEANSING

Implement a configurable rule engine with rule version, scope, severity, effective dates, pass/fail logic, exception permission, and remediation guidance.

## 8.1 Standardisation

- Trim and normalise whitespace and punctuation without destroying original values.
- Normalise vessel names for matching while retaining display names.
- Standardise dates to `yyyy-MM-dd HH:mm` for display, with seconds and offset available when supplied.
- Standardise units for TEU, tonnes, GRT, DWT, LOA, draft, minutes, and hours.
- Harmonise vessel type, movement type, berth, terminal, cargo type, service category, resource names, and delay categories.
- Prevent silent precision loss.

## 8.2 Identity and vessel-call matching

Use deterministic keys first: VCN, IMO, call sign, source call ID, voyage, port, arrival window. Then use probabilistic comparison of normalised vessel name, ETA/ATA windows, berth, agent, and voyage data.

Example expected behaviour: `MSC AURORA`, `MSC AURORA.`, and `MSC-AURORA` may receive a 98% match score, but the decision must show evidence. Configurable defaults:

- >= 0.98 with no key conflict: auto-merge.
- 0.85 to 0.9799: steward review.
- < 0.85: retain separately.
- Any conflicting IMO/VCN: never auto-merge.

Provide side-by-side compare, survivorship rules by source priority/recency/completeness, merge preview, merge audit, and safe unmerge.

## 8.3 Completeness and duplicate checks

Detect duplicate fields, source rows, events, VCNs, vessel calls, and repeated batches. Detect missing mandatory data according to vessel type, movement, stage, and KPI dependency. Example: Pilot Request exists but Pilot Assigned is missing, severity High.

## 8.4 Timestamp and sequence validation

Represent chronology as a directed acyclic graph with conditional and parallel branches, not a single rigid line. Validate only rules applicable to the movement and available events.

Seed these rules:

- ETA before ATA, ETD, and ATD.
- Port Limit In before Pilot On Board and Breakwater In.
- Pilot Assigned before Pilotage Start, Pilot On Board, Pilot Disembark, and Pilotage End.
- Pilotage Start before Pilot On Board.
- Arrival Pilot On Board before Breakwater In.
- Tug Arrival after the relevant request and normally after Pilot On Board; allow configurable port-specific exceptions.
- Tug Line-Up after Tug Arrival.
- Tug Line-Down after Last Line Tied for arrival, and after relevant unmooring milestones for departure.
- Pilot Disembark after Last Line Tied for arrival.
- All start times before corresponding end times.
- Service Start after Service Request.
- First Line Tied before Last Line Tied before All Fast.
- First Crane Movement before Last Crane Movement.
- Departure Pilot On Board before Breakwater Out.
- Departure Pilot Disembark before Breakwater Out, if this is the configured local process; otherwise permit a port-specific rule override.
- Breakwater Out before Port Limit Out.
- When actual time exceeds scheduled/target time, Delay Reason is mandatory or the record must be flagged.
- Pilotage chain: Request < Assigned < Start < On Board < Disembark < End.
- Berthing chain: First Line Tied < Last Line Tied < All Fast.

Also validate the extended intended sequence from nomination/clearances through ETA, port-limit entry, ATA/anchorage, pilot and tug arrival activities, berthing, shifting, cargo, sailing, breakwater out, port-limit out, and ATD. Parallel activities must not create false violations.

## 8.5 Anomaly detection

Flag missing timestamps, duplicates, negative durations where invalid, unrealistic times, blank values, inconsistent identifiers, wrong event order, missing reasons, conflicts between sources, missing requested/scheduled/served fields, and statistical outliers. A negative delay is not a negative duration error when it represents early delivery.

Classify issues as Info, Low, Medium, High, or Critical and as Data Quality, Operational Sequence, Identity, Completeness, Duplicate, Conflict, Outlier, or Policy. Provide owner, status, age, due date, comments, evidence, resolution, and approval.

## 8.6 Data quality score

Calculate transparent completeness, validity, consistency, uniqueness, timeliness, and lineage scores. Show score by batch, source, field, vessel call, period, and domain. Do not hide event-level issues behind an average score.

---

# 9. MODULE 3: VESSEL JOURNEY RECONSTRUCTION

Construct a chronological event graph for every vessel call. The default reference flow is:

Pre-arrival -> Regulatory Clearances -> ETA/ATA -> Anchorage -> Arrival Service Request -> Pilot Boarding -> Breakwater In -> Towage -> Berthing -> Pilot Disembark -> Health/Immigration/Customs clearances as applicable -> Cargo Operations -> Lashing/Unlashing -> Optional Shifting -> Unberthing -> Departure Service Request -> Departure Pilot Boarding -> Towage -> Pilot Disembark -> Breakwater Out -> Port Limit Out -> ATD.

Incorporate the operational swimlane stages and actors, including Vessel Agent, TNPA Port Control/PFSO/Marine Safety, terminal/DCT, PHO, MRCC/MSCC, vessel, immigration, police and port security, pilots, tug masters, mooring team, berthing master, customs, and terminal cargo teams. Support milestones from T-21, T-14, T-7, T-5, T-3 days, 24/4/2 hours before ETA, 12 NM, 6 NM ETA/ATA, 2.5 NM, fairway buoy, breakwater in, berth, load/unload, outward clearance, unmooring, breakwater out, and sailing. Treat these offsets as configurable templates, not universal hard-coded rules.

Model process branches:

- IMDG cargo requires IMDG clearance.
- Deep-sea vessel may submit COPRAR and inbound EDI; coastal vessel may submit inbound EDI.
- All required clearances determine continuation; failures may halt operations or move the vessel aside.
- Cargo loading/unloading, outward clearances, stowaway check, customs readiness, and departure readiness precede sailing.
- Shifting may occur zero, one, or multiple times.

For each vessel call generate:

- Unified chronological timeline.
- Stage grouping and durations.
- Actual versus standard path.
- Missing and inferred events.
- Source confidence and conflicts.
- Stakeholder handovers and wait between handovers.
- Active service, passive wait, hold, delay, and unclassified time.
- Operational deviation report.
- Journey map and playable timeline.
- AI-generated factual summary with citations to internal records.
- Versioned reconstruction history.

Manual corrections must not overwrite raw data. Create a corrected canonical observation with reason, user, timestamp, and approval state.

---

# 10. MODULE 4: TIME AND MOTION ANALYTICS

## 10.1 Duration semantics

Implement and clearly distinguish:

- Lead Time = End actual timestamp - Start actual timestamp.
- Planning Lead Time = Requested service time - request submission time.
- Scheduling Gap = Scheduled time - requested time.
- Execution Delay = actual service time - scheduled time.
- Target Variance = actual duration/time - target duration/time.
- Waiting Time = inactive interval awaiting prerequisite/resource/clearance.
- Service Time = interval during which the service is actively executed.
- Delay Frequency = delayed eligible events / total eligible events.
- Early Delivery = negative execution delay.

All formulas require eligibility, null handling, unit, timezone, exclusions, and versioning.

## 10.2 Lead-time catalogue

Seed standard calculations:

- Port Stay: ETA or ATA to ATD, with the selected convention disclosed.
- Anchorage Waiting: Anchorage Arrival to Pilot On Board.
- Pilot Response: Pilot Request to Pilot On Board.
- Inward Movement: Pilot On Board to All Fast.
- Berth Stay: All Fast to Departure from Berth.
- Cargo Operation: First Crane Movement to Last Crane Movement.
- Departure Movement: Departure Pilot On Board to Breakwater Out or ATD.
- ETA to ATA; ATA to Anchorage Arrival; Anchorage Arrival to Anchor Drop; Anchor Drop to Anchor Aweigh; Anchorage Arrival to Pilot Request; Pilot Request to Pilot Assigned; Pilot Assigned to Pilot On Board; Pilot On Board to Breakwater In; Breakwater In to All Fast; Breakwater In to First Line Tied; First Line Tied to Last Line Tied; Last Line Tied to All Fast; All Fast to First Crane Movement; All Fast to First Container Movement; First to Last Crane Movement; Last Crane Movement to Lashing End; Last Crane Movement to Berthing End; Last Container Movement to ATD; Berthing End to Unmooring Start; Unmooring Start to End; Unmooring End to Departure from Berth; Unmooring End to Breakwater Out; Departure from Berth to Breakwater Out; Breakwater Out to ATD; Port Limit In to Breakwater In; ETA to ETD; ATA to ATD.

Provide a custom lead-time builder where authorised users select any valid start and end events, handling repeated occurrences, movement scope, missing events, aggregation, save/share, and formula version.

Aggregate by berth, cargo volume, crane deployment, delay category, day/week/month/quarter/year, movement type, pilot, pilotage/towage requirement, season, shipping line, terminal, tug, VCN, vessel, vessel size, vessel type, cargo type, port, source quality, and incident presence.

## 10.3 Statistics

For each eligible metric and cohort calculate observation count, missing count, mean, median, standard deviation, coefficient of variation, minimum, maximum, P25, P75, P90, P95 where configured, fastest, slowest, and identified outliers. State percentile method and sample-size caveats. Flag right-skew when mean materially exceeds median according to a configurable threshold.

## 10.4 Delay cause analysis

Seed delay categories: Pilot, Tug, Berth Non-Availability, Weather, Regulatory Clearance, Terminal Readiness, Cargo Operation, Equipment Breakdown, Crane Downtime, Mooring, Documentation, Vessel-Side, Port-Side, External/Uncontrollable, and Other.

Allow multiple causes with duration allocation and primary/secondary designation. When reasons are absent, infer probable cause only from evidence such as stage, late request, resource availability, berth occupancy, weather data if integrated, incident data, and terminal readiness. Output proposed cause, confidence, factors supporting/opposing, and human review state.

## 10.5 Bottlenecks

Score bottlenecks from duration, frequency, variability, tail risk, turnaround contribution, repeated target breach, and business criticality. Detect resource bottlenecks such as pilot/tug/crane shortage and berth congestion, as well as process bottlenecks such as waits, clearances, and repeated delays. Never label the longest stage alone as the bottleneck.

## 10.6 Outliers and exceptions

Detect turnaround above P90, pilot boarding delay beyond configurable sigma or robust MAD threshold, cargo duration unusual for vessel size/volume, tug before pilot where invalid, late first crane move after all fast, impossible chronology, and high-criticality cases. Classify as Operational Outlier, Data Quality Outlier, Process Violation, Extreme Delay Case, or High-Criticality Case.

## 10.7 Stage contribution, variability, and tail risk

- Contribution = stage duration / relevant total journey duration, preventing double-counting overlapping stages.
- CV = standard deviation / mean where mean is non-zero and meaningful.
- Tail Risk Ratio = P90 / median where median is positive; handle zero/negative safely.
- Provide decomposition and residual/unclassified time.

## 10.8 Operational criticality

Calculate Duration, Variability, and Tail-Risk scores from 1 to 5 using configurable thresholds. Overall score = arithmetic mean of the three by default, with optional governed weights.

- 1.0-1.9 Low
- 2.0-2.9 Moderate
- 3.0-3.9 High
- 4.0-5.0 Critical

Show component scores and do not display a black-box score.

## 10.9 Targets, benchmarks, and trends

Compare actuals with internal targets, historical periods, prior month/quarter/year, vessel category, berth, terminal, and peer-port benchmarks where licensed/available. Record benchmark source and period. Use Green/Amber/Red bands with configurable tolerances. Trends must support daily, weekly, monthly, quarterly, and annual grains, baseline comparison, rolling averages, seasonality, and improving/deteriorating/stable classification.

---

# 11. KPI ENGINE

Create a versioned KPI registry with name, business definition, formula, numerator, denominator, units, eligible population, required fields/events, exclusions, aggregation method, vessel applicability, target, thresholds, owner, effective dates, and lineage. Seed all KPIs below.

## Pre-arrival and anchorage
1. Number of Vessel Calls: count unique vessel arrivals per period.
2. Average Vessel Call Size: total cargo in TEU or tonnes / vessel calls; never mix units.
3. Average Pre-Berthing Waiting Time: total pre-berthing wait / eligible vessels.
4. Pre-Berthing Delay: Berth Commencement - Anchorage Arrival.
5. Anchorage Time Variation Index: standard deviation of Pilot Boarding - Anchorage Arrival, segmented by vessel type.
6. VTS Clearance Time: average Anchorage Arrival to VTS Clearance.

## Inward movement
7. Average Inward Movement Time: Pilot On Board at anchorage to All Fast.
8. Average Inward Towage Duration: tug service duration / assisted vessels or services, with denominator choice disclosed.
9. Tug Availability: available tug hours / requested tug hours * 100.
10. Pilot Availability: available pilot hours / requested pilot hours * 100.
11. Tug Response Time: average Tug Arrival - Tug Request.
12. Pilot Boarding Time: average Pilot On Board - Pilot Assigned.
13. Pilot-to-Berth Time: average All Fast/Berthing - Pilot On Board.

## Berthing and at berth
14. Berth Occupancy Rate: occupied berth hours / available berth hours * 100.
15. Average Berthing Time: total berth stay / vessel count.
16. Berthing Time Variation Index: standard deviation of All Fast - Pilot On Board, by/across vessel type.
17. Average Non-Working Time at Berth: total non-working berth time / vessels.
18. Idle Time at Berth: idle time / total berth time * 100.
19. Number of Vessel Shifts.
20. Shifting Time: shift durations / completed shifts.
21. Berth Productivity: container moves / crane-hours, ensuring the formula does not multiply by crane count twice if crane-hours are already summed.
22. Berth Utilisation Ratio: used berth hours / available berth hours * 100.

## Cargo handling
23. Cargo Handled in MT.
24. Container Traffic in TEUs: loaded + unloaded + transshipped, with configured treatment of restows.
25. Voyage Productivity: total moves / vessel calls.
26. First Container Lift Time: average First Container Lift - Berthing/All Fast, configured and disclosed.
27. Average Ship Berth-Day Output: cargo handled / berth-days.
28. Number of Cranes per Vessel.
29. Equipment Downtime: downtime / total equipment time * 100.
30. Crane Moves per Hour per Crane: total moves / summed productive crane-hours.

## Yard operations
31. Import Container Dwell Time: exit - unloading.
32. Export Container Dwell Time: loading - entry.
33. Yard Utilisation Rate: occupied capacity / total capacity * 100.
34. Container Re-handling Rate: re-handles / handled containers.
35. Yard Productivity: yard moves / yard crane-hours.

## Gate and landside
36. Truck Gate Turnaround: exit - entry.
37. Gate Transactions per Hour.
38. Truck Waiting at Entry: gate-in - gate-arrival.
39. Rail Dwell Time.
40. Rail Rake Handling Time.

## Departure and turnaround
41. Turnaround Time: departure - anchorage arrival, with governed exclusions such as litigation/repairs.
42. Berth Turnaround: berth departure - berth arrival/all fast.
43. Average Outward Movement: berth departure to Port Limit Out.
44. Average Outward Towage Duration.
45. Outward Movements per Day.

## Operational efficiency and coordination
46. Crane Availability Ratio.
47. Average Moves per Gang Shift.
48. Unproductive Moves Ratio.

## Resource utilisation
49. Pilot Utilisation: pilot service hours / available scheduled pilot hours * 100.
50. Tug Utilisation: tug service hours / available tug operational hours * 100.
51. Berth Occupancy: vessel berth time / available berth time * 100.
52. Crane Utilisation: productive crane working hours / available crane hours * 100, subtracting validated downtime where required.
53. Average Tug Response: average Tug Arrival - Request.
54. Average Pilot Response: average Pilot On Board - Request.
55. Average Crane Downtime: total downtime / incidents, with optional vessel-level total downtime / worked vessel calls.

Detect and document overlapping/duplicated KPIs such as Tug Response 11/53 and Berth Occupancy 14/51. Preserve source KPI numbers for traceability, but allow an administrator to designate a primary KPI and aliases so dashboards do not double-count.

---

# 12. DASHBOARDS AND USER EXPERIENCES

## 12.1 Executive Dashboard

Cards and visualisations: vessel calls, turnaround, throughput with unambiguous unit, delays, critical risks, target status, trend arrows, top bottlenecks, criticality heatmap, data-quality confidence, and AI executive narrative. Every card drills to evidence.

## 12.2 Live Operations Dashboard

Show active vessels, anchorage queue, berth plan and occupancy, upcoming movements, pilots/tugs available and assigned, active incidents, overdue events, clearances, resource conflicts, and map/timeline if geospatial data exists. Distinguish live, delayed, stale, manually entered, and inferred observations. Provide refresh timestamp and degraded-data warning.

## 12.3 KPI Dashboard

KPI catalogue, scorecards, trend, actual vs target, benchmarks, variance, period-over-period, filters, cohort comparison, definition drawer, formula/lineage, and drill-through to underlying calls.

## 12.4 Delay and Bottleneck Dashboard

Delay cause Pareto, stage heatmap, frequency distribution, duration distribution, bottleneck ranking, criticality components, P90 tail risk, resource capacity relationship, stage contribution, trend, inferred vs confirmed causes, and action tracking.

## 12.5 Vessel Journey Dashboard

Search/select a vessel call and display arrival, pilotage, towage, berthing, cargo, shifting, and departure. Include swimlane by stakeholder, event timestamp, source icon, confidence, duration ribbons, waits, delays, clearances, handovers, anomalies, actual vs standard path, raw evidence drawer, corrections, and replay controls. Enable export of one-vessel journey report.

## 12.6 Data Quality Dashboard

Scores by source/field/batch/domain, issue aging, high-criticality queue, duplicate candidates, mapping coverage, schema drift, unresolved conflicts, missing event matrix, trend, and remediation throughput.

## 12.7 Time and Motion Explorer

Custom event-pair analysis, cohort filters, distribution chart, box plot, histogram, trend, scatter plot, summary statistics, outlier table, compare cohorts, save analysis, export, and explain methodology.

Use accessible chart palettes, tooltips, legends, units, sample sizes, data-quality warnings, and downloadable underlying data.

---

# 13. AI-POWERED REPORTING

Generate PDF, Excel, PowerPoint, and Word on demand and by daily/weekly/monthly/quarterly schedule. Support templates, port branding, version, reporting period, author/system, approval, distribution by email/notification/document repository, retry, delivery log, and access control.

Reports:

1. Daily Operations: movements, anchorage, pilotage, towage, berth, cargo progress, delays, incidents, resources, exceptions, attention list.
2. Weekly Marine Performance: turnaround, pilot/tug, berth, delays, resources, bottlenecks, targets, recent history, actions.
3. Monthly Management Review: KPIs, throughput, turnaround, delays, utilisation, criticality, trends, drivers, risks, recommendations.
4. Quarterly KPI Review: full scorecards, targets, trends, variance, rankings, bottlenecks, sustained issues/improvements.
5. Benchmark Performance: internal/historical/peer comparison where available, gaps, strengths, opportunities, and recommendations.

AI narrative must be generated only from calculated facts, cite metric IDs and vessel-call evidence internally, state period/filter, distinguish correlation from causation, disclose weak data, and avoid fabricated explanations.

---

# 14. CONVERSATIONAL AI / COPILOT

Implement retrieval and tool-based analytics over authorised governed data. The copilot must not answer operational questions from model memory when a database calculation is required.

Support questions such as highest turnaround vessels, causes of increasing pilot boarding time, delays by berth, vessel-type comparison, highest variability stage, top bottlenecks, management summary, tug delay report, P90 arrival lead time, SLA breaches, and relationships between vessel size/berth time, berth occupancy/pre-berthing delay, crane deployment/cargo time, cargo volume/turnaround, season/delay, and tug response/inward movement.

Each answer must contain:

- Direct answer.
- Reporting period and filters.
- Supporting metric and definition.
- Relevant vessel calls/records.
- Chart or table where useful.
- Explanation and evidence.
- Data-quality caveat.
- Suggested operational action.
- Method note for statistical claims.

For relationship questions, provide sample size, missingness, correlation method, coefficient, uncertainty/significance where appropriate, segmented checks, confounder warning, and explicit statement that correlation does not establish causation. Never repeat the example claim that occupancy above 85% increases waiting by 42% unless current data actually produces it.

Support follow-up context, saved conversations, export, feedback, citation deep-links, role-safe responses, prompt-injection resistance from uploaded files, and complete audit logging. Never expose data outside the user's scope.

---

# 15. ALERTS, ACTIONS, AND WORKFLOW

Implement configurable alerts for SLA breach, deteriorating trend, critical bottleneck, extreme P90 case, missing mandatory event, invalid sequence, duplicate call, stale live feed, resource shortage, berth conflict, severe incident, and failed report/integration. Support severity, threshold, suppression, deduplication, owner, escalation, acknowledgement, resolution, comments, attachments, action item, due date, and audit history.

---

# 16. API AND INTEGRATION CONTRACTS

Provide versioned REST APIs and event/webhook contracts for vessel calls, events, resources, incidents, quality issues, analytics, KPI results, dashboards, reports, and copilot. Include pagination, filtering, sorting, idempotency keys, correlation IDs, error schemas, rate limits, authentication, authorisation, and OpenAPI documentation. Supply import/export schemas and sample payloads using synthetic data.

---

# 17. SECURITY, PRIVACY, AND GOVERNANCE

- OIDC authentication, MFA compatibility, least privilege, scoped service accounts, and session controls.
- Encryption in transit and at rest; secrets in a managed vault.
- Tenant/port/terminal isolation.
- Input validation, malware scanning for uploads, file type/size restrictions, safe OCR/document processing, SQL injection/XSS/CSRF/SSRF protection, and secure headers.
- Immutable or append-only audit trail for login, view of sensitive data, export, correction, merge, rule/formula change, report publication, and administrative action.
- Configurable retention, archive, legal hold, backup, restore, and deletion.
- Mask personally identifiable staff information where not required.
- AI governance: grounded outputs, inference labels, confidence, human approval, model/version log, prompt/response audit with sensitive-data controls, and feedback mechanisms.
- Threat model and security test suite.

---

# 18. PERFORMANCE, RELIABILITY, AND SCALE

Define measurable service objectives. Default POC targets, configurable after discovery:

- Common dashboard initial load under 3 seconds at p95 for agreed data volume.
- Filter/drill response under 2 seconds at p95 for cached aggregate queries.
- Vessel journey under 3 seconds at p95.
- Import progress visible within 5 seconds.
- Long analytics/report jobs asynchronous with progress and cancellation.
- No silent data loss; idempotent jobs; retries with dead-letter handling.
- Health, readiness, liveness, queue depth, connector status, freshness, and data-latency monitoring.

Provide load-test fixtures and document realistic capacity assumptions rather than claiming unlimited scale.

---

# 19. TESTING REQUIREMENTS

Create automated unit, integration, contract, migration, end-to-end, accessibility, security, performance, and data-quality tests. At minimum test:

- File/API ingestion, retries, idempotency, schema drift, OCR low confidence.
- Alias mapping and timezone/date-format conversions.
- Vessel matching, conflicting IMO/VCN, threshold review, merge/unmerge.
- Missing, duplicate, conflicting, impossible, parallel, and corrected events.
- Arrival, shifting, and sailing journeys, including no shift and multiple shifts.
- Conditional IMDG/regulatory paths and halted operations.
- Duration, early service, overlapping stages, nulls, zero median, and daylight-saving anomalies.
- Mean, median, standard deviation, CV, percentiles, outliers, criticality, targets, trends.
- Every KPI formula with known synthetic fixtures and edge cases.
- Role and data-scope restrictions, export controls, audit logging.
- Dashboard filters and drill-through consistency.
- Report schedules, formats, publication, and failures.
- Copilot grounding, citations, weak-data caveats, prompt injection, and unauthorised-data attempts.

Use golden datasets with manually verified expected outputs. Add data-reconciliation tests proving dashboard totals equal API and database calculations for identical filters.

---

# 20. ACCEPTANCE CRITERIA

The solution is acceptable only when:

1. At least one file-based and one API/database ingestion path work end to end.
2. Source fields can be mapped and reused through versioned templates.
3. Raw evidence is immutable and every canonical value is traceable.
4. Duplicate vessel-call candidates are explainable and merge/unmerge is auditable.
5. Required chronology and logical rules flag seeded violations correctly without treating valid parallel events as errors.
6. A vessel call can be reconstructed across pre-arrival, arrival, berth/cargo, shifting if present, and departure.
7. Custom lead time between any two eligible events works per call and aggregated cohort.
8. Statistical metrics and P75/P90 are correct against golden data.
9. Negative execution delay is shown as early service.
10. Delay causes distinguish confirmed and inferred.
11. Bottleneck and criticality calculations expose component scores.
12. All 55 source KPIs exist in a governed registry, including duplicate/alias treatment.
13. Executive, Operations, KPI, Delay, Vessel Journey, and Data Quality dashboards function with filters and drill-through.
14. Word, Excel, PowerPoint, and PDF reporting works for at least one report template, with scheduling architecture in place.
15. Copilot answers are grounded, scoped, reproducible, caveated, and linked to supporting records.
16. Role permissions, audit logs, accessibility, test suite, migrations, backups, observability, deployment instructions, and administrator documentation are complete.
17. There are no placeholder controls, fabricated production metrics, or unlabelled AI inferences.

---

# 21. REQUIRED DELIVERY ARTIFACTS

Produce:

- Executable source code and repository structure.
- README with local setup, configuration, seed, test, build, and deployment steps.
- Product requirements traceability matrix mapping this prompt to features and tests.
- Architecture diagrams and ADRs.
- ERD and data dictionary.
- Canonical event catalogue and alias dictionary.
- Data-source onboarding template.
- OpenAPI specification and sample synthetic payloads.
- Database migrations and seed data.
- KPI/formula catalogue and versioning guide.
- Data-quality rule catalogue.
- Security threat model.
- Test strategy, automated tests, golden datasets, and results.
- UX screen inventory and accessibility checklist.
- Runbooks for ingestion failure, data correction, merge/unmerge, recalculation, backup/restore, and incident response.
- User guides for administrator, steward, controller, analyst, executive, and report manager.
- Known limitations, assumptions, and production-hardening backlog.


---

# 21A. MANDATORY SYNTHETIC DATASET FOR DEVELOPMENT, TESTING, AND OUTPUT VALIDATION

Use the accompanying workbook `Synthetic_Marine_Time_Motion_Test_Data.xlsx` as the primary governed test fixture for development, integration testing, demonstrations, regression testing, data-quality testing, analytics reconciliation, and acceptance testing. The workbook is entirely synthetic. Do not treat its vessels, personnel, shipping lines, port, timestamps, quantities, delays, or operational records as real-world facts.

The application must support uploading this workbook directly. It must also support importing each worksheet separately after it is exported to CSV. Because CSV does not support multiple worksheets, when separate CSV files are used, preserve the worksheet name as the dataset/entity name and use `VCN` as the principal cross-file join key unless a more specific identifier is provided.

## 21A.1 Dataset files and expected package handling

Expected development package:

- `Level_100_Time_Motion_Study_AI_Coding_Prompt_v2_With_Synthetic_Dataset.md`: controlling build specification.
- `Synthetic_Marine_Time_Motion_Test_Data.xlsx`: multi-sheet synthetic input and expected-output workbook.
- Optional CSV exports of the individual worksheets, retaining identical column names.

At application startup or through an administrator/developer utility, provide a clearly labelled **Load Synthetic Test Dataset** action. This action must:

1. Require an authorised administrator or developer role.
2. Label the data as synthetic in all environments and screens.
3. Prevent synthetic data from being confused or combined with production data.
4. Import using the same ingestion, mapping, validation, lineage, journey reconstruction, analytics, KPI, and reporting services used for production data.
5. Be idempotent. Re-importing the same workbook must not unintentionally multiply valid canonical records.
6. Allow complete removal/reset of the synthetic dataset without affecting other datasets.
7. Display an import summary with accepted, rejected, quarantined, duplicate, merged, conflicting, and warning counts.
8. Preserve workbook name, worksheet name, row number, ingestion batch, checksum, and original values as lineage evidence.

Do not bypass validation or insert the workbook directly into analytical tables. It must exercise the real ingestion pipeline.

## 21A.2 Worksheet contracts

### README

Treat `README` as human-readable dataset documentation, not transactional input. Make it accessible from the dataset/import details screen. It describes the dataset purpose, synthetic status, structure, join logic, timezone, and testing guidance.

### VesselCalls

Purpose: canonical vessel-call-level source records.

Expected columns:

- `VCN`
- `Vessel_Name`
- `IMO_No`
- `Shipping_Line`
- `Vessel_Type`
- `Cargo_Type`
- `Reason_For_Visit`
- `Terminal`
- `Berth`
- `GRT`
- `DWT`
- `LOA_m`
- `Planned_Quantity`
- `Quantity_Unit`
- `Nomination_Date`
- `ETA`
- `ATA`
- `Port_Limit_In`
- `Port_Limit_Out`
- `ATD`
- `Record_Status`
- `Test_Note`

Expected handling:

- Use `VCN` as the vessel-call business key, subject to duplicate and conflict rules.
- Use `IMO_No` as a vessel identity attribute, not as the unique vessel-call key.
- Parse all timestamps using `yyyy-MM-dd HH:mm` and the dataset timezone.
- Preserve `Test_Note` as test metadata and exclude it from operational KPI calculations.
- Validate quantity against `Quantity_Unit`. Never add TEU, MT, Units, and passenger counts into a single unqualified throughput total.
- Recognise the deliberate exact duplicate and probable identity-variant records described in `DQ_Cases`.

### Events

Purpose: event-level source data used to reconstruct vessel journeys.

Expected columns:

- `Event_ID`
- `VCN`
- `Event_Name`
- `Event_Timestamp`
- `Source_System`
- `Timezone`
- `Verification_Status`
- `Confidence_Score`
- `Intentional_Flag`

Expected handling:

- `Event_ID` is the event-record identifier.
- Resolve `VCN` to a vessel call. An unknown VCN must not silently create a valid vessel call unless the configured ingestion policy explicitly permits a provisional record.
- Map `Event_Name` to the canonical event catalogue.
- Use `Source_System`, verification state, confidence, and conflict policy when selecting a canonical occurrence.
- `Intentional_Flag = Y` identifies a deliberately introduced test anomaly. Treat the event through normal validation and do not automatically suppress it.
- Support repeated events, parallel events, and conflicting observations from different sources.

The event catalogue in this fixture includes nomination, ETA, ATA, port-limit events, anchorage arrival, pilot request/schedule/on-board/disembark events, breakwater in/out, tug service, first/last line tied or untied, all fast, cargo start/end, ATD, and optional shifting events.

### Services

Purpose: requested, scheduled, and delivered marine-service records.

Expected columns:

- `Service_ID`
- `VCN`
- `Movement_Type`
- `Service_Type`
- `Location`
- `Submission_Time`
- `Requested_Time`
- `Scheduled_Time`
- `Served_Time`
- `Execution_Delay_Hours`
- `Assigned_Resource`
- `Data_Status`

Expected handling:

- Validate `Submission_Time`, `Requested_Time`, `Scheduled_Time`, and `Served_Time` independently.
- Recalculate execution delay as `Served_Time - Scheduled_Time`; compare it with the supplied value and flag any mismatch beyond the configured tolerance.
- Retain negative delay values as early service.
- Support Pilotage Service, Tug Service, and Berthing Service for Arrival and Sailing, with the model extensible to Shifting and other service types.
- Interpret `Assigned_Resource` based on service type, such as pilot, tug, or mooring team.

### CargoOps

Purpose: cargo-operation inputs and cargo working-time validation.

Expected columns:

- `Cargo_Operation_ID`
- `VCN`
- `Cargo_Type`
- `Operation_Type`
- `Planned_Quantity`
- `Unit`
- `Cargo_Start`
- `Cargo_End`
- `Working_Hours`
- `Resources_Deployed`
- `Downtime_Hours`
- `Actual_Quantity`
- `Data_Status`

Expected handling:

- Recalculate `Working_Hours = Cargo_End - Cargo_Start` and reconcile with the supplied result.
- Validate that downtime is non-negative and does not exceed the relevant operation window without explanation.
- Keep planned and actual quantity distinct.
- Segment productivity by cargo type and unit.
- Use resource and downtime fields in productivity and variability analysis where eligible.

### Delays

Purpose: confirmed delay records for delay classification and dashboard tests.

Expected columns:

- `Delay_ID`
- `VCN`
- `Movement_Type`
- `Scheduled_Time`
- `Served_Time`
- `Delay_Hours`
- `Delay_Reason`
- `Delay_Category`
- `Cause_Status`
- `Confidence`
- `Resolution_Status`

Expected handling:

- Recalculate delay duration and reconcile it with `Delay_Hours`.
- Distinguish reason from category.
- Preserve confirmed/inferred cause status.
- Validate that positive delays have a reason or are flagged for review.
- Use resolution status for the exception/action workflow, not to change historical delay duration.
- Do not infer a replacement reason over a confirmed reason.

### ExpectedOutputs

Purpose: gold-standard vessel-level expected results for automated reconciliation.

Expected columns:

- `VCN`
- `Expected_Turnaround_Hours_ATA_to_ATD`
- `Expected_Anchorage_Wait_Hours`
- `Expected_Inward_Movement_Hours`
- `Expected_Berth_Stay_Hours`
- `Expected_Cargo_Working_Hours`
- `Expected_Outward_Movement_Hours`
- `Expected_Arrival_Execution_Delay_Hours`
- `Expected_Sailing_Execution_Delay_Hours`
- `Expected_Turnaround_Over_120h`

This worksheet is an expected-result oracle, not an operational source. Never ingest it into canonical event or KPI tables. Load it only into a test/reconciliation schema that is isolated from application calculations.

For each valid VCN, compare application-calculated results with these expected values. Use configurable numeric tolerance, defaulting to:

- Duration comparison tolerance: plus or minus 0.02 hours.
- Timestamp comparison tolerance: plus or minus 1 minute.
- Boolean comparison: exact match.

A test passes only if the system independently calculates the metric from input worksheets and matches the expected result. Do not copy expected values into actual output fields.

### DQ_Cases

Purpose: negative-test manifest documenting intentionally injected anomalies.

Expected columns:

- `Case_ID`
- `Test_Type`
- `Sheet`
- `Record_Key`
- `Injected_Condition`
- `Severity`
- `Expected_System_Behaviour`

Use this manifest to drive automated data-quality tests. Every case must create the intended issue or workflow outcome and must be traceable by case ID.

The supplied scenarios include:

1. `DQ-001`: exact duplicate vessel-call record. Expect duplicate detection and prevention of double counting.
2. `DQ-002`: probable duplicate identity with punctuation variation and the same VCN/IMO. Expect a very high-confidence merge candidate and explainable evidence.
3. `DQ-003`: missing ATA. Expect a missing-mandatory-timestamp issue and dependent metrics marked unavailable or ineligible.
4. `DQ-004`: ETA after ATA. Expect an `ETA before ATA` chronology violation.
5. `DQ-005`: pilot request exists but pilot scheduled event is absent. Expect a missing service event issue.
6. `DQ-006`: pilot on board occurs before scheduled time by an intentionally invalid sequence. Expect a chronological or pilotage rule violation. Do not confuse this with a valid small negative execution delay if it breaches the configured operational sequence scenario.
7. `DQ-007`: positive delay with missing reason/category. Expect mandatory delay-reason review.
8. `DQ-008`: extreme 720-hour expected turnaround outlier. Expect extreme-delay/outlier and P90-related handling according to the test design.
9. `DQ-009`: orphan event with `VCN = SYNVCN-NOTFOUND`. Expect referential-integrity rejection or quarantine.
10. `DQ-010`: two conflicting ATA values separated by five hours. Expect conflict detection, source evidence comparison, and steward review.

### ValidationSummary

Purpose: high-level expected population and scenario counts.

Use this worksheet for smoke-test reconciliation. It includes expected counts for the base vessel-call population, total rows, unique VCNs, duplicate cases, merge candidates, orphan events, data-quality cases, optional shifts, long-turnaround calls, and negative execution-delay cases.

Do not use `ValidationSummary` as an operational input. It belongs in the isolated testing schema.

## 21A.3 Required automated dataset test harness

Build a repeatable command, API, or administrator workflow named conceptually `run-synthetic-validation` that performs the following:

1. Reset or create an isolated synthetic test tenant/dataset.
2. Ingest `VesselCalls`, `Events`, `Services`, `CargoOps`, and `Delays` through the real ingestion pipeline.
3. Load `ExpectedOutputs`, `DQ_Cases`, and `ValidationSummary` into the isolated test framework only.
4. Execute mapping, standardisation, identity matching, duplicate detection, chronology validation, quality scoring, journey reconstruction, service-delay calculation, analytics, KPI calculation, and report generation.
5. Produce a machine-readable reconciliation result and a human-readable test report.
6. Compare actual and expected outputs by VCN and metric.
7. List passed, failed, unavailable, excluded, and tolerance-exceeded comparisons.
8. Verify every DQ case produced the expected rule, severity, disposition, and workflow state.
9. Confirm valid negative delays remain negative and are labelled early service.
10. Confirm duplicate and variant rows do not inflate vessel-call, throughput, delay-frequency, or KPI counts.
11. Confirm quarantined critical records are excluded by default and disclosed if intentionally included.
12. Retain execution time, application version, formula version, rule version, dataset checksum, and test result history.

The validation report must include:

- Dataset/import summary.
- Row counts by worksheet and disposition.
- Mapping and schema errors.
- Data-quality case results.
- Vessel journey reconstruction coverage.
- Metric-by-metric reconciliation.
- KPI reconciliation.
- Duplicate impact check.
- Negative/early-service check.
- Outlier and tail-risk check.
- Dashboard/API/database total consistency.
- Final pass/fail result and failure details.

## 21A.4 Development and demonstration scenarios

Use the workbook to implement and demonstrate at least these vertical slices:

### Scenario A: Clean vessel journey

Select a vessel call without an intentional issue. Demonstrate ingestion, mapping, complete journey reconstruction, stage durations, services, cargo operations, and expected-output reconciliation.

### Scenario B: Early service

Select a call with a negative arrival or sailing execution delay. Demonstrate that the platform reports early service and does not raise a negative-duration error solely because the delay is below zero.

### Scenario C: Confirmed operational delay

Select a delayed call from `Delays`. Demonstrate scheduled-versus-served variance, confirmed reason/category, relevant timeline evidence, delay dashboard inclusion, and action/resolution status.

### Scenario D: Duplicate consolidation

Run `DQ-001` and `DQ-002`. Demonstrate exact duplicate handling, high-confidence candidate matching, merge evidence, survivorship, audit trail, and protection against KPI double counting.

### Scenario E: Missing and invalid timestamps

Run `DQ-003` through `DQ-006`. Demonstrate quality issue creation, severity, quarantine/eligibility impact, steward correction, recalculation, and issue closure.

### Scenario F: Conflicting source records

Run `DQ-010`. Demonstrate simultaneous preservation of both source observations, source/confidence comparison, canonical selection, manual decision, and audit history.

### Scenario G: Extreme outlier

Run `DQ-008`. Demonstrate outlier detection, percentile/tail-risk behaviour, exclusion/inclusion transparency, and drill-through to the vessel call.

### Scenario H: Orphan record

Run `DQ-009`. Demonstrate rejection or quarantine and confirm the event is not attached to an unrelated vessel call.

## 21A.5 Dataset-specific acceptance criteria

In addition to the general acceptance criteria, the build is not acceptable until:

1. The workbook imports through the normal ingestion UI/API without manual database manipulation.
2. Every transactional worksheet has a reusable source mapping.
3. The base valid population is reconstructed without duplicate inflation.
4. All ten documented DQ scenarios produce the expected system outcome.
5. Vessel-level calculated metrics match `ExpectedOutputs` within tolerance for eligible valid calls.
6. Negative execution delays remain negative and appear as early service.
7. Missing or invalid required events make dependent outputs unavailable, rather than fabricating values.
8. The orphan event is rejected or quarantined.
9. Conflicting ATA observations remain traceable and require governed resolution.
10. The dashboard, API, report, and database totals reconcile under identical filters.
11. The synthetic-data flag is visible and synthetic data cannot be mistaken for production data.
12. A validation report can be rerun after any code, rule, mapping, or KPI formula change and compared with prior runs.

## 21A.6 Constraints for coding agents

- Do not alter the synthetic workbook merely to make a failing implementation pass.
- If a genuine fixture defect is discovered, record it as a test-data issue, create a corrected version, retain the original, and document the change.
- Do not hard-code the synthetic VCNs or expected results into application logic.
- Do not special-case `Intentional_Flag` to manufacture desired validations. Normal rules must identify the anomaly.
- Do not use `ExpectedOutputs`, `DQ_Cases`, or `ValidationSummary` as training or operational facts.
- Do not claim a test passed when a result was unavailable, excluded, or not independently calculated.
- Ensure the same rules used against the fixture are configurable and usable for future real source files.

---

# 22. AUTONOMOUS BUILD SEQUENCE

Execute without repeatedly asking for approval:

1. Parse this specification into a requirements traceability matrix.
2. Create assumptions and decisions register.
3. Define architecture, boundaries, data model, event catalogue, quality rules, and KPI registry.
4. Scaffold repository, authentication, authorisation, configuration, database, logging, and CI.
5. Build ingestion and lineage first.
6. Build mapping, quality, exception, and consolidation workflows.
7. Build journey reconstruction and event timeline.
8. Build analytics, KPI, benchmark, trend, bottleneck, outlier, and criticality engines.
9. Build dashboards and drill-through.
10. Build reporting and copilot using the governed services.
11. Load and use `Synthetic_Marine_Time_Motion_Test_Data.xlsx` as the primary synthetic fixture. Supplement it only where a requirement is not represented, and clearly label any additional fixture data. Demonstrate normal, delayed, duplicate, missing, conflicting, shifting, outlier, orphan, and early-service cases.
12. Run the synthetic validation harness, reconcile calculated results against `ExpectedOutputs`, verify every `DQ_Cases` scenario, fix defects, and document remaining constraints.
13. Provide a final implementation report containing completed items, test evidence, assumptions, and backlog.

At each phase, keep the application runnable. Prefer complete vertical slices over a wide set of superficial screens.

---

# 23. FINAL INSTRUCTION TO THE CODING AGENT

Begin implementation now. Treat `Synthetic_Marine_Time_Motion_Test_Data.xlsx` as the mandatory primary development and regression fixture. Do not respond only with a plan. First produce the requirements traceability matrix, architecture decision summary, repository tree, canonical data model, and phased implementation plan, then create the working application in the environment. If an external credential or unavailable proprietary system blocks an integration, implement a clean adapter interface, synthetic sandbox connector, contract tests, and explicit setup instructions. Do not fabricate successful connectivity. Ensure every major requirement above is represented in code, configuration, tests, documentation, or a clearly identified production backlog item with rationale.
