# Phase 11 — Frontend shell and the three evidence-facing screens
**Model: `gemini-3.7-flash-high`**

Read `AGENTS.md`. Spec §5, §12.2, §12.5, §12.6 and the accessibility requirement in §2 are the
reference. Everything on screen is backed by a real service call — there are no mock values in this
phase or any other.

## Design direction

This is a port control-room tool used on large displays during live operations, not a marketing SaaS
dashboard. Design accordingly:

- Information density is a feature. Operators scan; they do not browse. Resist the urge to chop
  content into identical rounded cards with soft shadows — that pattern wastes the screen and flattens
  hierarchy that actually matters here.
- The subject matter is maritime operations: timelines, tides of activity, berth occupancy as
  horizontal bands, vessel movement as directional flow. Let the visual language come from that,
  not from a generic template.
- Pick a palette that survives an operations room: high contrast, legible at distance and at an angle.
  Status must never be carried by colour alone — pair every status colour with a shape, glyph or text
  label, because spec §2 requires colour-independent statuses and a control room will have someone
  who needs that.
- One or two typefaces, a deliberate type scale, tabular figures for every timestamp and duration
  column so numbers align down the column.
- Motion only where it shows a state change the operator caused. No decorative entrance animations.

Record the token system (4–6 named colours, typefaces and roles, layout concept, principles) in
`docs/design-system.md` before building, and build against it.

## 1. Shell

Primary navigation per spec §5. Routes not yet built are absent from the nav, not present-and-dead.

Global filter bar: date range, port, terminal, berth, vessel type, movement type, shipping line,
vessel size, cargo type, data-quality status. Filter state is encoded in the URL, persists through
drill-down, and is shareable as a link that reproduces the exact view. Build this once as a shared
primitive; every screen consumes it.

Undismissable synthetic-data banner from phase 02, visible on every screen.

A reusable data-table primitive with filtering, sorting, server-side pagination, search, saved views,
column selection, export and row deep-linking — spec §2 requires this of every list, so building it
once properly is the whole game.

## 2. Vessel Calls

List of consolidated vessel calls with quality status, merge state, journey completeness and the key
durations. Drill into a single call. Show merge candidates and merged-from records with their
evidence. Every duration cell opens the traceability drawer: formula, version, source records,
filters, exclusions, quality status.

## 3. Vessel Journey (spec §12.5)

The centrepiece. For a selected call: arrival, pilotage, towage, berthing, cargo, shifting and
departure, as a swimlane by stakeholder against a time axis. Event markers with timestamp, source
icon and confidence. Duration ribbons. Waits, delays, clearances and handovers distinguished
visually. Anomalies marked. Actual path against standard path. A raw-evidence drawer reaching back to
the original workbook cell. Corrections with their history. Replay controls that step through the
journey chronologically. Export of a single-vessel journey report.

Test it against `SYNVCN2600070` (two conflicting ATAs — both must be visible with the canonical
selection explained), one of the eight shifting calls, and `SYNVCN2600018` (missing ATA — dependent
durations render as `Unavailable` with the reason, never as `0h` or `—`).

## 4. Data Quality (spec §12.6)

Scores by source, field, batch and domain, always expandable to their components. Issue aging.
High-criticality queue. Duplicate candidate review with side-by-side comparison and merge/unmerge
actions. Mapping coverage. Schema drift. Unresolved conflicts. Missing-event matrix. Remediation
throughput trend.

## 5. Accessibility — WCAG 2.2 AA, not aspirationally

Full keyboard navigation including the timeline and the data grid. Visible focus states. Semantic
labels and landmarks. Colour-independent status. Text alternatives and data tables for every chart.
Contrast checked. Respect `prefers-reduced-motion`. Add automated axe tests to CI and fix what they
find — do not suppress rules.

## Done when
Three screens run on real data with working filters, deep links and drill-through; every metric opens
its traceability drawer; `UNAVAILABLE` is visually distinct from zero; axe tests pass in CI; keyboard
navigation reaches every control including the journey timeline.
