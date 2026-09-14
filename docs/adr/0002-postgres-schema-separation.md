# 2. Postgres Schema Separation

Date: 2026-09-14

## Context
We need to handle data across different lifecycle stages (raw ingestion, staging, canonical representation, analytics, etc.) while ensuring strict access and querying separation.

## Decision
We will use a single Postgres 16 database but strictly separate data using schemas (`raw`, `staging`, `canonical`, `analytics`, `audit`, `config`, `testkit`).

## Consequences
- Queries can still join across schemas if needed, without network overhead.
- Clear separation of concerns and easier role-based access control.
