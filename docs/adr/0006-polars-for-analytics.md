# 6. Polars for Analytics

Date: 2026-09-14

## Context
The platform must calculate complex time-and-motion durations, KPIs, and perform anomaly detection over large datasets.

## Decision
We will use Polars in the Python service layer for heavy analytical compute.

## Consequences
- Extremely fast vectorized operations.
- Safer than pandas for strict typing and lazy evaluation.
