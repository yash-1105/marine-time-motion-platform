# 3. Event-Occurrence Model over Wide Timestamp Table

Date: 2026-09-14

## Context
Vessel journeys have many timestamps (ETA, ATA, ATD, Pilot On Board, etc.). Storing these as columns on a single table (wide table) becomes unmanageable as new events are added or when multiple instances of the same event type occur.

## Decision
We will use an event-occurrence data model (e.g., `vessel_call_events` table with `event_type` and `timestamp`).

## Consequences
- Highly extensible to new port events without schema changes.
- Requires pivots or complex aggregations for reporting (which Polars/SQL views can handle).
