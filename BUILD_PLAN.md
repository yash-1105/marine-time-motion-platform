# Build Plan — Marine Time & Motion Platform

How to take a 1,038-line "Level 100" specification and actually ship it with Antigravity CLI.

---

## 1. Read this first: scope reality

The spec as written describes 12–18 months of work for a team of six. It asks for OCR pipelines,
Navis N4 connectors, AIS geofencing, peer-port benchmarking, yard and gate and rail analytics, a
full alerting engine, four report formats on schedules, and a grounded copilot — on top of a
governed data platform. You have one person and one dataset.

The good news is that the spec tells you how it will be judged, and it judges you on the fixture.
§21A.5 and §20 are the real acceptance criteria, and every single one of them is reachable with the
data in the workbook. So the plan is:

**Build the governed spine completely. Build everything the fixture can prove. Register everything
else honestly as a backlog item with its required inputs.**

That is not cutting corners — §6 of the spec explicitly instructs you to record ambiguity, implement
a configurable default, and log it. A KPI that exists in the registry with status `NO_SOURCE_DATA`
and a documented input list scores better than a KPI with a fabricated number behind it. The spec
says so in §2 and §20.17.

What that means concretely:

| Fully built | Registered + backlogged with rationale |
|---|---|
| Ingestion, mapping, lineage, dry-run, idempotency | OCR / scanned register pipeline (adapter + contract tests only) |
| DQ rule engine, chronology DAG, quarantine, scoring | Live AIS / VTS streaming connectors (adapter + sandbox connector) |
| Identity resolution, merge/unmerge, survivorship | Peer-port benchmark sets (schema + admin UI, no licensed data) |
| Journey reconstruction, conflict resolution, corrections | Yard, gate, rail KPIs 31–40 (registry entries, `NO_SOURCE_DATA`) |
| Duration semantics, lead-time catalogue, custom builder | Crane-level productivity and downtime KPIs |
| Statistics, outliers, bottlenecks, criticality | Email/SFTP ingestion, webhook DLQ replay UI |
| KPI engine + all 55 registry entries | Report *scheduling execution* (architecture built, cron deferred) |
| Six dashboards + drill-through | Multi-tenant onboarding beyond a single synthetic tenant |
| One report template in all four formats | |
| Grounded copilot over governed data | |
| RBAC, audit, accessibility, deploy, docs | |

Write this table into `docs/scope-decisions.md` on day one and show it to your mentor. It converts
"you didn't build everything" into "here is my governed scope with reasoning", which is the
difference between a failed PS-II project and a strong one.

---

## 2. Model routing strategy

Antigravity CLI's model list moves fast. Run `agy models` before you start and map my
recommendations onto what you actually see. As of late August 2026 the roster was:

```
gemini-3.7-flash-high / -medium / -low
gemini-3.6-flash-*  gemini-3.5-flash-*
gemini-3.1-pro-high / -low
claude-sonnet-4-6
claude-opus-4-6-thinking
gpt-oss-120b-medium
```

A newer Flash (3.8) has been appearing in recent builds. If `agy models` shows a Flash newer than
3.7, use it wherever I say `gemini-3.7-flash-high`.

### The routing rule

**Pro for semantics. Flash for volume. Claude for rescue.**

| Work type | Model | Why |
|---|---|---|
| Architecture, data modelling, rule-engine design, journey graph, duration semantics, reconciliation logic | `gemini-3.1-pro-high` | These phases encode decisions that everything downstream inherits. A wrong call here costs you three phases of rework. Worth the slower, more expensive run. |
| Feature implementation against a settled design: endpoints, services, React pages, tests | `gemini-3.7-flash-high` | This is 70% of the build. Flash-high is strong on well-specified implementation and you can run many more iterations per quota unit. |
| Boilerplate, config YAML, docs, seed data, CRUD scaffolding, OpenAPI polish | `gemini-3.7-flash-medium` | Cheapest thing that works. Don't spend reasoning budget on a Dockerfile. |
| A phase that has failed twice on Pro, or a reconciliation bug you cannot isolate | `claude-sonnet-4-6` | Reserve slot. Different failure modes from Gemini, so it breaks deadlocks. |
| Final security + acceptance audit | `claude-sonnet-4-6` | Reserve slot. Adversarial review benefits from a second family of model. |
| Anything | `claude-opus-4-6-thinking` | Budget zero. Only if Sonnet also stalls on a critical-path blocker. |

Across the 15 phases below that comes to roughly **6 Pro sessions, 9+ Flash sessions, 2 reserved
Sonnet slots, 0 Opus**. That respects your constraint while putting the expensive reasoning exactly
where the spec's difficulty actually is.

### Switching models

```bash
agy --model gemini-3.1-pro-high            # start a session on Pro
agy --model gemini-3.7-flash-high
/model                                     # switch mid-session
```

Feed a phase prompt from a file rather than pasting:

```bash
agy --model gemini-3.1-pro-high --prompt "$(cat prompts/phase-00-foundation.md)"
```

---

## 3. Session hygiene (this matters more than model choice)

1. **`AGENTS.md` does the heavy lifting.** It is in the repo root and Antigravity loads it every
   session. That is why the phase prompts are short — they don't repeat the rules. Never delete it,
   and update §6 if you learn new fixture facts.
