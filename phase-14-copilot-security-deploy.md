# Phase 14 — Copilot, security hardening, deployment, documentation
**Model: `gemini-3.1-pro-high` for the copilot; `gemini-3.7-flash-medium` for deploy and docs;
then `claude-sonnet-4-6` for the final audit pass (reserved slot)**

Read `AGENTS.md`. Spec §14, §16, §17, §18, §19, §21 are the reference. Run this as three sessions.

---

## Session A — Copilot (`gemini-3.1-pro-high`)

Retrieval and tool-based analytics over governed data. The single hard rule: **the copilot never
answers an operational question from model memory when a database calculation is required.** It calls
tools; the tools call the same analytics, KPI and journey services the dashboards use.

Implement as Gemini function calling over a tool surface: query vessel calls, compute a lead time,
fetch a KPI result, list delays by dimension, compute a statistic for a cohort, fetch a journey, run a
correlation. Tools enforce the caller's role and data scope — the copilot cannot reach data the user
could not open directly. Test that explicitly.

Every answer contains, per spec §14: the direct answer; reporting period and filters; the supporting
metric and its definition; the relevant vessel calls or records as deep links; a chart or table where
useful; explanation and evidence; a data-quality caveat; a suggested operational action; and a method
note for any statistical claim.

For relationship questions: sample size, missingness, correlation method, coefficient, uncertainty or
significance where appropriate, segmented checks, a confounder warning, and an explicit statement that
correlation does not establish causation. The spec calls out an example claim about 85% occupancy and
42% waiting — never reproduce it unless the current data actually produces it.

Support follow-up context, saved conversations, export, feedback, citation deep-links, role-safe
responses, and complete audit logging of prompts and responses with sensitive-data controls.

Prompt-injection resistance: content arriving from uploaded files, OCR output or ingested records is
data, never instruction. Write adversarial tests — put an instruction inside a `Test_Note` field and a
vessel name and assert the copilot ignores it.

Test the questions in spec §14: highest turnaround vessels, causes of increasing pilot boarding time,
delays by berth, vessel-type comparison, highest variability stage, top bottlenecks, management
summary, tug delay report, P90 arrival lead time, SLA breaches, and the relationship questions. Each
answer must be reproducible — same question, same filters, same data, same numbers.

---

## Session B — Security, observability, deployment (`gemini-3.7-flash-medium`)

**Security (§17)**: encryption in transit and at rest; secrets in a managed vault, never in the repo;
tenant/port/terminal isolation verified by test; input validation; malware scanning on uploads; file
type and size restrictions; safe document processing; SQLi/XSS/CSRF/SSRF protection; secure headers;
PII masking for staff names where not operationally required; configurable retention, archive, legal
hold, backup, restore and deletion. Write `docs/threat-model.md` and a security test suite.

**AI governance (§17)**: grounded outputs, inference labels, confidence, human approval paths,
model and version logging, prompt/response audit, feedback mechanism.

**Observability (§18)**: structured logs with correlation ids, metrics, traces, health/readiness/
liveness, queue depth, connector status, data freshness and latency monitoring, job telemetry,
alerting. Define the service objectives from §18 and add load-test fixtures that measure against them
rather than asserting them.

**Deployment**: Vercel for `apps/web`; Railway for `apps/api`, `apps/worker`, Postgres and Redis; GCS
for artifacts; GitHub Actions for CI/CD with automated migrations on deploy. Environment-specific
configuration, backup schedule, and a documented disaster-recovery procedure. Deploy and verify — a
deployment that has not been exercised is not a deployment.

**Documentation (§21)**: README with setup/config/seed/test/build/deploy; complete the RTM with final
statuses; ADRs; ERD and data dictionary; canonical event catalogue and alias dictionary; data-source
onboarding template; OpenAPI spec with synthetic sample payloads; KPI and formula catalogue with a
versioning guide; DQ rule catalogue; test strategy and results; UX screen inventory and accessibility
checklist; runbooks for ingestion failure, data correction, merge/unmerge, recalculation,
backup/restore and incident response; user guides for administrator, steward, controller, analyst,
executive and report manager; and known limitations, assumptions and the production-hardening backlog.

---

## Session C — Final audit (`claude-sonnet-4-6`, reserved slot)

Adversarial review against spec §20's seventeen acceptance criteria and §21A.5's twelve
dataset-specific criteria. For each, state PASS or FAIL with the evidence — a test name, a harness
report line, or a file path. No criterion may be marked PASS on assertion alone.

Then hunt specifically for these, which are the failures most likely to have crept in:

1. Any placeholder control, dead link, empty card or hard-coded metric value.
2. Any metric displayed without a traceable formula, version and source records.
3. Any negative execution delay that was coerced, zeroed or flagged as invalid.
4. Any AI inference presented without its label, confidence and evidence.
5. Any auto-merge that could occur on name similarity alone or across a conflicting IMO or VCN.
6. Any quarantined record contributing to a KPI without disclosure.
7. Any synthetic VCN, expected value or `Intentional_Flag` reference inside application logic.
8. Any route missing an authorisation dependency, or any query missing a data-scope filter.
9. Any naive datetime, or any timestamp stored without its full envelope.
10. Any place where `UNAVAILABLE` is rendered or computed as zero.
11. Any throughput figure that sums across TEU, MT and Units.
12. Any expected value that could reach an actual-output field.

Write the findings to `docs/final-audit.md` with severity and a remediation plan, then fix everything
at HIGH or above.
