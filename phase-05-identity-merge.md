# Phase 05 — Identity resolution, duplicate detection, merge and unmerge
**Model: `gemini-3.7-flash-high`**
*(If the scoring logic stalls, escalate this phase only to `gemini-3.1-pro-high`.)*

Read `AGENTS.md`. Spec §8.2 and §8.3 are the reference.

## 1. Matching

Two stages, in order:

**Deterministic first** — VCN, IMO, call sign, source call id, voyage, port plus arrival window.
A deterministic key match is decisive and short-circuits scoring.

**Probabilistic second** — normalised vessel name similarity, ETA/ATA proximity windows, berth, agent,
voyage data. Produce a score in [0,1] with a per-attribute contribution breakdown stored in
`identity.match_evidence`. The score must be explainable: for any candidate pair, the UI shows which
attributes agreed, which disagreed, and how much each moved the score.

Configurable thresholds (defaults from `config/thresholds.yaml`):
- `>= 0.98` and no key conflict → auto-merge
- `0.85` to `0.9799` → steward review queue
- `< 0.85` → retain separately
- **Any conflicting IMO or VCN → never auto-merge, regardless of score.** Hard rule, not a threshold.

Normalisation for matching must handle the punctuation and separator variants the spec names
(`MSC AURORA` / `MSC AURORA.` / `MSC-AURORA`) while the display name is preserved verbatim.

## 2. Survivorship and merge

- Survivorship rules by source priority, recency and completeness, configurable per field.
- Side-by-side comparison view with field-level provenance.
- Merge preview showing exactly what the consolidated record will look like before commit.
- Merge writes a `merge_decision` with actor, timestamp, score, evidence snapshot and rule version.
- **Unmerge must be safe and complete**: the original records are restored intact, downstream
  aggregates recalculate, and both the merge and the unmerge remain in the audit trail. Test that a
  merge followed by an unmerge returns the system to a state equivalent to before the merge.

## 3. Double-counting protection

This is the point of the whole phase. After consolidation:
- vessel-call counts, throughput totals, delay frequencies and every KPI denominator must count the
  consolidated record once
- a test must assert that the count before and after merging the fixture's duplicates differs by
  exactly the number of merges, and that no metric silently double-counted beforehand

## 4. Fixture cases

| Case | Record | Expected |
|---|---|---|
| DQ-001 | `SYNVCN2600005` exact duplicate row | `DUPLICATE_RECORD` flag, CRITICAL; auto-handled; no double counting anywhere |
| DQ-002 | `SYNVCN2600012` same VCN/IMO, punctuation variant name | merge candidate `>= 0.98` with explainable evidence |

The fixture has 74 `VesselCalls` rows against 72 valid VCNs. After this phase the base population must
be exactly 72 and `ValidationSummary` must reconcile on that number.

Do not reference these VCNs in application code. The matcher finds them because it is correct.

## Done when
Both DQ cases produce their expected outcome through ordinary matching; conflicting IMO/VCN blocks
auto-merge in a test; merge evidence is visible and complete; unmerge restores state; the base
population reconciles to 72 in `make validate`.
