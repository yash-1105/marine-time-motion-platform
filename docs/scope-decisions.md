# Scope Decisions

As per §6 of the specification, the following scoping decisions govern the implementation of the platform. We rely entirely on the provided synthetic fixture data for validation. Where source data is unavailable in the fixture, the feature is registered and backlogged with rationale.

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
| Daily Operations report workflow, approval, publication, artifact access and delivery log | Four registered report templates (Weekly, Monthly, Quarterly, Benchmark) are explicitly deferred; scheduler invocation interface exists but production cron deployment remains deferred |
| Grounded copilot over governed data | |
| RBAC, audit, accessibility, deploy, docs | |
| Security headers, dependency readiness, bounded upload validation, structured request telemetry, and deployment/security runbooks | Malware scanning/content-disarm, live GCS IAM verification, live backup restore, and deployed scheduler exercise require production integrations and credentials |
