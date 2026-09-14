# Maritime Operations Control-Room Design System (Phase 11)

## 1. Overview & Philosophy

The Marine Time & Motion Platform frontend is an operational control-room tool engineered for port operations centers, vessel traffic services (VTS), and marine terminals. It prioritizes:
- **Information Density:** High information throughput without visual noise. Operators scan rather than browse.
- **High Contrast & Legibility:** Optimized for large wall displays and desktop terminals viewed under varying ambient light conditions and viewing angles.
- **Maritime Operational Visual Language:** Direct representation of directional vessel movement, stage duration ribbons, berth occupancy, and timeline swimlanes.
- **Accessibility & Non-Color Reliance (WCAG 2.2 AA):** Status is never communicated by color alone. Every colored state is paired with an unambiguous glyph, badge, or text label.
- **Deterministic Traceability:** Every calculated metric allows one-click inspection of formula, version, source records, and quality state.
- **Zero Decorative Animations:** Motion is reserved solely for operator-initiated actions (drawer expansion, tab switching).

---

## 2. Color Palette & Functional Tokens

| Token Name | Hex Code | Purpose & Semantic Role |
|---|---|---|
| `--color-canvas-bg` | `#0f172a` / `#f8fafc` | Deep Slate / Operations Canvas Background |
| `--color-surface` | `#1e293b` / `#ffffff` | Elevated panels, cards, data table containers |
| `--color-border` | `#334155` / `#e2e8f0` | High-contrast table grid lines and container dividers |
| `--color-text-primary` | `#0f172a` / `#f8fafc` | High-contrast headings, primary identifiers (VCN, IMO) |
| `--color-text-secondary` | `#475569` / `#94a3b8` | Supporting metadata, unit labels, stage subtitles |
| `--color-status-active` | `#059669` (Emerald) | Active service stage, healthy record, PASS status `[✓]` |
| `--color-status-wait` | `#0284c7` (Sky) | Passive anchorage wait, scheduling gap, in-transit `[⏳]` |
| `--color-status-hold` | `#d97706` (Amber) | Clearance hold, steward review needed, WARNING `[⚠]` |
| `--color-status-critical` | `#dc2626` (Crimson) | Critical sequence violation, quarantine, FAIL status `[✕]` |
| `--color-status-inferred` | `#7c3aed` (Purple) | AI/Inferred observation requiring human audit `[⚡]` |
| `--color-status-unavailable` | `#64748b` (Slate) | Governed `UNAVAILABLE` / missing mandatory input `[⊘]` |

---

## 3. Typography & Numerical Alignment

- **Primary Font:** `Inter`, system font stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`).
- **Tabular / Monospace Font:** `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace`.
- **Numerical Alignment:** All duration columns, timestamps, IMO numbers, and VCNs enforce `font-mono` and CSS `font-variant-numeric: tabular-nums` to guarantee strict vertical alignment across dense table columns.
- **Type Scale:**
  - Micro / Meta: `10px` (`0.625rem`), uppercase, tracking-wider
  - Dense Body / Table: `11px` - `12px` (`0.75rem`)
  - Subheader / Card Title: `13px` - `14px` (`0.875rem`), font-semibold
  - Screen Header: `16px` - `18px` (`1.125rem`), font-bold

---

## 4. Operational Components

### 4.1 Global Filter Bar
- Sits below the application shell header.
- Manages 10 operational filter dimensions:
  1. Date Range (Start / End)
  2. Port (e.g. `ZADUR`)
  3. Terminal (e.g. `DCT`, `MPT`)
  4. Berth
  5. Vessel Type (Container, Bulker, Tanker, etc.)
  6. Movement Type (Arrival, Shifting, Sailing)
  7. Shipping Line
  8. Vessel Size (TEU ranges)
  9. Cargo Type
  10. Data Quality Status (Clean, Flagged, Quarantined)
- Encodes all state directly into URL parameters (`?port=ZADUR&vessel_type=Container...`), ensuring sharable deep-links and preservation across drill-downs.

### 4.2 Reusable Data Table
- High-density rows with alternating subtle stripes.
- Sortable headers with visual directional indicators (`▲` / `▼`).
- Integrated instant search filtering.
- Pagination controls with items per page and record range display (`1-25 of 72`).
- Row drill-down on click to detailed journey view.

### 4.3 Journey Swimlane & Timeline Ribbon
- Horizontal sequence representing the 8 major operational phases:
  `Arrival → Anchorage Wait → Inward Movement → Berthing → Cargo Operations → Shifting (Optional) → Outward Movement → Departure`
- Visual ribbons sized proportional to stage duration.
- Distinct styling for Active Service vs Passive Wait vs Operational Delays vs Clearances.
- Explicit markers for sequence anomalies (e.g. pilot boarded before scheduled).

### 4.4 Traceability Drawer
- Slide-over panel triggered by clicking any duration or metric cell.
- Displays:
  - Metric Name & Formatted Duration
  - Formal Formula & Formula Version
  - Source Records & Event Identifiers
  - Applied Global & Cohort Filters
  - Exclusions / Quarantined flags
  - Data Quality validation status

---

## 5. Non-Negotiable Rules

1. **No Fake / Placeholder Data:** Every metric and row originates from real backend endpoints (`/api/v1/...`).
2. **Never Fabricate Zeroes:** Missing or uncomputable metrics render explicitly as `UNAVAILABLE` with stated reason.
3. **Signed Delays:** Negative execution delays render with `-` sign and badge `EARLY SERVICE`.
4. **No Dead Navigation:** Only fully implemented screens are present in the sidebar.
