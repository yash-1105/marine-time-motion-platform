# Phase 10 — `run-synthetic-validation` harness
**Model: `gemini-3.1-pro-high`**
*(Reserved escalation: if the harness will not go green after two Pro attempts, switch to
`claude-sonnet-4-6` for the debugging session only.)*

Read `AGENTS.md` §6 carefully. Spec §21A.3 is the reference. This phase is the one your mentor will
actually run. Everything else is judged through its output.

The skeleton exists from phase 03. Fill it in completely.

## The twelve steps (spec §21A.3)

1. Reset or create an isolated synthetic test tenant.
2. Ingest `VesselCalls`, `Events`, `Services`, `CargoOps`, `Delays` through the real pipeline.
3. Load `ExpectedOutputs`, `DQ_Cases`, `ValidationSummary` into `testkit` only.
4. Execute mapping, standardisation, identity matching, duplicate detection, chronology validation,
   quality scoring, journey reconstruction, service-delay calculation, analytics, KPI calculation and
   report generation — using the production services, not test-only reimplementations.
5. Produce a machine-readable JSON result and a human-readable Markdown report.
6. Compare actual against expected by VCN and by metric.
7. List passed, failed, unavailable, excluded and tolerance-exceeded comparisons as distinct outcomes.
   `UNAVAILABLE` is not `FAILED` and must not be reported as either a pass or a failure.
8. Verify every DQ case produced the expected rule, severity, disposition and workflow state.
9. Confirm valid negative delays remain negative and are labelled early service.
10. Confirm duplicate and variant rows did not inflate vessel-call, throughput, delay-frequency or KPI counts.
11. Confirm quarantined critical records are excluded by default and disclosed if intentionally included.
12. Retain execution time, application version, formula version, rule version, dataset checksum and
    test result history, so runs are comparable across code changes.

## Tolerances
Duration ±0.02 hours. Timestamp ±1 minute. Boolean exact. Configurable.

Use `round(abs(actual − expected), 6) <= tolerance` — several fixture rows land exactly on the
boundary and raw float subtraction produces spurious failures on them.

## Report sections (spec §21A.2)
Dataset/import summary; row counts by worksheet and disposition; mapping and schema errors; DQ case
results; journey reconstruction coverage; metric-by-metric reconciliation; KPI reconciliation;
duplicate impact check; negative/early-service check; outlier and tail-risk check; dashboard/API/
database total consistency; final pass/fail with failure detail.

## Expected result on this fixture

When the build is correct the report should show:

- 74 `VesselCalls` rows → 72 base vessel calls after consolidation
- 1745 `Events` rows, 1 orphan quarantined
- 432 `Services`, 72 `CargoOps`, 41 `Delays`
- 72 of 72 journeys reconstructed, 8 with a shifting stage
- Turnaround: 70 of 71 reconcile (one has no ATA — DQ-003 — so `UNAVAILABLE`, and `SYNVCN2600063`
  diverges by design as DQ-008's 720-hour override, reported as an intentional documented case)
- Anchorage Wait: 71 of 72 (DQ-006's `SYNVCN2600045` computes −3.60h, a sequence violation)
- Inward Movement: 71 of 72 (same call)
- Berth Stay, Cargo Working, Outward Movement: 72 of 72
- Arrival and Sailing Execution Delay: 72 of 72
- 6 calls over 120h, 7 negative arrival delays, 10 negative sailing delays — all preserved
- 10 of 10 DQ cases producing their documented behaviour

If your numbers differ from these, your implementation is wrong, not the fixture. Investigate before
adjusting anything.

## Scenario demonstrations (spec §21A.4)
Implement a `--scenario` flag running each of the eight vertical slices A–H individually with narrated
output, so each can be demonstrated on its own: clean journey, early service, confirmed delay,
duplicate consolidation, missing/invalid timestamps, conflicting sources, extreme outlier, orphan record.

## Constraints (spec §21A.6) — enforce these in code review of your own output
- Do not alter the workbook to make anything pass.
- Do not hard-code synthetic VCNs or expected results in application logic. The harness may reference
  VCNs; the application may not.
- Do not special-case `Intentional_Flag`.
- Do not use `ExpectedOutputs`, `DQ_Cases` or `ValidationSummary` as operational facts.
- Do not report a pass where the result was unavailable, excluded, or not independently calculated.
  Add an assertion that fails the run if any expected value was ever copied into an actual field.

## Done when
`make validate` runs from a clean database to a complete report; the numbers above are reproduced;
a second run produces an identical result and a comparable history entry; the report distinguishes
pass, fail, unavailable, excluded and tolerance-exceeded.
