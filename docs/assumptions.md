# Assumptions and Decisions Register

| ID | Spec reference | Ambiguity | Decision taken | Configurable? | Config key | Test |
|---|---|---|---|---|---|---|
| A-001 | §6 | Port Stay convention (ETA-to-ATD vs ATA-to-ATD) | Default to ATA-to-ATD | Yes | `metrics.port_stay.start_event` | `test_port_stay_calculation` |
| A-002 | §6 | Turnaround exclusions (litigation, repairs) | Default none, admin-configurable exclusion list | Yes | `metrics.turnaround.exclusions` | `test_turnaround_exclusions` |
| A-003 | §6 | Restow treatment in TEU throughput | Default excluded from throughput, reported separately | Yes | `metrics.throughput.include_restow` | `test_teu_throughput_restow` |
| A-004 | §6 | Auto-merge threshold | Default 0.98, review band 0.85–0.9799 | Yes | `identity.merge.threshold` | `test_auto_merge_thresholds` |
| A-005 | §6 | Outlier method | Default robust MAD with configurable sigma | Yes | `analytics.outlier.sigma` | `test_outlier_mad` |
| A-006 | §6 | Criticality weighting | Default arithmetic mean of the three component scores | Yes | `analytics.criticality.method` | `test_criticality_weighting` |
| A-007 | §6 | Tug-before-pilot tolerance | Default treated as violation, port-level override available | Yes | `rules.sequence.tug_before_pilot.tolerance` | `test_sequence_violation_tug` |
| A-008 | §9 | Canonical occurrence selection precedence when multiple observations conflict | Verification status first, then confidence, then configured source priority; ties broken by earliest ingested | Yes | `thresholds.canonical_occurrence_selection` | `test_dq010_conflicting_ata_preserved_and_resolved` |
| A-009 | §9 | Active/wait/hold/delay/unclassified decomposition must not double-count overlapping stages (e.g. shifting occurs inside Cargo Operations) | Compute the main-path sequential stages first (they partition the timeline by construction), then carve the shifting duration out of whichever main-path bucket contains it and add it to DELAY | No (algorithmic) | n/a | `test_shifting_time_is_carved_out_of_cargo_not_double_counted` |
| A-010 | §9 | AI journey narrative must never fabricate a fact; Gemini API key is not provisioned in this environment | Build a fact sheet strictly from persisted reconstruction rows; try Gemini only if `GEMINI_API_KEY` is configured, otherwise generate deterministically from the same fact sheet so the feature is fully functional offline | Yes | `GEMINI_API_KEY`, `GEMINI_MODEL` | `test_narrative_is_grounded_and_does_not_invent_missing_stage` |
| A-011 | §9 | "Missing" vs "inferred" events: no inference source exists yet in the pipeline (no phase has built one) | Every currently-absent single-occurrence event is reported MISSING, never INFERRED, on this fixture; the `is_inferred`/`inference_reason` fields and code path exist and are exercised so a future inference rule (e.g. Phase 07+) can populate them without a schema change | Yes (per-rule) | n/a | `test_missing_ata_produces_unavailable_stage_not_zero_duration` |
