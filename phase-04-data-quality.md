# Phase 04 — Data quality, validation, and cleansing engine
**Model: `gemini-3.1-pro-high`**

Read `AGENTS.md`. Spec §8 is the reference. This phase is where most implementations quietly cheat by
hard-coding the test cases — do not. The rules are configuration, and the fixture's anomalies must be
caught because the rules are correct, not because the rules were written to catch them.

## 1. Rule engine

Rules load from `config/quality_rules.yaml` into `quality.quality_rule`. Each carries id, version,
scope (entity/field/movement type), severity, effective dates, a declarative pass/fail expression,
whether exceptions are permitted and by which permission, and remediation guidance.

The engine evaluates a record against the applicable rule set and emits `quality.quality_issue` rows
with owner, status, age, due date, evidence (pointing at raw lineage), comments, resolution and
approval state. Issues are classified two ways, per spec §8.5:
- Severity: `INFO | LOW | MEDIUM | HIGH | CRITICAL`
- Type: `DATA_QUALITY | OPERATIONAL_SEQUENCE | IDENTITY | COMPLETENESS | DUPLICATE | CONFLICT | OUTLIER | POLICY`

Rule changes are versioned; a recalculation records which rule version produced each issue.

## 2. Standardisation (spec §8.1)
Whitespace and punctuation normalisation that never destroys the original; vessel-name normalisation
for matching with display name retained; display format `yyyy-MM-dd HH:mm` with seconds and offset
available when supplied; unit standardisation for TEU, MT, GRT, DWT, LOA, draft, minutes, hours;
harmonisation of vessel type, movement type, berth, terminal, cargo type, service category, resource
names and delay categories via config lookup tables. No silent precision loss — test it with decimals.

## 3. Chronology as a DAG (spec §8.4) — the hard part

Do **not** implement chronology as a linear ordered list. Model it as a directed acyclic graph with
conditional and parallel branches, loaded from `config/journey_templates.yaml`. Validate only the
rules applicable to the movement type and only where both endpoint events exist.

Seed every rule in spec §8.4, including the pilotage chain (Request < Assigned < Start < On Board <
Disembark < End), the berthing chain (First Line Tied < Last Line Tied < All Fast), ETA before ATA/ETD/ATD,
Port Limit In before Pilot On Board and Breakwater In, tug ordering with port-specific override,
Breakwater Out before Port Limit Out, all starts before their ends, service start after service request.

**Parallel activities must not generate false violations.** Tug service and pilot boarding overlap
legitimately; cargo operations and clearances overlap; multiple tugs run concurrently. Write explicit
tests for legitimate concurrency producing zero issues — this is the single most common failure mode.

## 4. Completeness, duplicates, anomalies

- Missing mandatory data determined by vessel type, movement, stage and KPI dependency — not a static
  required-fields list. The spec's example: Pilot Request present but Pilot Assigned absent → HIGH.
- Duplicate detection at field, source row, event, VCN, vessel call and batch level.
- Anomaly flags per spec §8.5: missing timestamps, duplicates, invalid negative durations, unrealistic
  values, blanks, inconsistent identifiers, wrong order, missing reasons, cross-source conflicts,
  missing requested/scheduled/served fields, statistical outliers.

**The negative-value distinction, restated because it is the most-failed requirement.** Two separate
code paths:
- `Served_Time − Scheduled_Time < 0` on a service → **early service**. Valid. Preserve the sign.
  Never an issue. The fixture contains 7 negative arrival and 10 negative sailing delays that must
  survive untouched.
- A duration between two events the DAG says are ordered coming out negative → **sequence violation**.
  Raise an issue. Do not coerce to zero, do not take absolute value, do not drop the record.

Write a test that asserts both behaviours on the same dataset simultaneously.

## 5. Quarantine and eligibility
Records with unresolved CRITICAL issues are quarantined: excluded from downstream analytics by
default. An authorised user may include them explicitly; that inclusion is recorded and must be
disclosed on every affected metric response. Build the disclosure into the metric response shape now.

## 6. Data quality score (spec §8.6)
Transparent sub-scores for completeness, validity, consistency, uniqueness, timeliness and lineage.
Available by batch, source, field, vessel call, period and domain. The composite score must always
expand to its components — never present an average that conceals event-level issues.

## 7. Fixture cases this phase must produce

Through ordinary rule evaluation, with no reference to `Intentional_Flag` or to any VCN:

| Case | Record | Expected |
|---|---|---|
| DQ-003 | `SYNVCN2600018` ATA blank | `MISSING_MANDATORY`, HIGH; ATA-dependent metrics become `UNAVAILABLE` |
| DQ-004 | `SYNVCN2600027` ETA after ATA | `ETA_BEFORE_ATA` chronology violation, HIGH |
| DQ-005 | `SYNVCN2600036` pilot request present, scheduled absent | missing service event, HIGH |
| DQ-006 | `SYNVCN2600045` pilot on board before scheduled | pilotage sequence violation, CRITICAL |
| DQ-007 | `SYNVCN2600054` positive delay, reason blank | mandatory delay-reason review, MEDIUM |
| DQ-009 | `EV-ORPHAN-001` | referential-integrity rejection/quarantine (already handled in phase 03 — assert it here) |

DQ-006 deserves care: for that call, `ANCHORAGE_ARRIVAL → PILOT_ON_BOARD_ARRIVAL` computes to −3.60h.
That is a sequence violation, **not** early service, and your engine must reach that conclusion from
the DAG rather than from the sign alone. Meanwhile the same call's service execution delay, if
negative, would still be early service. This pair is the sharpest test of §4 above.

Also note: `Services.Execution_Delay_Hours` matches recalculation on all 432 fixture rows. The
mismatch-detection rule (recalculate and flag beyond tolerance) must still exist and be tested with a
synthetic unit fixture of your own — do not claim the workbook proves it.

## Done when
`make validate` shows the six DQ cases above producing their expected rule, severity and disposition;
tests prove parallel events raise no violations; tests prove early service and sequence violations are
handled by different paths on the same run; quality scores expand to components; quarantine excludes
by default and discloses on inclusion.
