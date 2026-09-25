"""Deterministic FRD v2 source-field and marine-event standardisation.

No inference is performed here. Ambiguous aliases require an explicit movement
scope; otherwise the original value is retained for steward review and lineage.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _token(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


@lru_cache(maxsize=1)
def load_v2_dictionary() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[4] / "config" / "frd_v2_data_dictionary.yaml"
    with path.open(encoding="utf-8") as source:
        return yaml.safe_load(source) or {}


@lru_cache(maxsize=1)
def load_aliases() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[4] / "config" / "aliases.yaml"
    with path.open(encoding="utf-8") as source:
        return (yaml.safe_load(source) or {}).get("aliases", [])


class StandardizationRegistry:
    """Maps source labels onto the existing long-form governed source contract."""

    VESSEL_TARGET_COLUMNS = {
        "license_number": "License_Number",
        "imo_number": "IMO_Number",
        "vcn": "VCN",
        "vessel_name": "Vessel_Name",
        "vessel_type": "Vessel_Type",
        "vessel_size_teu": "Vessel_Size_TEU",
        "flag": "Flag",
        "last_port_of_call": "Last_Port_Of_Call",
        "next_port_of_call": "Next_Port_Of_Call",
        "port_of_lading": "Port_Of_Lading",
        "port_of_discharge": "Port_Of_Discharge",
        "reason_for_visit": "Reason_For_Visit",
        "cargo_type": "Cargo_Type",
        "commodity": "Commodity",
        "quantity_value": "Planned_Quantity",
        "grt": "GRT",
        "loa_value": "LOA_Value",
        "dwt": "DWT",
        "forward_draft_value": "Forward_Draft",
        "aft_draft_value": "Aft_Draft",
        "call_sign": "Call_Sign",
    }

    BERTH_TARGET_COLUMNS = {
        "CARGO_START": "Cargo_Start",
        "CARGO_END": "Cargo_End",
        "resources_deployed": "Resources_Deployed",
    }

    COLUMN_ALIASES = {
        "VesselCalls": {
            "licenseno": "License_Number",
            "imonumber": "IMO_Number",
            "imono": "IMO_Number",
            "vcn": "VCN",
            "vesselname": "Vessel_Name",
            "vesseltype": "Vessel_Type",
            "vesselsizeteus": "Vessel_Size_TEU",
            "flag": "Flag",
            "lastportofcall": "Last_Port_Of_Call",
            "lastport": "Last_Port_Of_Call",
            "nextportofcall": "Next_Port_Of_Call",
            "nextport": "Next_Port_Of_Call",
            "portoflading": "Port_Of_Lading",
            "portofdischarge": "Port_Of_Discharge",
            "reasonforvisit": "Reason_For_Visit",
            "cargotype": "Cargo_Type",
            "commodity": "Commodity",
            "quantity": "Planned_Quantity",
            "grt": "GRT",
            "loa": "LOA_Value",
            "dwt": "DWT",
            "fwddraft": "Forward_Draft",
            "forwarddraft": "Forward_Draft",
            "aftdraft": "Aft_Draft",
            "callsign": "Call_Sign",
        },
        "Events": {
            "vcn": "VCN",
            "eventname": "Event_Name",
            "eventtimestamp": "Event_Timestamp",
            "movementtype": "Movement_Type",
            "operationtype": "Operation_Type",
            "timezone": "Timezone",
            "sourcesystem": "Source_System",
            "eventid": "Event_ID",
            "verificationstatus": "Verification_Status",
            "confidencescore": "Confidence_Score",
        },
        "Services": {
            "vcn": "VCN",
            "servicetype": "Service_Type",
            "movementtype": "Movement_Type",
            "servicerequestsubmissiontime": "Submission_Time",
            "submissiontime": "Submission_Time",
            "servicerequestedtime": "Requested_Time",
            "requestedtime": "Requested_Time",
            "pilotrequesttime": "Requested_Time",
            "scheduledservicetime": "Scheduled_Time",
            "scheduledtime": "Scheduled_Time",
            "pilotassignedtime": "Scheduled_Time",
            "actualscheduleddatetime": "Scheduled_Time",
            "actualservicetime": "Served_Time",
            "servedtime": "Served_Time",
            "serveddatetime": "Served_Time",
            "pilotagestart": "Served_Time",
            "resourceassigned": "Resource_Assigned",
            "datastatus": "Data_Status",
        },
        "CargoOps": {
            "vcn": "VCN",
            "cargooperationid": "Cargo_Operation_ID",
            "cargotype": "Cargo_Type",
            "operationtype": "Operation_Type",
            "plannedquantity": "Planned_Quantity",
            "unit": "Unit",
            "startofcargooperations": "Cargo_Start",
            "cargostart": "Cargo_Start",
            "endofcargooperations": "Cargo_End",
            "cargoend": "Cargo_End",
            "workinghours": "Working_Hours",
            "numberofcranesdeployedforavessel": "Resources_Deployed",
            "resourcesdeployed": "Resources_Deployed",
            "downtimehours": "Downtime_Hours",
            "actualquantity": "Actual_Quantity",
            "datastatus": "Data_Status",
        },
        "Delays": {
            "vcn": "VCN",
            "delayid": "Delay_ID",
            "movementtype": "Movement_Type",
            "scheduledtime": "Scheduled_Time",
            "servedtime": "Served_Time",
            "actualservicetime": "Served_Time",
            "delayhours": "Delay_Hours",
            "durationhours": "Duration_Hours",
            "delayreason": "Delay_Reason",
            "delaycategory": "Delay_Category",
        },
    }

    def __init__(self) -> None:
        dictionary = load_v2_dictionary()
        self.column_aliases = {worksheet: dict(aliases) for worksheet, aliases in self.COLUMN_ALIASES.items()}
        for source_name, canonical, _datatype in dictionary.get("vessel_cargo_attributes", []):
            self.column_aliases["VesselCalls"][_token(source_name)] = self.VESSEL_TARGET_COLUMNS[canonical]
        for source_name, canonical, _datatype in dictionary.get("berth_attributes", []):
            self.column_aliases["CargoOps"][_token(source_name)] = self.BERTH_TARGET_COLUMNS.get(canonical, canonical)
        self.event_names = {
            _token(source_name): canonical
            for source_name, canonical in dictionary.get("marine_event_datetime_attributes", [])
        }
        self.berth_datetime_fields = {
            canonical
            for _source_name, canonical, datatype in dictionary.get("berth_attributes", [])
            if datatype == "DATETIME"
        }
        self.event_names.update(
            {
                _token(source_name): canonical
                for source_name, canonical, datatype in dictionary.get("berth_attributes", [])
                if datatype == "DATETIME"
            }
        )
        self.aliases = load_aliases()

    def canonical_column(self, worksheet: str, source_column: str) -> str:
        return self.column_aliases.get(worksheet, {}).get(_token(source_column), source_column)

    def normalize_row(self, worksheet: str, values: dict[str, Any]) -> dict[str, Any]:
        normalized = {self.canonical_column(worksheet, str(column)): value for column, value in values.items()}
        if worksheet == "Events" and normalized.get("Event_Name"):
            normalized["Event_Name"] = self.canonical_event_name(
                str(normalized["Event_Name"]), normalized.get("Movement_Type")
            )
        return normalized

    def canonical_event_name(self, source_name: str, movement: str | None = None) -> str:
        value = source_name.strip()
        # Existing canonical keys are authoritative and must never be remapped to
        # an older human-readable alias target.
        if value and value == value.upper() and " " not in value:
            return value
        direct = self.event_names.get(_token(value))
        if direct:
            return direct
        movement_key = (movement or "").strip().upper()
        movement_key = {"INWARD": "ARRIVAL", "OUTWARD": "SAILING", "DEPARTURE": "SAILING"}.get(
            movement_key, movement_key
        )
        for alias in self.aliases:
            if _token(str(alias.get("alias", ""))) != _token(value):
                continue
            required_scope = str(alias.get("movement_scope") or "").upper()
            if required_scope and required_scope != movement_key:
                continue
            target = str(alias.get("event_name") or value)
            if "{MOVEMENT}" in target:
                if movement_key not in {"ARRIVAL", "SHIFTING", "SAILING"}:
                    return value
                target = target.replace("{MOVEMENT}", movement_key)
            if alias.get("match_type") != "FIELD_ALIAS":
                return target
        return value
