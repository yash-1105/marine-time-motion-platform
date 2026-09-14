# 4. timestamptz + UTC Storage with Port-Local Display

Date: 2026-09-14

## Context
Timezones are a common source of bugs in marine operations. Ports operate in local time, but analytics often require absolute timeline comparison.

## Decision
All timestamps will be stored as `timestamptz` (UTC) in PostgreSQL. The UI will display times in the port's local timezone (e.g., `Africa/Johannesburg`).

## Consequences
- Prevents timezone ambiguity at the data layer.
- Frontend must handle timezone conversion for display.
