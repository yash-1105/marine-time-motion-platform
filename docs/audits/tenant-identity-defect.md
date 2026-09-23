# Tenant Identity Integration Defect

## Root cause

The authenticated development/demo users and service account are seeded with the tenant ID
`tenant-synthetic-01`. The frontend development principal uses the same ID. However, ingestion and
several analytics routers independently translated `tenant-synthetic-01` (and wildcard scopes) to
`synthetic-tenant`. The delays router did not apply that translation. The upload therefore persisted
the batch and canonical vessel calls as `synthetic-tenant`, while
`GET /api/v1/delays/service-timings` correctly filtered by the authenticated value
`tenant-synthetic-01` and returned no rows.

`synthetic-tenant` originated in the testkit loader, validation harness, legacy service defaults, and
router-local demo aliases. `tenant-synthetic-01` originated in seeded authentication records,
development JWT/session claims, and the frontend development authentication context.

## Identity trace

| Boundary | Tenant source before fix | Contract after fix |
|---|---|---|
| Authentication/JWT/session | `config.user.tenant_id` / `config.service_account.tenant_id` | Authenticated principal is authoritative |
| Development token | Hard-coded `synthetic-tenant` | Server setting `development_tenant_id` (`tenant-synthetic-01`) |
| Upload API | Router rewrote principal to `synthetic-tenant` | Exact concrete principal tenant |
| Ingestion manifest / `raw.batch` | Upload router value | Exact upload principal tenant |
| Raw/staging values | Batch ID linkage | Tenant inherited through the immutable batch |
| Canonical vessel calls | `raw.batch.tenant_id` | Same canonical tenant as the batch |
| Service requests/assignments/executions | Vessel-call foreign-key lineage | Same tenant as the owning vessel call |
| Journey, delays, analytics, KPI | Service-specific router aliases or engine argument | One tenant passed from the principal through every engine |
| Tenant-scoped APIs | Inconsistent local aliases; some client tenant overrides | Concrete principal tenant; mismatching query tenant is rejected with 403 |
| Synthetic fixture/harness | `synthetic-tenant` constant | Server-owned `development_tenant_id` and fixture manifest metadata |

Service assignments and executions do not duplicate `tenant_id`; they are scoped through
`ServiceRequest -> VesselCall`. Analytics and KPI results similarly retain their governed foreign-key
lineage. Direct tenant columns exist on batches, vessel calls, dashboard snapshots, report records,
and Copilot conversations.

## Canonical contract

`Authenticated Principal -> Canonical Tenant ID -> Upload Batch -> Raw/Staging -> Canonical Vessel
Call -> Journey/Service Timing -> Analytics/KPI -> Tenant-scoped API`

No runtime alias equivalence remains. A client-supplied tenant may only equal the authenticated
tenant. A wildcard principal cannot read or persist tenant data unless it is the synthetic local
principal, which the server binds to its configured development tenant.

## Historical-data safety

Read-only production API inspection found an authenticated tenant of `tenant-synthetic-01`, while
persisted demo batches/scorecard data were under `synthetic-tenant`. This is the same legacy demo
boundary error; there was no evidence of arbitrary real-tenant rewriting because non-demo tenant IDs
were passed through unchanged.

Migration `p4q5r6s7t8u9` normalizes only the known legacy demo ID on direct tenant columns. It keeps
all record IDs, batch IDs, checksums, source rows, foreign keys, audit history, and result lineage. It
refuses to run if both IDs already own ingestion batches, preventing an unreviewed cross-tenant
merge. The downgrade intentionally does not recreate the invalid split identity.

## Affected exposure

The divergence affected service-timing and leg-filtered delay exposure most visibly. It could also
cause inconsistent results across dashboard, operations, journey, analytics, KPI, quality, reporting,
alerts, outliers, bottlenecks, criticality, and Copilot routes because each had evolved its own tenant
resolver. The audit also found that `analytics.statistical_aggregate` and population-level
`analytics.kpi_result` rows had no tenant ownership, allowing a latest aggregate/result lookup to be
global. Migration `p4q5r6s7t8u9` adds tenant keys, tenant-aware aggregate uniqueness, and tenant-first
scorecard indexes; the engines and all reads now enforce those keys. These routes now share the
authenticated tenant contract. Strict tenant isolation remains in force; no query combines aliases
and no tenant filter was removed.