2. **One phase per session.** Long sessions degrade: context fills with tool output and the model
   starts forgetting the non-negotiables. Finish a phase, commit, `/clear` or exit, start fresh.
3. **Commit before every phase.** A phase that goes wrong is then one `git reset --hard` away from
   recovery, not an archaeology exercise.
4. **Run the harness after every phase from P05 onward.** `make validate` should go from "0 of 8
   metrics reconcile" to "8 of 8" gradually. If a number that was passing starts failing, you
   regressed — fix it in the phase that broke it, not later.
5. **Never let the agent edit `/fixtures`.** Add it to `.gitignore` for writes and check
   `git status` on it after each phase. Agents under pressure will "fix" test data.
6. **Paste back failures verbatim.** When something fails, give the agent the actual traceback and
   the actual harness output, not your summary of it.

---

## 4. Phase map

Each phase is one session, ends runnable, ends committed. Prompts are in `prompts/`.

| # | Phase | Model | Ends when |
|---|---|---|---|
| 00 | Foundation: repo, RTM, ADRs, compose, CI | `gemini-3.1-pro-high` | `docker compose up` serves a health endpoint and a homepage; RTM exists |
| 01 | Canonical data model + migrations + config seed | `gemini-3.1-pro-high` | Migrations apply clean; event catalogue, alias dictionary, KPI registry, DQ rules seeded from YAML |
| 02 | Auth, RBAC, data scope, audit trail | `gemini-3.7-flash-high` | 9 roles enforce action+scope; every sensitive action writes an append-only audit event |
| 03 | Ingestion + lineage + Load Synthetic Dataset | `gemini-3.1-pro-high` | Workbook imports through the UI; raw immutable; idempotent replay; `testkit` loader isolated |
| 04 | Data quality rule engine | `gemini-3.1-pro-high` | Chronology DAG validates without false positives on parallel events; DQ-003/004/005/006/007/009 fire |
| 05 | Identity resolution, duplicates, merge/unmerge | `gemini-3.7-flash-high` | DQ-001 and DQ-002 behave as specified; merge is evidenced, audited, reversible |
| 06 | Journey reconstruction | `gemini-3.1-pro-high` | 72 calls reconstruct; DQ-010 conflict preserved and steward-resolvable; corrections don't overwrite raw |
| 07 | Time & motion analytics engine | `gemini-3.1-pro-high` | All 8 expected metrics computed; custom lead-time builder works; statistics correct |
| 08 | KPI engine + all 55 registry entries | `gemini-3.7-flash-high` | 55 registered, computable ones compute, rest are `NO_SOURCE_DATA`; alias/duplicate handling |
| 09 | Delays, bottlenecks, outliers, criticality | `gemini-3.7-flash-high` | Component scores visible; DQ-008 handled as extreme outlier; inferred vs confirmed separated |
| 10 | `run-synthetic-validation` harness | `gemini-3.1-pro-high` | `make validate` produces machine + human reports; 8/8 metrics; 10/10 DQ cases |
| 11 | Frontend shell + Vessel Calls, Journey, Data Quality | `gemini-3.7-flash-high` | Real data, real filters, deep links, drill-through, WCAG 2.2 AA |
| 12 | Executive, KPI, Delay dashboards + T&M Explorer | `gemini-3.7-flash-high` | Every card drills to evidence; totals reconcile with API and DB |
| 13 | Reporting (PDF/XLSX/PPTX/DOCX) + alerts and actions | `gemini-3.7-flash-medium` | Daily Operations report renders in 4 formats from governed services |
| 14 | Copilot, security hardening, deploy, docs | `gemini-3.1-pro-high` → then `claude-sonnet-4-6` for audit | Copilot answers are grounded and cited; deployed to Vercel + Railway; docs complete |

Sequencing note: phases 03→07 are the spine. If you run short on time, a project that nails 00–07 and
10 with two dashboards will assess far better than one that has fifteen half-wired screens.

---

## 5. Deployment topology

```
GitHub ──┬─→ Vercel        apps/web (Next.js)
         └─→ Railway       apps/api (FastAPI) + apps/worker (Dramatiq)
                           + Postgres 16 + Redis
GCP      ──→ GCS bucket    uploads, OCR artifacts, generated reports
         ──→ Gemini API    copilot + narrative generation + mapping suggestions
```

Set these up in phase 00 with empty apps so you never face a first-deploy at the end:

```bash
railway init && railway add --database postgres && railway add --database redis
vercel link
gcloud storage buckets create gs://<project>-tms-artifacts --location=asia-south1
```

Keep `DATABASE_URL`, `REDIS_URL`, `GEMINI_API_KEY`, `GCS_BUCKET`, `OIDC_*` in Railway and Vercel
project variables, mirrored in `.env.example` with dummy values.

---

## 6. Order of operations for you, today

1. Create the repo, drop in `AGENTS.md`, the spec at `docs/spec/LEVEL_100_SPEC.md`, and the workbook
   at `fixtures/`.
2. Commit. Push.
3. Run phase 00 on `gemini-3.1-pro-high`.
4. Verify, commit, move to phase 01.

Do not skip ahead to dashboards because they demo well. The dashboards are worthless if the numbers
behind them are not reconciled, and the harness in phase 10 is what proves they are.
