"""Loads config/journey_templates.yaml, and keeps journey.journey_template /
journey.journey_stage in sync so the DB carries a referenceable, versioned catalogue
(spec §9: "configurable templates, not universal hard-coded rules")."""

from typing import Any, Dict, List, Tuple

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.journey import JourneyStage, JourneyTemplate

TEMPLATE_PATH = "config/journey_templates.yaml"

# Events which legitimately repeat (shifting may occur zero, one or many times).
REPEATABLE_EVENTS = {"SHIFT_PILOT_ON_BOARD", "SHIFT_ALL_FAST"}


def load_raw_template(path: str = TEMPLATE_PATH) -> Dict[str, Any]:
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    templates = data.get("templates", [])
    if not templates:
        raise ValueError(f"No journey templates defined in {path}")
    return templates[0]


def ensure_template(db: Session, path: str = TEMPLATE_PATH) -> Tuple[JourneyTemplate, List[Dict[str, Any]]]:
    """Upserts the template + its stage catalogue into the DB, returns (template row, stage dicts)."""
    raw = load_raw_template(path)
    name = raw["name"]
    rule_version = raw.get("rule_version", "1.0")
    stage_defs = raw.get("stages", [])

    template = db.execute(select(JourneyTemplate).where(JourneyTemplate.name == name)).scalar_one_or_none()
    if not template:
        template = JourneyTemplate(name=name, rule_version=rule_version, dag_definition=raw.get("dag", {}))
        db.add(template)
        db.flush()
    else:
        template.rule_version = rule_version
        template.dag_definition = raw.get("dag", {})

    existing_stages = {
        s.stage_name: s
        for s in db.execute(select(JourneyStage).where(JourneyStage.template_id == template.id)).scalars().all()
    }

    stages: List[Dict[str, Any]] = []
    for sdef in stage_defs:
        stage_name = sdef["name"]
        row = existing_stages.get(stage_name)
        if not row:
            row = JourneyStage(template_id=template.id, stage_name=stage_name)
            db.add(row)

        row.sequence_index = sdef.get("sequence_index", 0)
        row.start_event_name = sdef.get("start_event")
        row.end_event_name = sdef.get("end_event")
        row.time_category = sdef.get("time_category", "UNCLASSIFIED")
        row.actor_from = sdef.get("actor_from")
        row.actor_to = sdef.get("actor_to")
        row.is_optional = bool(sdef.get("is_optional", False))
        row.is_repeatable = bool(sdef.get("is_repeatable", False))
        db.flush()

        stages.append(
            {
                "id": row.id,
                "name": stage_name,
                "sequence_index": row.sequence_index,
                "start_event": row.start_event_name,
                "end_event": row.end_event_name,
                "time_category": row.time_category,
                "actor_from": row.actor_from,
                "actor_to": row.actor_to,
                "is_optional": row.is_optional,
                "is_repeatable": row.is_repeatable,
            }
        )

    stages.sort(key=lambda s: s["sequence_index"])
    return template, stages
