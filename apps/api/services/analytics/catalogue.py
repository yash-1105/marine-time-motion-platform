"""Governed Lead-Time Catalogue (spec §10.2).

Seeds and maintains the catalogue of standard lead-time and duration definitions.
Definitions with source data in the fixture are COMPUTABLE.
Definitions requiring yard, crane-level, gate, or unmooring events that the fixture
lacks are explicitly registered with status NO_SOURCE_DATA and their required event list,
per AGENTS.md §6 and spec §10.2.
"""

from typing import Any, Dict, List
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.analytics import LeadTimeDefinition

# 8 reconciliation targets + additional computable + NO_SOURCE_DATA definitions
CATALOGUE_SEEDS: List[Dict[str, Any]] = [
    # --- 8 Reconciliation Targets (COMPUTABLE) ---
    {
        "name": "Turnaround",
        "start_event": "ATA",
        "end_event": "ATD",
        "description": "Total port stay from Actual Time of Arrival (ATA) to Actual Time of Departure (ATD).",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["ATA", "ATD"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Anchorage Wait",
        "start_event": "ANCHORAGE_ARRIVAL",
        "end_event": "PILOT_ON_BOARD_ARRIVAL",
        "description": "Waiting time at anchorage awaiting pilot boarding for arrival movement.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["ANCHORAGE_ARRIVAL", "PILOT_ON_BOARD_ARRIVAL"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Inward Movement",
        "start_event": "PILOT_ON_BOARD_ARRIVAL",
        "end_event": "ALL_FAST_ARRIVAL",
        "description": "Inward transit from pilot boarding at anchorage to all fast at designated berth.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["PILOT_ON_BOARD_ARRIVAL", "ALL_FAST_ARRIVAL"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Berth Stay",
        "start_event": "ALL_FAST_ARRIVAL",
        "end_event": "LAST_LINE_UNTIED_SAILING",
        "description": "Total duration alongside berth from all lines secured to last line cast off for departure.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["ALL_FAST_ARRIVAL", "LAST_LINE_UNTIED_SAILING"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Cargo Working",
        "start_event": "CARGO_START",
        "end_event": "CARGO_END",
        "description": "Net cargo working duration between cargo operations commencement and completion.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["CARGO_START", "CARGO_END"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Outward Movement",
        "start_event": "PILOT_ON_BOARD_SAILING",
        "end_event": "BREAKWATER_OUT",
        "description": "Outward transit from departure pilot boarding to clearing breakwater outward.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["PILOT_ON_BOARD_SAILING", "BREAKWATER_OUT"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Arrival Execution Delay",
        "start_event": "SCHEDULED_TIME",
        "end_event": "SERVED_TIME",
        "description": "Execution delay for Arrival Pilotage Service: Served_Time − Scheduled_Time. Negative values represent early service.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["PILOT_SCHEDULED_ARRIVAL", "PILOT_ON_BOARD_ARRIVAL"],
        "is_execution_delay": True,
        "execution_delay_movement": "Arrival",
    },
    {
        "name": "Sailing Execution Delay",
        "start_event": "SCHEDULED_TIME",
        "end_event": "SERVED_TIME",
        "description": "Execution delay for Sailing Pilotage Service: Served_Time − Scheduled_Time. Negative values represent early service.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["PILOT_SCHEDULED_SAILING", "PILOT_ON_BOARD_SAILING"],
        "is_execution_delay": True,
        "execution_delay_movement": "Sailing",
    },

    # --- Additional Standard Calculations (COMPUTABLE) ---
    {
        "name": "Pre-Arrival",
        "start_event": "NOMINATION_SUBMITTED",
        "end_event": "ATA",
        "description": "Planning duration from vessel nomination submission to actual arrival.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["NOMINATION_SUBMITTED", "ATA"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Pilot Response Arrival",
        "start_event": "PILOT_REQUEST_ARRIVAL",
        "end_event": "PILOT_ON_BOARD_ARRIVAL",
        "description": "Arrival pilot response duration from request time to pilot boarding.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["PILOT_REQUEST_ARRIVAL", "PILOT_ON_BOARD_ARRIVAL"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Breakwater In to All Fast",
        "start_event": "BREAKWATER_IN",
        "end_event": "ALL_FAST_ARRIVAL",
        "description": "Harbour basin transit duration from breakwater entry to all fast.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["BREAKWATER_IN", "ALL_FAST_ARRIVAL"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "First Line to All Fast",
        "start_event": "FIRST_LINE_TIED_ARRIVAL",
        "end_event": "ALL_FAST_ARRIVAL",
        "description": "Mooring duration from first mooring line secured to all lines fast.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["FIRST_LINE_TIED_ARRIVAL", "ALL_FAST_ARRIVAL"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Unberthing Duration",
        "start_event": "FIRST_LINE_UNTIED_SAILING",
        "end_event": "LAST_LINE_UNTIED_SAILING",
        "description": "Mooring team unberthing duration from first line untied to last line untied.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["FIRST_LINE_UNTIED_SAILING", "LAST_LINE_UNTIED_SAILING"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Breakwater Out to ATD",
        "start_event": "BREAKWATER_OUT",
        "end_event": "ATD",
        "description": "Duration from clearing breakwater to recorded Actual Time of Departure.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "COMPUTABLE",
        "required_events": ["BREAKWATER_OUT", "ATD"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },

    # --- NO_SOURCE_DATA Definitions (governed registration per spec §10.2) ---
    {
        "name": "Crane Start to Last Move",
        "start_event": "FIRST_CRANE_MOVEMENT",
        "end_event": "LAST_CRANE_MOVEMENT",
        "description": "Crane operating duration between first and last container crane movement.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "NO_SOURCE_DATA",
        "required_events": ["FIRST_CRANE_MOVEMENT", "LAST_CRANE_MOVEMENT"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "First Container to ATD",
        "start_event": "FIRST_CONTAINER_MOVEMENT",
        "end_event": "ATD",
        "description": "Elapsed duration from first container lifted to vessel departure.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "NO_SOURCE_DATA",
        "required_events": ["FIRST_CONTAINER_MOVEMENT", "ATD"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Berthing End to Unmooring Start",
        "start_event": "BERTHING_END",
        "end_event": "UNMOORING_START",
        "description": "Waiting time at berth between commercial completion and unmooring commencement.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "NO_SOURCE_DATA",
        "required_events": ["BERTHING_END", "UNMOORING_START"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Lashing End to ATD",
        "start_event": "LASHING_END",
        "end_event": "ATD",
        "description": "Departure clearance and unberthing buffer after container lashing completion.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "NO_SOURCE_DATA",
        "required_events": ["LASHING_END", "ATD"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Anchor Drop to Aweigh",
        "start_event": "ANCHOR_DROP",
        "end_event": "ANCHOR_AWEIGH",
        "description": "Net anchor physical deployment time from anchor drop to anchor aweigh.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "NO_SOURCE_DATA",
        "required_events": ["ANCHOR_DROP", "ANCHOR_AWEIGH"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
    {
        "name": "Truck Gate Turnaround",
        "start_event": "GATE_IN",
        "end_event": "GATE_OUT",
        "description": "Landside terminal truck turnaround duration from gate-in to gate-out.",
        "formula_version": "1.0",
        "unit": "hours",
        "null_handling": "UNAVAILABLE",
        "occurrence_selection": "first",
        "availability_status": "NO_SOURCE_DATA",
        "required_events": ["GATE_IN", "GATE_OUT"],
        "is_execution_delay": False,
        "execution_delay_movement": None,
    },
]


def ensure_catalogue(db: Session) -> Dict[str, LeadTimeDefinition]:
    """Upserts the governed catalogue of lead-time definitions into analytics.lead_time_definition.

    Returns a mapping of definition_name -> LeadTimeDefinition model instance.
    """
    existing = {
        d.name: d
        for d in db.execute(select(LeadTimeDefinition)).scalars().all()
    }

    result = {}
    for item in CATALOGUE_SEEDS:
        name = item["name"]
        row = existing.get(name)
        if not row:
            row = LeadTimeDefinition(
                name=name,
                start_event=item["start_event"],
                end_event=item["end_event"],
                description=item.get("description"),
                formula_version=item.get("formula_version", "1.0"),
                unit=item.get("unit", "hours"),
                null_handling=item.get("null_handling", "UNAVAILABLE"),
                occurrence_selection=item.get("occurrence_selection", "first"),
                availability_status=item.get("availability_status", "COMPUTABLE"),
                required_events=item.get("required_events", []),
                custom_builder=False,
                is_execution_delay=item.get("is_execution_delay", False),
                execution_delay_movement=item.get("execution_delay_movement"),
            )
            db.add(row)
            db.flush()
        else:
            # Update columns
            row.start_event = item["start_event"]
            row.end_event = item["end_event"]
            row.description = item.get("description")
            row.formula_version = item.get("formula_version", "1.0")
            row.unit = item.get("unit", "hours")
            row.null_handling = item.get("null_handling", "UNAVAILABLE")
            row.occurrence_selection = item.get("occurrence_selection", "first")
            row.availability_status = item.get("availability_status", "COMPUTABLE")
            row.required_events = item.get("required_events", [])
            row.is_execution_delay = item.get("is_execution_delay", False)
            row.execution_delay_movement = item.get("execution_delay_movement")
            db.flush()

        result[name] = row

    db.commit()
    return result
