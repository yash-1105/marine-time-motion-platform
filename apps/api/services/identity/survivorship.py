from typing import Any, Dict, List, Optional, Tuple
from apps.api.models.canonical import VesselCall
from apps.api.services.identity.normalizer import VesselNameNormalizer


class SurvivorshipEngine:
    """
    Applies governed survivorship rules (source priority, recency, completeness)
    to generate consolidated previews and resolve field conflicts between two candidate records.
    """

    COMPARABLE_FIELDS = [
        ("vessel_name", "Vessel Name", "text_clean"),
        ("imo_number", "IMO Number", "first_non_null"),
        ("vcn", "VCN", "first_non_null"),
        ("vessel_type", "Vessel Type", "first_non_null"),
        ("vessel_size_teu", "TEU Capacity", "max_numeric"),
        ("flag", "Flag State", "first_non_null"),
        ("last_port_of_call", "Last Port of Call", "first_non_null"),
        ("next_port_of_call", "Next Port of Call", "first_non_null"),
        ("port_of_lading", "Port of Lading", "first_non_null"),
        ("port_of_discharge", "Port of Discharge", "first_non_null"),
        ("reason_for_visit", "Reason for Visit", "first_non_null"),
        ("cargo_type", "Cargo Type", "first_non_null"),
        ("commodity", "Commodity", "first_non_null"),
        ("quantity_value", "Cargo Quantity", "max_numeric"),
        ("quantity_unit", "Quantity Unit", "first_non_null"),
        ("grt", "GRT", "max_numeric"),
        ("loa_value", "LOA (m)", "max_numeric"),
        ("dwt", "DWT", "max_numeric"),
        ("forward_draft_value", "Forward Draft", "max_numeric"),
        ("aft_draft_value", "Aft Draft", "max_numeric"),
        ("call_sign", "Call Sign", "first_non_null"),
    ]

    @classmethod
    def determine_survivor_record(cls, v1: VesselCall, v2: VesselCall) -> Tuple[VesselCall, VesselCall]:
        """
        Determines which record serves as the master survivor and which is merged into it.
        Prefers:
        1. Cleanest vessel name (no trailing punctuation / hyphens).
        2. Record with higher field completeness.
        3. Earlier created_at.
        """
        score1 = 0
        score2 = 0

        # Completeness check
        for attr, _, _ in cls.COMPARABLE_FIELDS:
            val1 = getattr(v1, attr, None)
            val2 = getattr(v2, attr, None)
            if val1 is not None and val1 != "":
                score1 += 1
            if val2 is not None and val2 != "":
                score2 += 1

        # Normalized name clean check: prefer the standard normalized display
        name1 = v1.vessel_name or ""
        name2 = v2.vessel_name or ""
        norm1 = VesselNameNormalizer.normalize(name1)
        norm2 = VesselNameNormalizer.normalize(name2)

        # If name1 has hyphens or odd punctuation, penalise slightly
        if "-" in name1 or "." in name1:
            score1 -= 2
        if "-" in name2 or "." in name2:
            score2 -= 2

        if score1 >= score2:
            return v1, v2
        return v2, v1

    @classmethod
    def resolve_field(cls, field_name: str, rule_type: str, val1: Any, val2: Any, v1_id: str, v2_id: str) -> Dict[str, Any]:
        """
        Resolves a single field between two values based on survivorship rules.
        """
        if val1 is None and val2 is None:
            return {
                "field": field_name,
                "winner_value": None,
                "winning_record_id": v1_id,
                "rule_applied": "both_null",
                "provenance": "none",
            }
        if val1 is not None and val2 is None:
            return {
                "field": field_name,
                "winner_value": val1,
                "winning_record_id": v1_id,
                "rule_applied": "completeness (val2 is null)",
                "provenance": f"record:{v1_id}",
            }
        if val1 is None and val2 is not None:
            return {
                "field": field_name,
                "winner_value": val2,
                "winning_record_id": v2_id,
                "rule_applied": "completeness (val1 is null)",
                "provenance": f"record:{v2_id}",
            }

        # Both non-null
        if val1 == val2:
            return {
                "field": field_name,
                "winner_value": val1,
                "winning_record_id": v1_id,
                "rule_applied": "unanimous agreement",
                "provenance": "both_records",
            }

        if rule_type == "text_clean":
            # Prefer the cleaner text without hyphens or trailing punctuation
            s1 = str(val1).strip()
            s2 = str(val2).strip()
            if ("-" in s1 or s1.endswith(".")) and not ("-" in s2 or s2.endswith(".")):
                return {
                    "field": field_name,
                    "winner_value": val2,
                    "winning_record_id": v2_id,
                    "rule_applied": "clean_text_normalisation",
                    "provenance": f"record:{v2_id}",
                }
            return {
                "field": field_name,
                "winner_value": val1,
                "winning_record_id": v1_id,
                "rule_applied": "clean_text_normalisation",
                "provenance": f"record:{v1_id}",
            }

        if rule_type == "max_numeric":
            try:
                n1 = float(val1)
                n2 = float(val2)
                if n1 >= n2:
                    return {
                        "field": field_name,
                        "winner_value": val1,
                        "winning_record_id": v1_id,
                        "rule_applied": "max_numeric",
                        "provenance": f"record:{v1_id}",
                    }
                return {
                    "field": field_name,
                    "winner_value": val2,
                    "winning_record_id": v2_id,
                    "rule_applied": "max_numeric",
                    "provenance": f"record:{v2_id}",
                }
            except Exception:
                pass

        # Default: first non-null (record 1 priority)
        return {
            "field": field_name,
            "winner_value": val1,
            "winning_record_id": v1_id,
            "rule_applied": "source_priority_recency",
            "provenance": f"record:{v1_id}",
        }

    @classmethod
    def generate_preview(cls, v1: VesselCall, v2: VesselCall) -> Dict[str, Any]:
        """
        Generates a side-by-side comparison view and consolidated preview for commit.
        """
        survivor, merged = cls.determine_survivor_record(v1, v2)
        v1_id = str(v1.id)
        v2_id = str(v2.id)

        field_comparisons = []
        consolidated_record = {}

        for attr, label, rule in cls.COMPARABLE_FIELDS:
            val1 = getattr(v1, attr, None)
            val2 = getattr(v2, attr, None)
            resolution = cls.resolve_field(attr, rule, val1, val2, v1_id, v2_id)
            consolidated_record[attr] = resolution["winner_value"]

            field_comparisons.append({
                "field": attr,
                "label": label,
                "record_1_value": val1,
                "record_2_value": val2,
                "consolidated_value": resolution["winner_value"],
                "winning_record_id": resolution["winning_record_id"],
                "rule_applied": resolution["rule_applied"],
                "provenance": resolution["provenance"],
            })

        return {
            "survivor_id": str(survivor.id),
            "merged_id": str(merged.id),
            "survivor_vcn": survivor.vcn,
            "merged_vcn": merged.vcn,
            "field_comparisons": field_comparisons,
            "consolidated_preview": consolidated_record,
        }
