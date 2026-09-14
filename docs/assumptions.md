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
