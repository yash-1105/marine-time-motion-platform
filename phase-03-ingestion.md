# Phase 03 — Ingestion, lineage, and the Load Synthetic Dataset action
**Model: `gemini-3.1-pro-high`**

Read `AGENTS.md`, especially §4 (fixture rules) and §6 (verified fixture facts). This is the backbone
phase. Spec §22 says build ingestion and lineage first for a reason: everything downstream is only as
trustworthy as this pipeline.

## 1. The pipeline

`upload → raw (immutable) → parse → staging → map → validate (dry-run) → commit → canonical`

- `raw.record` is append-only and stores the original cell value as text, worksheet name, row number,
  column name, ingestion batch, file checksum. Nothing overwrites it, ever.
- `staging.record` holds the parsed/typed interpretation with parse errors attached per field.
- Promotion to `canonical` happens only after validation, and carries lineage links back to the raw row.

## 2. Ingestion features (spec §7)

- Connector catalogue with the spec §7 configuration fields per source (system name, data owner,
  connection type, frequency, format, mandatory/optional fields, source unique identifier, timestamp
  format, source timezone, credentials reference, schema version, expected volume, sensitivity, SLA)
  and a connection test action.
- File upload: drag-and-drop, preview, worksheet/table selection, detection of encoding, delimiter,
  header row, decimal separator, date format and timezone — with detected values shown and overridable.
- Source-field-to-canonical mapping UI backed by the alias dictionary. Suggest matches using exact,
  case-insensitive, normalised and regex strategies. Add a Gemini-backed suggestion path that returns
  `AI_SUGGESTED` mappings which are **inert until a human confirms them** — surface confidence and
  rationale, and never let an unconfirmed suggestion affect an import.
- Reusable, versioned import templates.
- **Dry run**: full validation producing accepted / rejected / quarantined counts and a downloadable
  error report, with zero writes to canonical. This is a hard requirement — implement it as the same
  code path as commit with a transaction rollback, not a separate simplified path, or the two will drift.
- Batch progress with row counts and per-row disposition; error CSV download.
- **Idempotency**: re-importing the same file must not create duplicate canonical records. Key on
  (file checksum, worksheet, row number, source record id). Replay is explicit and safe.
- Incremental and full-refresh modes.
- Schema-drift detection with an approval workflow when a source's columns change against its
  registered schema version.
- Original file preserved to object storage with checksum.
- REST ingestion endpoint with authentication, throttling, retries, dead-letter queue and replay.

For OCR and the scanned-register path: build the adapter interface, a synthetic sandbox connector,
contract tests, and the `OCRArtifact` model with bounding box / confidence / human-verification fields.
Do not fake a working OCR engine. Document it in `docs/scope-decisions.md` as adapter-only.

## 3. Load Synthetic Test Dataset (spec §21A.1)

An administrator/developer action, plus a `make load-synthetic` CLI equivalent, that:
1. Requires the administrator or developer role.
2. Creates or resets an isolated tenant flagged `is_synthetic = true`, rendering the undismissable
   banner everywhere.
3. Imports `VesselCalls`, `Events`, `Services`, `CargoOps`, `Delays` **through the ordinary ingestion
   pipeline** — same mapping, same validation, same lineage. No direct inserts into analytical tables.
4. Loads `ExpectedOutputs`, `DQ_Cases`, `ValidationSummary` into `testkit` only, via a separate loader
   that domain services cannot invoke.
5. Is idempotent — re-running does not multiply canonical records.
6. Supports complete removal/reset of the synthetic dataset without touching other data.
7. Displays an import summary: accepted, rejected, quarantined, duplicate, merged, conflicting, warning.
8. Preserves workbook name, worksheet, row number, batch id, checksum and original values as lineage.

**The `ExpectedOutputs` decoder.** `Expected_Turnaround_Hours_ATA_to_ATD` is stored as Excel
date-formatted cells. Decode per `AGENTS.md` §6 with the 1900 leap-year correction. This decoder lives
in the `testkit` loader only — it must not exist in the ingestion path. Write the finding into
`docs/test-data-issues.md`, retain the original workbook untouched.

## 4. Expected behaviour on this fixture

At the end of this phase, importing the workbook should give you: 74 `VesselCalls` raw rows promoted
against 72 distinct VCNs with the duplicate pair surfaced (not yet resolved — that's phase 05); 1745
`Events` raw rows with `EV-ORPHAN-001` failing referential integrity and being quarantined rather than
creating a phantom vessel call; 432 `Services`; 72 `CargoOps`; 41 `Delays`. Timestamps parsed with
format `yyyy-MM-dd HH:mm` in `Africa/Johannesburg`, stored UTC, local semantics retained.
`Test_Note` is preserved as test metadata and excluded from operational calculations.

An unknown VCN must not silently create a valid vessel call. Make that policy configurable
(`ingestion.unknown_vcn_policy: REJECT | QUARANTINE | PROVISIONAL`) with `QUARANTINE` as the default.

## 5. Harness spine

Create `make validate` / `run-synthetic-validation` now, as a skeleton: it resets the synthetic
tenant, runs the import, loads the testkit oracles, and emits a report where every reconciliation line
reads `UNAVAILABLE — not yet implemented`. Later phases fill it in. Emit both a machine-readable JSON
result and a human-readable Markdown report, with execution time, app version, formula version, rule
version and dataset checksum recorded.

## Done when
The workbook imports through the UI with no manual database manipulation; re-importing changes no
counts; raw is provably immutable; the orphan event is quarantined; the dry run writes nothing; the
testkit schema is unreachable from domain code; `make validate` runs and produces a report skeleton.
