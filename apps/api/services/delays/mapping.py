"""Canonical delay categories and mapping rules (spec §10.4, Phase 09).

Categories:
- Pilot
- Tug
- Berth Non-Availability
- Weather
- Regulatory Clearance
- Terminal Readiness
- Cargo Operation
- Equipment Breakdown
- Crane Downtime
- Mooring
- Documentation
- Vessel-Side
- Port-Side
- External/Uncontrollable
- Other
"""
from typing import Optional

CANONICAL_DELAY_CATEGORIES = [
    "Pilot",
    "Tug",
    "Berth Non-Availability",
    "Weather",
    "Regulatory Clearance",
    "Terminal Readiness",
    "Cargo Operation",
    "Equipment Breakdown",
    "Crane Downtime",
    "Mooring",
    "Documentation",
    "Vessel-Side",
    "Port-Side",
    "External/Uncontrollable",
    "Other",
]


def map_to_canonical_category(source_category: Optional[str], reason: Optional[str]) -> str:
    """
    Map source delay categories and reason descriptions onto the canonical 15 categories.
    Preserves visibility of source values while providing governed grouping.
    """
    if not source_category and not reason:
        return "Other"

    src = (source_category or "").strip().lower()
    rsn = (reason or "").strip().lower()

    # 1. Weather
    if "weather" in src or "weather" in rsn or "swells" in rsn or "wind" in rsn or "fog" in rsn or "storm" in rsn:
        return "Weather"

    # 2. Tug
    if "tug" in rsn:
        return "Tug"

    # 3. Pilot
    if "pilot" in rsn:
        return "Pilot"

    # 4. Berth Non-Availability
    if "berth" in rsn or "berth unavailable" in rsn or "berth congestion" in rsn:
        return "Berth Non-Availability"

    # 5. Terminal Readiness
    if "cargo" in rsn or "awaiting cargo" in rsn or "terminal awaiting" in rsn:
        return "Terminal Readiness"

    # 6. Crane Downtime
    if "crane" in rsn:
        return "Crane Downtime"

    # 7. Equipment Breakdown
    if "equipment" in rsn or "breakdown" in rsn:
        return "Equipment Breakdown"

    # 8. Mooring
    if "mooring" in rsn or "lines" in rsn:
        return "Mooring"

    # 9. Documentation
    if "documentation" in rsn or "customs" in rsn or "paperwork" in rsn:
        return "Documentation"

    # 10. Vessel-Side
    if "ship not ready" in rsn or "vessel" in src:
        return "Vessel-Side"

    # 11. Regulatory Clearance
    if "clearance" in rsn or "regulatory" in rsn or "quarantine" in rsn or "immigration" in rsn:
        return "Regulatory Clearance"

    # 12. Port-Side / Marine Service
    if "shift" in rsn or "marine service" in src:
        return "Port-Side"

    # 13. Exact match against canonical
    for cat in CANONICAL_DELAY_CATEGORIES:
        if cat.lower() == src:
            return cat

    return "Other"
