"""
AI-generated per-vessel-call journey narrative (phase-06-journey.md §4, spec §9).

The narrative is grounded strictly in the reconstructed record: it is built from a fact sheet
assembled entirely from persisted StageOccurrence/JourneyInstance rows, cites internal record ids,
and is always labelled as generated (inference_status). It never states a fact that is not present
in the fact sheet, and unavailable stages are always reported as unavailable, never invented.

When `settings.gemini_api_key` is configured, generation is delegated to Gemini with the fact
sheet as the *only* permitted source of truth (the prompt forbids adding anything else); if the
key is absent, unset, or the call fails for any reason, a deterministic template-based generator
produces the narrative directly from the same fact sheet, so the feature always works end to end.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.core.config import settings
from apps.api.models.canonical import VesselCall
from apps.api.models.journey import JourneyInstance, JourneyNarrative, StageOccurrence


def build_fact_sheet(db: Session, instance: JourneyInstance, vc: VesselCall) -> Dict[str, Any]:
    stages = db.execute(
        select(StageOccurrence)
        .where(StageOccurrence.journey_instance_id == instance.id)
        .order_by(StageOccurrence.sequence_index, StageOccurrence.shift_occurrence_index)
    ).scalars().all()

    stage_facts = []
    grounding_ids = [str(instance.id), str(vc.id)]
    for s in stages:
        fact = {
            "stage": s.stage_name,
            "shift_occurrence_index": s.shift_occurrence_index,
            "availability": s.availability,
            "duration_hours": s.duration_hours,
            "deviation_type": s.deviation_type,
            "record_id": str(s.id),
        }
        stage_facts.append(fact)
        grounding_ids.append(str(s.id))
        if s.start_event_occurrence_id:
            grounding_ids.append(str(s.start_event_occurrence_id))
        if s.end_event_occurrence_id:
            grounding_ids.append(str(s.end_event_occurrence_id))

    return {
        "vcn": vc.vcn,
        "vessel_name": vc.vessel_name,
        "status": instance.status,
        "coverage_summary": instance.coverage_summary,
        "time_decomposition": instance.time_decomposition,
        "deviations": instance.deviation_report or [],
        "stages": stage_facts,
        "grounding_record_ids": sorted(set(grounding_ids)),
    }


def _deterministic_narrative(facts: Dict[str, Any]) -> str:
    sentences = [
        f"Vessel call {facts['vcn']} ({facts['vessel_name']}) reconstructed with status {facts['status']}."
    ]

    for stage in facts["stages"]:
        label = stage["stage"]
        if stage["shift_occurrence_index"]:
            label = f"{label} #{stage['shift_occurrence_index']}"

        if stage["availability"] != "AVAILABLE":
            sentences.append(f"{label} is UNAVAILABLE: no canonical observation was recorded for it.")
            continue

        duration = stage["duration_hours"]
        if stage["deviation_type"] == "SEQUENCE_VIOLATION":
            sentences.append(
                f"{label} recorded a sequence violation with duration {duration}h (end preceded start; preserved, not corrected)."
            )
        else:
            sentences.append(f"{label} took {duration}h.")

    decomposition = facts.get("time_decomposition") or {}
    if decomposition.get("status") == "AVAILABLE":
        sentences.append(
            "Time decomposition: "
            + ", ".join(
                f"{cat}={decomposition.get(cat)}h"
                for cat in ["ACTIVE_SERVICE", "PASSIVE_WAIT", "HOLD", "DELAY", "UNCLASSIFIED"]
            )
            + f" (total {decomposition.get('total_hours')}h)."
        )

    if facts["deviations"]:
        sentences.append(f"{len(facts['deviations'])} operational deviation(s) were identified.")

    return " ".join(sentences)


def _try_gemini_narrative(facts: Dict[str, Any]) -> str | None:
    if not getattr(settings, "gemini_api_key", ""):
        return None
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(getattr(settings, "gemini_model", "gemini-2.0-flash"))
        prompt = (
            "You are a factual port-operations narrator. You may state ONLY facts present in the "
            "JSON fact sheet below. Never infer, estimate, or add any event, duration or cause not "
            "explicitly present. If a stage's availability is not 'AVAILABLE', say it is unavailable "
            "and do not guess a duration or timing for it.\n\nFact sheet:\n" + str(facts)
        )
        response = model.generate_content(prompt)
        text = getattr(response, "text", None)
        return text.strip() if text else None
    except Exception:
        return None


class JourneyNarrativeService:
    @staticmethod
    def generate(db: Session, vessel_call_id: str) -> JourneyNarrative:
        vc = db.execute(select(VesselCall).where(VesselCall.id == vessel_call_id)).scalar_one_or_none()
        if not vc:
            raise ValueError(f"VesselCall {vessel_call_id} not found")

        instance = db.execute(
            select(JourneyInstance).where(JourneyInstance.vessel_call_id == vc.id)
        ).scalar_one_or_none()
        if not instance:
            raise ValueError(f"No reconstructed journey for vessel call {vessel_call_id}")

        facts = build_fact_sheet(db, instance, vc)

        model_name = "template:deterministic:v1"
        text = _try_gemini_narrative(facts)
        if text:
            model_name = getattr(settings, "gemini_model", "gemini-2.0-flash")
        else:
            text = _deterministic_narrative(facts)

        narrative = JourneyNarrative(
            vessel_call_id=vc.id,
            journey_instance_id=instance.id,
            narrative_text=text,
            grounding_record_ids=facts["grounding_record_ids"],
            model_name=model_name,
            is_ai_generated=True,
            inference_status="AI_GENERATED",
            generated_at=datetime.now(timezone.utc),
        )
        db.add(narrative)
        db.commit()
        db.refresh(narrative)
        return narrative
