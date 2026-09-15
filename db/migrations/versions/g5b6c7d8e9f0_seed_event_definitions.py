"""seed_event_definitions

Seeds all EventDefinition names required by the analytics catalogue, journey template,
and fixture workbook into config.event_definition.

Without these records, the ingestion pipeline silently drops event occurrences because
`event_def_map.get(event_name)` returns None for names like ANCHORAGE_ARRIVAL, etc.

Revision ID: g5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-09-15

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = 'g5b6c7d8e9f0'
down_revision: Union[str, Sequence[str], None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Complete set of event names: from the fixture workbook, the analytics catalogue,
# and the journey template. These are the exact names the ingestion pipeline resolves.
EVENT_DEFINITIONS = [
    # ── From events.yaml (human-readable) ─────────────────────────────────────
    ("Nomination Details Submission", "Pre-arrival and clearance"),
    ("ISPS Submission", "Pre-arrival and clearance"),
    ("ISPS Clearance", "Pre-arrival and clearance"),
    ("PHO Submission", "Pre-arrival and clearance"),
    ("PHO Issuance", "Pre-arrival and clearance"),
    ("IMDG Submission", "Pre-arrival and clearance"),
    ("IMDG Issuance", "Pre-arrival and clearance"),
    ("ETA", "Pre-arrival and clearance"),
    ("ATA", "Pre-arrival and clearance"),
    ("Anchorage Arrival", "Pre-arrival and clearance"),
    ("Anchor Drop", "Pre-arrival and clearance"),
    ("Anchor Aweigh", "Pre-arrival and clearance"),
    ("Port Limit In", "Pre-arrival and clearance"),
    ("Port Limit Out", "Pre-arrival and clearance"),
    ("Pilot Request", "Pilotage"),
    ("Pilot Assigned", "Pilotage"),
    ("Pilot On Board", "Pilotage"),
    ("Pilotage Start", "Pilotage"),
    ("Pilotage End", "Pilotage"),
    ("Pilot Disembark", "Pilotage"),
    ("Tug Request", "Towage"),
    ("Tug Assigned", "Towage"),
    ("Tug Arrival", "Towage"),
    ("Tug Service Start", "Towage"),
    ("Tug Line-Up", "Towage"),
    ("Tug Line-Down", "Towage"),
    ("Tug Service End", "Towage"),
    ("Planned Berthing Time", "Berthing"),
    ("First Line Tied", "Berthing"),
    ("Stern Line Tied", "Berthing"),
    ("Last Line Tied", "Berthing"),
    ("All Fast", "Berthing"),
    ("First Line Untied", "Berthing"),
    ("Last Line Untied", "Berthing"),
    ("Departure from Berth", "Berthing"),
    ("ETD", "Sailing"),
    ("ATD", "Sailing"),
    ("Breakwater In", "Movement"),
    ("Breakwater Out", "Movement"),
    ("Cargo Operations Start", "Cargo"),
    ("Cargo Operations End", "Cargo"),

    # ── Uppercase canonical names used in the fixture workbook Events sheet ───
    # These are the exact Event_Name values in the fixture; without them, the
    # pipeline drops every event occurrence silently.
    ("ANCHORAGE_ARRIVAL", "Anchorage"),
    ("PILOT_REQUEST_ARRIVAL", "Pilotage"),
    ("PILOT_ASSIGNED_ARRIVAL", "Pilotage"),
    ("PILOT_ON_BOARD_ARRIVAL", "Pilotage"),
    ("PILOT_DISEMBARK_ARRIVAL", "Pilotage"),
    ("PILOT_SCHEDULED_ARRIVAL", "Pilotage"),
    ("PILOT_REQUEST_SAILING", "Pilotage"),
    ("PILOT_ASSIGNED_SAILING", "Pilotage"),
    ("PILOT_ON_BOARD_SAILING", "Pilotage"),
    ("PILOT_DISEMBARK_SAILING", "Pilotage"),
    ("PILOT_SCHEDULED_SAILING", "Pilotage"),
    ("TUG_REQUEST_ARRIVAL", "Towage"),
    ("TUG_ASSIGNED_ARRIVAL", "Towage"),
    ("TUG_SERVICE_START_ARRIVAL", "Towage"),
    ("TUG_SERVICE_END_ARRIVAL", "Towage"),
    ("TUG_REQUEST_SAILING", "Towage"),
    ("TUG_ASSIGNED_SAILING", "Towage"),
    ("TUG_SERVICE_START_SAILING", "Towage"),
    ("TUG_SERVICE_END_SAILING", "Towage"),
    ("BREAKWATER_IN", "Movement"),
    ("BREAKWATER_OUT", "Movement"),
    ("FIRST_LINE_TIED_ARRIVAL", "Berthing"),
    ("LAST_LINE_TIED_ARRIVAL", "Berthing"),
    ("ALL_FAST_ARRIVAL", "Berthing"),
    ("FIRST_LINE_UNTIED_SAILING", "Sailing"),
    ("LAST_LINE_UNTIED_SAILING", "Sailing"),
    ("CARGO_START", "Cargo"),
    ("CARGO_END", "Cargo"),
    ("SHIFT_PILOT_ON_BOARD", "Shifting"),
    ("SHIFT_ALL_FAST", "Shifting"),
    ("NOMINATION_SUBMITTED", "Pre-arrival and clearance"),
    ("ISPS_CLEARANCE", "Pre-arrival and clearance"),
    ("PHO_CLEARANCE", "Pre-arrival and clearance"),
    ("IMDG_CLEARANCE", "Pre-arrival and clearance"),
    ("PORT_LIMIT_IN", "Movement"),
    ("PORT_LIMIT_OUT", "Movement"),
    ("ANCHOR_DROP", "Anchorage"),
    ("ANCHOR_AWEIGH", "Anchorage"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Fetch existing names to avoid unique constraint violations
    existing = {row[0] for row in conn.execute(sa.text("SELECT name FROM config.event_definition"))}

    rows_to_insert = []
    for name, category in EVENT_DEFINITIONS:
        if name not in existing:
            rows_to_insert.append({
                "id": str(uuid.uuid4()),
                "name": name,
                "category": category,
                "description": f"Seeded event definition: {name}",
                "version": 1,
            })

    if rows_to_insert:
        conn.execute(
            sa.text(
                "INSERT INTO config.event_definition (id, name, category, description, version) "
                "VALUES (:id, :name, :category, :description, :version) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            rows_to_insert,
        )


def downgrade() -> None:
    # Remove only the seeded definitions that have no event occurrences linked
    # (safe to skip if occurrences reference them)
    conn = op.get_bind()
    names = [name for name, _ in EVENT_DEFINITIONS]
    if names:
        conn.execute(
            sa.text(
                "DELETE FROM config.event_definition WHERE name = ANY(:names) "
                "AND id NOT IN (SELECT DISTINCT event_definition_id FROM canonical.event_occurrence "
                "WHERE event_definition_id IS NOT NULL)"
            ),
            {"names": names},
        )
