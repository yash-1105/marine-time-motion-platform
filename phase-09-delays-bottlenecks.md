# Phase 09 — Delay analysis, bottlenecks, outliers, criticality
**Model: `gemini-3.7-flash-high`**

Read `AGENTS.md`. Spec §10.4 to §10.9 are the reference.

## 1. Delay causes (spec §10.4)

Seed the categories: Pilot, Tug, Berth Non-Availability, Weather, Regulatory Clearance, Terminal
Readiness, Cargo Operation, Equipment Breakdown, Crane Downtime, Mooring, Documentation, Vessel-Side,
Port-Side, External/Uncontrollable, Other. The fixture uses four (Marine Service, Terminal, Weather,
Vessel/Other) — map them onto the canonical set via config and keep the source values visible.

Reason and category are distinct fields and must not be conflated.

Multiple causes per delay, each with an allocated duration and a primary/secondary designation. The
allocations must sum to the delay duration or the remainder is explicitly unallocated.

**Inference.** When a reason is absent, infer a probable cause only from evidence: stage, late request,
resource availability, berth occupancy, incident data, terminal readiness. Output the proposed cause,
a confidence, the factors supporting it, the factors opposing it, and a human review state. An
inferred cause is never stored as confirmed, never overrides a confirmed reason, and is visually
labelled everywhere it appears. All 41 fixture delays are `Confirmed` — so inference must be tested
against a synthetic fixture of your own, and must demonstrably decline to overwrite them.

Recalculate delay duration from `Served_Time − Scheduled_Time` and reconcile against the supplied
`Delay_Hours`, flagging mismatches beyond tolerance. Resolution status drives the action workflow and
must never alter the historical delay duration.

DQ-007 (`SYNVCN2600054`, positive delay with blank reason and category) must raise a mandatory
delay-reason review at MEDIUM severity.

## 2. Bottlenecks (spec §10.5)

Score from all of: duration, frequency, variability, tail risk, turnaround contribution, repeated
target breach, business criticality. Weights configurable.

**Never label the longest stage alone as the bottleneck.** Write a test with a long-but-stable stage
and a short-but-highly-variable stage that asserts the ranking is not simply by duration.

Detect resource bottlenecks (pilot, tug, crane shortage, berth congestion) and process bottlenecks
(waits, clearances, repeated delays) separately.

## 3. Outliers (spec §10.6)

Detect: turnaround above P90; pilot boarding delay beyond configurable sigma or robust MAD threshold;
cargo duration unusual for vessel size or volume; tug before pilot where invalid; late first crane
move after all fast; impossible chronology; high-criticality cases.

Classify as `OPERATIONAL_OUTLIER | DATA_QUALITY_OUTLIER | PROCESS_VIOLATION | EXTREME_DELAY_CASE |
HIGH_CRITICALITY_CASE`.

**DQ-008** is the case: `SYNVCN2600063` has an expected turnaround of 720 hours against a calculated
86.5. This is a deliberate oracle override, so handle it on two fronts — the analytics engine flags
the *expected* value as an extreme outlier in P90 and tail-risk behaviour per the test design, and the
harness reports the actual-vs-expected divergence as a documented, intentional case rather than a
silent failure. Exclusion and inclusion of outliers must be transparent on every affected statistic,
and every outlier drills through to its vessel call.

## 4. Criticality (spec §10.8)

Duration, Variability and Tail-Risk scores each 1–5 from configurable thresholds. Overall = arithmetic
mean by default, with optional governed weights. Bands: 1.0–1.9 Low, 2.0–2.9 Moderate, 3.0–3.9 High,
4.0–5.0 Critical.

**Always display the three component scores alongside the overall.** No black-box score anywhere in
the API response or the UI.

## 5. Alerts and actions (spec §15)

Build the rule model and evaluation now, since the data is here: SLA breach, deteriorating trend,
critical bottleneck, extreme P90 case, missing mandatory event, invalid sequence, duplicate call,
stale feed, resource shortage, berth conflict, severe incident, failed report or integration. With
severity, threshold, suppression, deduplication, owner, escalation, acknowledgement, resolution,
comments, attachments, linked action item, due date and audit history. In-app notification delivery is
enough for this phase; email delivery can ride on phase 13's distribution layer.

## Done when
Bottleneck ranking demonstrably is not duration-ordered; criticality always exposes components;
DQ-007 and DQ-008 behave as specified; inferred causes never overwrite confirmed ones and are labelled;
outlier inclusion/exclusion is transparent; alerts fire on the fixture and can be acknowledged and
actioned.
