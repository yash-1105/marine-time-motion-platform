# Phase 02 — Authentication, RBAC, data scope, audit trail
**Model: `gemini-3.7-flash-high`**

Read `AGENTS.md`. The data model from phase 01 is in place. Build the access layer that every later
endpoint will depend on, so that authorisation is never retrofitted.

## Deliverables

**1. Authentication**
- OIDC/OAuth2 authorization-code flow with PKCE, structured to be Microsoft Entra ID compatible.
  Provider config comes from environment, never hard-coded.
- A local development provider (self-hosted, seeded users) that is refused at startup when
  `ENVIRONMENT != development`. Make that a test.
- Session handling: short-lived access token, refresh, revocation, configurable idle and absolute
  timeouts, secure cookie flags.
- Service accounts for integration with scoped machine credentials and a documented rotation
  procedure. Credentials are hashed at rest.

**2. Authorisation**
- Action-based permissions, exactly the verb list in spec §4: view, create, edit, approve, reject,
  merge, unmerge, recalculate, publish, export, configure, administer, audit.
- Data scope attached to the principal: tenant, port, terminal. Scope filtering happens in the
  repository layer, not in route handlers, so a forgotten filter is impossible rather than unlikely.
  Implement this as a query-builder that requires a scope argument.
- Seed the 9 roles from `config/roles.yaml` with their permission sets.
- A FastAPI dependency `require(permission, resource)` used by every protected route. Add a test that
  enumerates all registered routes and fails if any non-public route lacks it.

**3. Audit trail**
- Every one of these writes an `audit.audit_event`: login, logout, failed auth, view of a record
  flagged sensitive, export, correction, merge, unmerge, rule change, formula change, config change,
  report publication, recalculation, administrative action, synthetic-dataset load or reset.
- Each event records actor, role, action, resource type and id, before/after where applicable,
  correlation id, IP, user agent, timestamp. Append-only is enforced at the database level already —
  add a test proving UPDATE and DELETE are rejected.
- Export actions additionally record the filter set and row count, because spec §17 requires sensitive
  exports to be logged with enough detail to reconstruct what left the system.

**4. Frontend**
- Auth flow wired in `apps/web`, protected routes, role-aware navigation that hides what the user
  cannot action (and the API still refuses it — never rely on hidden UI for security).
- A visible synthetic-data banner component, driven by the tenant's `is_synthetic` flag, that cannot
  be dismissed. Required by spec §21A.1.2.

## Constraints
- No permission logic duplicated between frontend and backend. Frontend reads a permissions payload
  from the API.
- Do not build user-management CRUD screens beyond what is needed to demonstrate role switching; the
  admin console comes later.

## Done when
Tests prove: each of the 9 roles can do exactly its permitted actions and no others; data scope
filters at the repository layer; every protected route has an authorisation dependency; audit rows are
written for all listed actions and cannot be modified; the local dev provider refuses to start outside
development.
