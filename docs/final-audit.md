# Final adversarial audit — Phase 16

**Audit date:** 2026-09-15  
**Scope:** repository state through Phase 15, local PostgreSQL/Redis readiness, focused security/Copilot tests, frontend production build, static code/configuration review.  
**Remediation update:** expected-output reconciliation now resides in the validation-only `testkit` package; application analytics and routes no longer read the oracle schema.

## Evidence checked

| Area | Evidence | Result |
|---|---|---|
| Auth/RBAC/audit | `tests/test_auth_rbac.py` (7 passed when isolated), route dependency review | Partially verified |
| Copilot scope/tools/injection | `tests/test_copilot_core.py` (5 passed) | Pass for covered paths |
| Security headers/uploads | `tests/test_security_hardening.py` (4 passed) | Pass for covered paths |
| Dependency health | `/ready` locally returned PostgreSQL and Redis `ok` | Pass locally |
| Web UX/build | `apps/web: npm run build` | Pass |
| Full test suite | `make test` started 84 tests but did not complete cleanly in the polluted local database; the repository scope test later failed because its default list limit omitted its inserted record | Fail/blocker |
| Validation harness | `make validate` reproduces existing fixture-reset execution failure | Fail/blocker |
| Deployment discovery | `railway.json`, compose, Git remote inspected; no Railway/Vercel/GCS credentials or deployment URL are available | Not verified |

## Findings

| Severity | Component | Evidence | Impact | Recommended action |
|---|---|---|---|---|
| Critical | Analytics/testkit isolation | `apps/api/services/analytics/engine.py` imports `ExpectedOutput`, exposes reconciliation to API code, and embeds fixture VCN exceptions; `apps/api/services/outliers/engine.py` embeds a fixture VCN and expected turnaround override. | Synthetic oracle values and fixture-specific business logic can influence application analytics, violating governed-data and fixture-isolation requirements. | Move reconciliation/oracle handling to `testkit`/harness-only code; replace fixture-specific outlier logic with ordinary configured rules; remove production reconciliation API access to `testkit`. |
| Resolved High | Validation/analytics persistence | `analytics.lead_time_result` is now constrained by `(vessel_call_id, definition_id)` and existing duplicates are deduplicated by migration; merge transfer retains the survivor event rather than transferring a duplicate canonical occurrence. Focused analytics/identity tests passed; `make validate` PASS artifact was produced. | Repeated analytics and fixture reset no longer reproduced the observed failures. | Retain idempotency regression coverage in CI. |
| High | Deployment evidence | No live Vercel, Railway API/worker, GCS IAM, exact production CORS origin, delivery adapter, scheduler, or backup/restore evidence is available. | Production claims cannot be verified. | Execute controlled deployment checklist in `docs/runbooks/deployment.md`; retain evidence. |
| Medium | Upload security | Extension/size/container checks exist, but malware scanning and content-disarm are not integrated. | Malicious but structurally valid documents may enter processing. | Add a managed malware scan/quarantine adapter before production uploads. |
| Medium | Reporting storage/delivery | Local-path renderer/storage and simulated delivery paths exist; GCS adapter and real delivery/scheduler execution remain unverified. | Artifact durability/distribution is not production-ready. | Implement and exercise GCS/document repository + mail/notification adapters with IAM tests. |
| Low | Test execution hygiene | Full suite is database-state sensitive. | Developers can obtain inconsistent local results. | Require ephemeral database/isolated tenant per suite in CI. |
| Low | Repository test determinism | `test_repository_level_data_scope` assumes its row appears in a default limited list on a polluted database. | Scope behaviour cannot be asserted reliably from that test run. | Use an isolated database or explicit pagination in the test; do not treat this as a scope-bypass finding. |
| High | Fixture-bound outlier test | `tests/test_delays_bottlenecks.py::test_dq008_extreme_operational_outlier` expects a fixture VCN/oracle override in `OutlierEngine`; it fails after removal of that production override. | The test must be relocated to testkit/harness validation rather than forcing fixture behaviour back into application code. | Refactor the test and reconciliation helper into validation-only code while retaining the DQ-008 acceptance assertion there. |

## Verified safeguards

- Copilot exposes a fixed tool allowlist, rejects SQL/query/scope overrides, keeps Sarvam credentials backend-only, and labels fallback execution modes.
- Report run lookup applies tenant, port, and terminal scope.
- Exact configured CORS origins, cookie-write origin checks, security headers, bounded uploads, and dependency readiness checks are implemented.
- Production startup now rejects weak/default JWT settings, empty CORS origin configuration, and insecure cookies.

## Accessibility/UX review

Source review found labelled Copilot input, loading states, error states and no inert report-template entry points. A real browser keyboard/screen-reader/mobile exercise was not possible without the deployed frontend; it remains a deployment acceptance task.
