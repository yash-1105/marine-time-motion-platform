# Phase 01 — Canonical data model, migrations, configuration seed
**Model: `gemini-3.1-pro-high`**

Read `AGENTS.md`. This phase encodes the domain. Get it wrong and phases 03–10 inherit the mistake,
so think about the model before writing migrations.

## 1. Canonical schema

Implement the entity list in spec §6 as Alembic migrations across the schemas from `AGENTS.md` §2.
Every entity: UUID PK, `created_at`/`updated_at` (`timestamptz`), `created_by`/`updated_by`,
`source_lineage_id`, `version` integer for optimistic concurrency, soft delete where the spec implies
history matters.

Prioritise correctly modelling these, since they carry the build:

- `canonical.vessel_call` — with all spec §6.1 master attributes, explicit units and precision.
- `canonical.event_occurrence` — the core. **Not** a wide timestamp table. Columns for vessel call,
  event definition, occurrence index (for repeated events like multiple shifts or multiple tugs),
  movement scope (`ARRIVAL|SHIFTING|SAILING`), plus the full timestamp envelope from `AGENTS.md` §3.3.
  Add a partial unique index and supporting indexes for `(vessel_call_id, event_definition_id, occurrence_index)`.
- `config.event_definition` and `config.event_alias` — configurable catalogue, aliases with match type
  (`EXACT|CASE_INSENSITIVE|NORMALISED|REGEX|AI_SUGGESTED`) and confirmation state.
- `canonical.service_request` / `service_assignment` / `service_execution` — modelling submission,
  requested, scheduled and served times as separate observations, with an arbitrary number of
  assigned resources. The tug model must support N tugs, not two columns.
- `canonical.delay` + `delay_allocation` — multiple causes per delay with duration allocation and
  primary/secondary designation, plus `cause_status` (`CONFIRMED|INFERRED`) and inference evidence.
- `quality.quality_rule` / `quality_issue` / `resolution_decision` with rule version and effective dates.
- `identity.match_candidate` / `match_evidence` / `merge_decision` — merges reversible by construction.
- `journey.journey_template` / `journey_stage` / `journey_instance` / `stage_occurrence` / `handover`.
- `analytics.lead_time_definition` / `lead_time_result` / `kpi` / `kpi_formula_version` / `kpi_result`.
- `audit.audit_event` — append-only. Enforce with a trigger that rejects UPDATE and DELETE.
- `testkit.*` — isolated expected-output and DQ-case tables. Add a DB role or an application-layer
  guard so domain services cannot read this schema. Prove it with a test.

Also create `canonical.timestamp_observation` (or an embedded composite) so the §3.3 envelope is
stored once and referenced, rather than duplicated as twelve columns on every table.

## 2. Configuration seed — `/config/*.yaml`

These are data, not code. The application reads them at migration/seed time into `config.*` tables and
they are editable by administrators afterwards.

- `events.yaml` — the full spec §6.2 catalogue: pre-arrival and clearance, arrival pilotage and pilot
  boat, arrival tug (N tugs), arrival berthing, shifting, sailing, berth and cargo, incident. This is
  a superset of the 26 event names in the fixture; that is correct and intended.
- `aliases.yaml` — the spec §6.3 dictionary, plus mappings for the fixture's `Event_Name` values
  (`PILOT_ON_BOARD_ARRIVAL`, `ALL_FAST_ARRIVAL`, `LAST_LINE_UNTIED_SAILING`, `BREAKWATER_OUT`, etc.)
  onto canonical definitions. The numbered variants (`Pilot Request Time 1/2/3`) map to canonical
  event + occurrence index.
- `quality_rules.yaml` — every rule from spec §8.4, with id, scope, severity, applicable movement
  types, pass/fail expression, remediation guidance, effective dates.
- `kpis.yaml` — all 55 KPIs from spec §11 with name, business definition, formula expression,
  numerator, denominator, unit, eligible population, required events/fields, exclusions, aggregation
  method, vessel applicability, target, thresholds, owner, effective dates. Include
  `computable_from: [...]` listing required source entities, and for those the fixture cannot feed,
  `status: NO_SOURCE_DATA`. Record the spec §11 duplicate pairs (11/53 tug response, 14/51 berth
  occupancy) with `primary_kpi_id` and `alias_of`.
- `journey_templates.yaml` — the spec §9 reference flow as a DAG with conditional branches (IMDG,
  deep-sea vs coastal, optional shifting) and the T-21/T-14/T-7/24h/12NM/6NM milestone offsets as a
  configurable template, not hard-coded rules.
- `thresholds.yaml` — criticality bands, outlier sigma, tolerance defaults, auto-merge thresholds,
  right-skew threshold.
- `roles.yaml` — the 9 roles from spec §4 with their action permissions.

## 3. Data dictionary and ERD
Generate `docs/data-dictionary.md` (every table, column, type, unit, nullability, meaning, source) and
`docs/erd.md` with a Mermaid ERD of the canonical schema.

## Constraints
- No fixture-specific values in migrations or code. The fixture's event names arrive via `aliases.yaml`,
  which is configuration a port administrator could edit.
- Units are explicit everywhere. There is no unqualified "quantity" column — quantity always carries
  its unit, and the model must make `TEU + MT + Units` impossible to sum accidentally.
- Every datetime column is `timestamptz`. A naive timestamp anywhere is a bug.

## Done when
`make migrate` applies and rolls back cleanly; `make seed` loads all config YAML into `config.*`;
tests assert the audit-table immutability trigger, the testkit isolation guard, and that all 55 KPIs
are present with the correct computable/no-source-data split; ERD and data dictionary generated.
