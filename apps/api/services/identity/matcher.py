import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from apps.api.models.canonical import VesselCall
from apps.api.services.identity.normalizer import VesselNameNormalizer


@dataclass
class AttributeEvidence:
    attribute: str
    value_1: Optional[str]
    value_2: Optional[str]
    agreement: str  # AGREED | DISAGREED | PARTIAL | MISSING
    weight: float
    contribution: float
    explanation: str


@dataclass
class MatchResult:
    match_score: float
    match_type: str  # DETERMINISTIC | PROBABILISTIC
    status: str  # AUTO_MERGE_CANDIDATE | STEWARD_REVIEW | SEPARATE | BLOCKED_BY_CONFLICT
    conflict_detected: bool
    conflict_reasons: List[str]
    evidence_breakdown: List[AttributeEvidence]
    total_attributes_evaluated: int
    auto_merge_eligible: bool


class IdentityMatcher:
    def __init__(self, thresholds_path: str = "config/thresholds.yaml"):
        self.auto_merge_threshold = 0.98
        self.steward_review_threshold = 0.85
        try:
            with open(thresholds_path, "r") as f:
                cfg = yaml.safe_load(f)
                th = cfg.get("thresholds", {})
                self.auto_merge_threshold = float(th.get("auto_merge", 0.98))
                self.steward_review_threshold = float(th.get("steward_review", 0.85))
        except Exception:
            pass

    def evaluate_pair(self, v1: VesselCall, v2: VesselCall) -> MatchResult:
        evidences: List[AttributeEvidence] = []
        conflicts: List[str] = []
        conflict_detected = False

        # --- Hard Rule Check: Conflicting IMO or VCN ---
        # Any conflicting IMO or VCN must NEVER auto-merge regardless of score.
        v1_imo = (v1.imo_number or "").strip()
        v2_imo = (v2.imo_number or "").strip()
        has_imo_conflict = bool(v1_imo and v2_imo and v1_imo != v2_imo)
        if has_imo_conflict:
            conflicts.append(f"Conflicting IMO numbers: '{v1_imo}' vs '{v2_imo}'")
            conflict_detected = True

        v1_vcn = (v1.vcn or "").strip()
        v2_vcn = (v2.vcn or "").strip()
        has_vcn_conflict = bool(v1_vcn and v2_vcn and v1_vcn != v2_vcn)
        if has_vcn_conflict:
            conflicts.append(f"Conflicting VCNs: '{v1_vcn}' vs '{v2_vcn}'")
            conflict_detected = True

        # --- Stage 1: Deterministic Matching ---
        # Decisive keys: VCN exact match, IMO exact match
        deterministic_match = False
        deterministic_keys: List[str] = []

        if v1_vcn and v2_vcn and v1_vcn == v2_vcn:
            deterministic_keys.append("VCN")
            if not conflict_detected:
                deterministic_match = True

        if v1_imo and v2_imo and v1_imo == v2_imo:
            deterministic_keys.append("IMO")
            # If same IMO and no VCN conflict, could also be deterministic
            if not conflict_detected and not has_vcn_conflict:
                deterministic_match = True

        # --- Stage 2: Attribute-level scoring & Explainable Evidence ---
        # Weights definition (sums to 1.0)
        weights = {
            "vessel_name": 0.40,
            "vcn": 0.25,
            "imo_number": 0.20,
            "vessel_type": 0.05,
            "flag": 0.05,
            "dimensions": 0.05,
        }

        # 1. Vessel Name
        name_sim, name_exp = VesselNameNormalizer.similarity(v1.vessel_name, v2.vessel_name)
        if name_sim >= 0.98:
            status = "AGREED"
        elif name_sim >= 0.70:
            status = "PARTIAL"
        elif name_sim > 0.0:
            status = "DISAGREED"
        else:
            status = "MISSING"
        contrib = round(name_sim * weights["vessel_name"], 4)
        evidences.append(AttributeEvidence(
            attribute="vessel_name",
            value_1=v1.vessel_name,
            value_2=v2.vessel_name,
            agreement=status,
            weight=weights["vessel_name"],
            contribution=contrib,
            explanation=name_exp,
        ))

        # 2. VCN
        if v1_vcn and v2_vcn:
            if v1_vcn == v2_vcn:
                vcn_status = "AGREED"
                vcn_contrib = weights["vcn"]
                vcn_exp = f"Exact VCN match ('{v1_vcn}')"
            else:
                vcn_status = "DISAGREED"
                vcn_contrib = 0.0
                vcn_exp = f"Conflicting VCN ('{v1_vcn}' vs '{v2_vcn}')"
        else:
            vcn_status = "MISSING"
            vcn_contrib = 0.0
            vcn_exp = "VCN missing on one or both records"
        evidences.append(AttributeEvidence(
            attribute="vcn",
            value_1=v1_vcn or None,
            value_2=v2_vcn or None,
            agreement=vcn_status,
            weight=weights["vcn"],
            contribution=vcn_contrib,
            explanation=vcn_exp,
        ))

        # 3. IMO Number
        if v1_imo and v2_imo:
            if v1_imo == v2_imo:
                imo_status = "AGREED"
                imo_contrib = weights["imo_number"]
                imo_exp = f"Exact IMO match ('{v1_imo}')"
            else:
                imo_status = "DISAGREED"
                imo_contrib = 0.0
                imo_exp = f"Conflicting IMO ('{v1_imo}' vs '{v2_imo}')"
        else:
            imo_status = "MISSING"
            imo_contrib = 0.0
            imo_exp = "IMO number missing on one or both records"
        evidences.append(AttributeEvidence(
            attribute="imo_number",
            value_1=v1_imo or None,
            value_2=v2_imo or None,
            agreement=imo_status,
            weight=weights["imo_number"],
            contribution=imo_contrib,
            explanation=imo_exp,
        ))

        # 4. Vessel Type
        vt1 = (v1.vessel_type or "").strip().upper()
        vt2 = (v2.vessel_type or "").strip().upper()
        if vt1 and vt2:
            if vt1 == vt2:
                vt_status = "AGREED"
                vt_contrib = weights["vessel_type"]
                vt_exp = f"Matching vessel type ('{vt1}')"
            else:
                vt_status = "DISAGREED"
                vt_contrib = 0.0
                vt_exp = f"Different vessel types ('{vt1}' vs '{vt2}')"
        else:
            vt_status = "MISSING"
            vt_contrib = 0.0
            vt_exp = "Vessel type absent on one or both records"
        evidences.append(AttributeEvidence(
            attribute="vessel_type",
            value_1=vt1 or None,
            value_2=vt2 or None,
            agreement=vt_status,
            weight=weights["vessel_type"],
            contribution=vt_contrib,
            explanation=vt_exp,
        ))

        # 5. Flag
        f1 = (v1.flag or "").strip().upper()
        f2 = (v2.flag or "").strip().upper()
        if f1 and f2:
            if f1 == f2:
                fl_status = "AGREED"
                fl_contrib = weights["flag"]
                fl_exp = f"Matching flag state ('{f1}')"
            else:
                fl_status = "DISAGREED"
                fl_contrib = 0.0
                fl_exp = f"Different flags ('{f1}' vs '{f2}')"
        else:
            fl_status = "MISSING"
            fl_contrib = 0.0
            fl_exp = "Flag missing on one or both records"
        evidences.append(AttributeEvidence(
            attribute="flag",
            value_1=f1 or None,
            value_2=f2 or None,
            agreement=fl_status,
            weight=weights["flag"],
            contribution=fl_contrib,
            explanation=fl_exp,
        ))

        # 6. Dimensions (LOA / TEU / GRT)
        dim_matches = 0
        dim_compared = 0
        if v1.loa_value and v2.loa_value:
            dim_compared += 1
            if abs(v1.loa_value - v2.loa_value) <= 0.01:
                dim_matches += 1
        if v1.vessel_size_teu and v2.vessel_size_teu:
            dim_compared += 1
            if v1.vessel_size_teu == v2.vessel_size_teu:
                dim_matches += 1
        if v1.grt and v2.grt:
            dim_compared += 1
            if abs(v1.grt - v2.grt) <= 0.01:
                dim_matches += 1

        if dim_compared > 0:
            ratio = dim_matches / dim_compared
            dim_contrib = round(ratio * weights["dimensions"], 4)
            dim_status = "AGREED" if ratio == 1.0 else ("PARTIAL" if ratio > 0 else "DISAGREED")
            dim_exp = f"{dim_matches}/{dim_compared} vessel dimensions matched"
        else:
            dim_status = "MISSING"
            dim_contrib = 0.0
            dim_exp = "Dimensions missing on one or both records"
        evidences.append(AttributeEvidence(
            attribute="dimensions",
            value_1=str(v1.loa_value or v1.vessel_size_teu or None),
            value_2=str(v2.loa_value or v2.vessel_size_teu or None),
            agreement=dim_status,
            weight=weights["dimensions"],
            contribution=dim_contrib,
            explanation=dim_exp,
        ))

        # Calculate total score
        raw_prob_score = sum(e.contribution for e in evidences)
        
        # If deterministic match with exact VCN, IMO and normalized name:
        if deterministic_match and not conflict_detected:
            # Short circuit: Decisive match
            final_score = max(raw_prob_score, 0.99 if name_sim >= 0.98 else 0.98)
            match_type = "DETERMINISTIC"
        else:
            final_score = round(min(1.0, max(0.0, raw_prob_score)), 4)
            match_type = "PROBABILISTIC"

        # Determine disposition & eligibility
        if conflict_detected:
            status = "BLOCKED_BY_CONFLICT"
            auto_merge_eligible = False
        elif final_score >= self.auto_merge_threshold:
            status = "AUTO_MERGE_CANDIDATE"
            auto_merge_eligible = True
        elif final_score >= self.steward_review_threshold:
            status = "STEWARD_REVIEW"
            auto_merge_eligible = False
        else:
            status = "SEPARATE"
            auto_merge_eligible = False

        return MatchResult(
            match_score=final_score,
            match_type=match_type,
            status=status,
            conflict_detected=conflict_detected,
            conflict_reasons=conflicts,
            evidence_breakdown=evidences,
            total_attributes_evaluated=len(evidences),
            auto_merge_eligible=auto_merge_eligible,
        )
