"""Focused contract tests for authoritative FRD v2 sections 4.2.1, 4.4.3 and 4.4.6."""

from apps.api.services.delays.service import DelayService
from apps.api.services.ingestion.standardization import StandardizationRegistry, load_v2_dictionary
from apps.api.services.outliers.engine import OutlierEngine, linear_percentile, load_outlier_rule_registry


def test_v2_data_dictionary_is_complete_and_mappable():
    dictionary = load_v2_dictionary()
    assert len(dictionary["vessel_cargo_attributes"]) == 21
    assert len(dictionary["berth_attributes"]) == 31
    assert len(dictionary["marine_event_datetime_attributes"]) + len(dictionary["marine_event_text_attributes"]) == 135

    registry = StandardizationRegistry()
    row = registry.normalize_row(
        "VesselCalls",
        {
            "License No.": "LIC-1",
            "IMO No.": "1234567",
            "Vessel Size (TEUs)": "8000",
            "Port of Lading": "Durban",
            "Fwd Draft": "10.5",
            "Call sign": "CALL-1",
        },
    )
    assert row == {
        "License_Number": "LIC-1",
        "IMO_Number": "1234567",
        "Vessel_Size_TEU": "8000",
        "Port_Of_Lading": "Durban",
        "Forward_Draft": "10.5",
        "Call_Sign": "CALL-1",
    }
    berth = registry.normalize_row(
        "CargoOps",
        {
            "Vessel Inspection by Customs Start Time": "2026-01-01 10:00",
            "Total Container moves per vessel": "1200",
            "TEUs transhipped": "45",
            "Berthing End Time": "2026-01-02 11:00",
        },
    )
    assert berth == {
        "CUSTOMS_INSPECTION_START": "2026-01-01 10:00",
        "total_container_moves": "1200",
        "teus_transhipped": "45",
        "BERTHING_END": "2026-01-02 11:00",
    }
    assert registry.canonical_event_name("Pilot On-Board 2", "Shifting") == "PILOT_ON_BOARD_SHIFTING"
    assert registry.canonical_event_name("Served Date and Time", "Sailing") == "PILOTAGE_START_SAILING"
    assert registry.canonical_event_name("Served Date and Time", None) == "Served Date and Time"


def test_v2_delay_frequency_boundaries_and_leg_populations():
    assert DelayService.classify_delay_frequency(39.999) == ("ACCEPTABLE", "GREEN")
    assert DelayService.classify_delay_frequency(40.0) == ("WATCH", "ORANGE")
    assert DelayService.classify_delay_frequency(60.0) == ("WATCH", "ORANGE")
    assert DelayService.classify_delay_frequency(60.001) == ("CRITICAL", "RED")

    rows = [
        {"leg": "ARRIVAL_INWARD", "execution_delay_hours": 1.0},
        {"leg": "ARRIVAL_INWARD", "execution_delay_hours": -0.25},
        {"leg": "SAILING_OUTWARD", "execution_delay_hours": 0.0},
        {"leg": "SHIFTING", "execution_delay_hours": None},
    ]
    result = {item["leg"]: item for item in DelayService._delay_frequency_by_leg(rows)}
    assert result["ARRIVAL_INWARD"]["delay_frequency_percent"] == 50.0
    assert result["ARRIVAL_INWARD"]["classification"] == "WATCH"
    assert result["SAILING_OUTWARD"]["delay_frequency_percent"] == 0.0
    assert result["SHIFTING"]["status"] == "UNAVAILABLE"


def test_v2_outlier_registry_and_threshold_methods():
    registry = load_outlier_rule_registry()
    rules = registry["rules"]
    assert len(rules) == 43
    assert {rule["id"] for rule in rules} == {f"OUT-V2-{number:03d}" for number in range(1, 44)}
    assert set(registry["categories"]) == OutlierEngine.CATEGORIES
    assert all(rule.get("required_inputs") for rule in rules)
    assert all(rule.get("required_inputs") for rule in rules if rule["status"] in {"NO_SOURCE_DATA", "UNAVAILABLE"})
    assert linear_percentile([0, 10], 0.30) == 3
    assert linear_percentile([0, 10], 0.90) == 9
    assert linear_percentile([0, 10], 0.95) == 9.5
