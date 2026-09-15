# Final adversarial audit — Phase 16

**Audit date:** 2026-09-15  
**Scope:** repository state through Phase 15, local PostgreSQL/Redis readiness, focused security/Copilot tests, frontend production build, static code/configuration review.  
**Final remediation update:** fixture loading, oracle reconciliation, and testkit ORM declarations reside in the validation-only root `testkit` package. Production API, worker, and web code have no fixture/oracle/synthetic-VCN dependency.

## Evidence checked

| Area | Evidence | Result |
|---|---|---|
| Auth/RBAC/audit | `tests/test_auth_rbac.py` (7 passed when isolated), route dependency review | Partially verified |
| Copilot scope/tools/injection | `tests/test_copilot_core.py` (5 passed) | Pass for covered paths |
| Security headers/uploads | `tests/test_security_hardening.py` (4 passed) | Pass for covered paths |
| Dependency health | `/ready` locally returned PostgreSQL and Redis `ok` | Pass locally |
| Web UX/build | `apps/web: npm run build` | Pass |
| Full test suite | `make test` | Pass (86 tests) |
| Validation harness | Retained `validation_report.{md,json}` and `validation_history.json`: PASS; 72/72 base calls and journeys, 8/8 targets, 10/10 DQ, 41/41 delays, 7/7 dashboard/API/database reconciliations | Pass |
| Deployment discovery | `railway.json`, compose, Git remote inspected; no Railway/Vercel/GCS credentials or deployment URL are available | Not verified |

## Findings

| Severity | Component | Evidence | Impact | Recommended action |
|---|---|---|---|---|
| Resolved Critical | Analytics/testkit isolation | Reconciliation, fixture loader, and testkit ORM declarations moved to root `testkit`; production reconciliation route, fixture-specific outlier override, and fixture-only frontend views were removed. Static search of API, worker, web, and contracts found no fixture/oracle/testkit/synthetic-VCN dependency. | Application analytics and UI no longer read or present test-oracle data. | Enforce with CI static check. |
| Resolved High | Validation/analytics persistence | `analytics.lead_time_result` is now constrained by `(vessel_call_id, definition_id)` and existing duplicates are deduplicated by migration; merge transfer retains the survivor event rather than transferring a duplicate canonical occurrence. Focused analytics/identity tests passed; `make validate` PASS artifact was produced. | Repeated analytics and fixture reset no longer reproduced the observed failures. | Retain idempotency regression coverage in CI. |
| High | Deployment evidence | No live Vercel, Railway API/worker, GCS IAM, exact production CORS origin, delivery adapter, scheduler, or backup/restore evidence is available. | Production claims cannot be verified. | Execute controlled deployment checklist in `docs/runbooks/deployment.md`; retain evidence. |
| Medium | Upload security | Extension/size/container checks exist, but malware scanning and content-disarm are not integrated. | Malicious but structurally valid documents may enter processing. | Add a managed malware scan/quarantine adapter before production uploads. |
| Medium | Reporting storage/delivery | Local-path renderer/storage and simulated delivery paths exist; GCS adapter and real delivery/scheduler execution remain unverified. | Artifact durability/distribution is not production-ready. | Implement and exercise GCS/document repository + mail/notification adapters with IAM tests. |
| Resolved Low | Repository test determinism | The repository scope test now searches for its unique inserted records, so pagination cannot mask the scope assertion; `make test` passes. | Scope coverage is deterministic without changing repository pagination. | Continue using isolated databases in CI where available. |
| Resolved High | Fixture-bound outlier test | Outlier tests now assert evidence-backed observed anomalies and governed exclusion without fixture identifiers. | Production behavior remains fixture-independent. | Retain regression coverage. |

## Verified safeguards

- Copilot exposes a fixed tool allowlist, rejects SQL/query/scope overrides, keeps Sarvam credentials backend-only, and labels fallback execution modes.
- Report run lookup applies tenant, port, and terminal scope.
- Exact configured CORS origins, cookie-write origin checks, security headers, bounded uploads, and dependency readiness checks are implemented.
- Production startup now rejects weak/default JWT settings, empty CORS origin configuration, and insecure cookies.
- DQ-008 is now verified as the documented validation-only `ExpectedOutputs` discrepancy: reconciliation excludes its 720h oracle while the governed canonical turnaround remains 86.50h. It is not a production outlier override.

## Accessibility/UX review

Source review found labelled Copilot input, loading states, error states and no inert report-template entry points. A real browser keyboard/screen-reader/mobile exercise was not possible without the deployed frontend; it remains a deployment acceptance task.
