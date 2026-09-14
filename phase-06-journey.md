# Phase 06 — Vessel journey reconstruction
**Model: `gemini-3.1-pro-high`**

Read `AGENTS.md`. Spec §9 is the reference. This phase turns a pile of events into a journey, and
everything in phases 07–12 reads from what you build here.

## 1. Reconstruction

For each vessel call, build a chronological event graph against the journey template in
`config/journey_templates.yaml`. The default reference flow is spec §9's: pre-arrival → clearances →
ETA/ATA → anchorage → arrival service request → pilot boarding → breakwater in → towage → berthing →
pilot disembark → health/immigration/customs → cargo operations → lashing → optional shifting →
unberthing → departure service request → departure pilot boarding → towage → pilot disembark →
breakwater out → port limit out → ATD.

Branches to model: IMDG cargo requiring IMDG clearance; deep-sea (COPRAR + inbound EDI) vs coastal
(inbound EDI); clearance failure halting operations or moving the vessel aside; shifting occurring
zero, one or many times. The T-21/T-14/T-7/T-5/T-3 day and 24/4/2 hour and 12/6/2.5 NM milestones are
configurable template offsets, not hard-coded rules.

Per vessel call, produce and persist:
- unified chronological timeline
- stage grouping with durations
- actual path versus standard path, with deviations named
- missing events and (separately, and clearly labelled) inferred events
- source confidence and unresolved conflicts
- stakeholder handovers and the wait between handovers, using the spec §9 actor list
- decomposition into active service, passive wait, hold, delay and unclassified time, where the
  components sum to the total without double-counting overlapping stages
- an operational deviation report
- a versioned reconstruction history, so a re-run after a rule change is comparable to the prior run

## 2. Canonical occurrence selection

When multiple source records observe the same event, select a canonical occurrence using source
priority, verification status, confidence score and the configured conflict policy — and **retain
every observation**. The canonical choice is a decision with evidence, not a deletion.

**DQ-010** is the test: `SYNVCN2600070` has two ATA events five hours apart — `EV-0070-005` (AIS,
15:22, Verified, 0.99) and `EV-CONFLICT-001` (Manual Log, 20:22, Conflicting, 0.99). Required
behaviour: both observations preserved and visible; a conflict issue raised; source and confidence
compared side by side; a canonical selection proposed with reasoning; a steward able to override with
the decision audited. Downstream metrics must state which observation they used.

## 3. Corrections

A steward correction creates a **new canonical observation** carrying reason, actor, timestamp and
approval state. It never mutates raw and never mutates the prior canonical value — that becomes
superseded, with history. Recalculation after an approved correction is triggered and traceable.

## 4. AI summary

Generate a factual per-call narrative with Gemini, grounded strictly in the reconstructed record and
citing internal record ids. It may not introduce any fact not present in the journey. It is labelled
as generated. Add a test that feeds a journey with a deliberately missing stage and asserts the
narrative does not invent it.

## 5. Expected results on the fixture

All 72 base calls reconstruct. Eight calls (every ninth) carry shifting events
(`SHIFT_PILOT_ON_BOARD`, `SHIFT_ALL_FAST`) and must reconstruct with a shifting stage present — and
the other 64 must reconstruct correctly with zero shifts, no phantom stage, no null-shift errors.

The fixture carries 26 distinct event names against a much larger canonical catalogue. Events absent
from the fixture produce `UNAVAILABLE` stages, not zero-duration stages. Make that distinction
visible in the output shape.

## Done when
72 of 72 calls reconstruct; the 8 shifting calls and the 64 non-shifting calls both handle correctly;
DQ-010 preserves both ATAs and requires governed resolution; a correction creates a new observation
and triggers recalculation without touching raw; stage decomposition sums correctly with no
double-counted overlap; `make validate` reports journey reconstruction coverage.
