from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.canonical import VesselCall
from apps.api.models.identity import MatchCandidate, MatchEvidence, MergeDecision
from apps.api.models.quality import QualityIssue, QualityRule
from apps.api.services.identity.matcher import IdentityMatcher
from apps.api.services.identity.merger import MergerService
from apps.api.services.identity.normalizer import VesselNameNormalizer


class IdentityEngine:
    def __init__(self, db: Session, tenant_id: str = "synthetic-tenant"):
        self.db = db
        self.tenant_id = tenant_id
        self.matcher = IdentityMatcher()

    def generate_candidates(self) -> list[MatchCandidate]:
        """
        Scans unmerged vessel calls, compares candidate pairs using deterministic & probabilistic rules,
        and saves MatchCandidate & MatchEvidence rows with explainable breakdown.
        """
        query = select(VesselCall).where(
            VesselCall.is_merged == False
        )
        if self.tenant_id:
            query = query.where(VesselCall.tenant_id == self.tenant_id)
        
        vessel_calls = self.db.execute(query).scalars().all()
        created_candidates = []

        # Compare all pairs (N is small ~74 calls)
        for i in range(len(vessel_calls)):
            for j in range(i + 1, len(vessel_calls)):
                v1 = vessel_calls[i]
                v2 = vessel_calls[j]

                # Blocking filter:
                # Pair must share VCN OR share IMO OR have normalised name similarity >= 0.70
                v1_vcn = (v1.vcn or "").strip()
                v2_vcn = (v2.vcn or "").strip()
                v1_imo = (v1.imo_number or "").strip()
                v2_imo = (v2.imo_number or "").strip()

                same_vcn = bool(v1_vcn and v2_vcn and v1_vcn == v2_vcn)
                same_imo = bool(v1_imo and v2_imo and v1_imo == v2_imo)
                norm_sim, _ = VesselNameNormalizer.similarity(v1.vessel_name, v2.vessel_name)

                # If they share nothing in common, skip pair
                if not same_vcn and not same_imo and norm_sim < 0.70:
                    continue

                # Evaluate pair
                result = self.matcher.evaluate_pair(v1, v2)

                # Check if candidate already exists
                id1, id2 = sorted([str(v1.id), str(v2.id)])
                existing = self.db.execute(
                    select(MatchCandidate).where(
                        MatchCandidate.source_record_1_id == id1,
                        MatchCandidate.source_record_2_id == id2,
                    )
                ).scalar_one_or_none()

                if not existing:
                    candidate = MatchCandidate(
                        source_record_1_id=id1,
                        source_record_2_id=id2,
                        match_score=result.match_score,
                        status=result.status,
                        match_type=result.match_type,
                        conflict_detected=result.conflict_detected,
                        conflict_reasons=result.conflict_reasons,
                    )
                    self.db.add(candidate)
                    self.db.flush()

                    # Save evidence breakdown
                    for ev in result.evidence_breakdown:
                        evidence_row = MatchEvidence(
                            match_candidate_id=candidate.id,
                            evidence_type=ev.attribute,
                            evidence_detail={
                                "attribute": ev.attribute,
                                "record_1_value": ev.value_1,
                                "record_2_value": ev.value_2,
                                "agreement": ev.agreement,
                                "weight": ev.weight,
                                "contribution": ev.contribution,
                                "explanation": ev.explanation,
                            },
                        )
                        self.db.add(evidence_row)

                    # Also register DQ cases for quality engine
                    # Case DQ-001: Exact duplicate row
                    if same_vcn and norm_sim == 1.0 and result.match_score >= 0.98:
                        self._register_quality_issue("DQ-001", v2.id, f"VesselCall:{v2.id}", "CRITICAL")

                    # Case DQ-002: Probable duplicate with punctuation variation
                    elif same_vcn and norm_sim >= 0.98 and result.match_score >= 0.98:
                        self._register_quality_issue("DQ-002", v2.id, f"VesselCall:{v2.id}", "HIGH")

                    created_candidates.append(candidate)
                else:
                    existing.match_score = result.match_score
                    existing.status = result.status
                    existing.match_type = result.match_type
                    existing.conflict_detected = result.conflict_detected
                    existing.conflict_reasons = result.conflict_reasons
                    created_candidates.append(existing)

        self.db.commit()
        return created_candidates

    def _register_quality_issue(self, rule_id: str, vc_id: Any, ref: str, severity: str):
        rule = self.db.execute(select(QualityRule).where(QualityRule.rule_id == rule_id)).scalar_one_or_none()
        if not rule:
            rule = QualityRule(
                rule_id=rule_id,
                scope="vessel_call",
                severity=severity,
                pass_fail_expression="no duplicate vessel calls",
            )
            self.db.add(rule)
            self.db.flush()

        # Check existing
        existing_issue = self.db.execute(
            select(QualityIssue).where(
                QualityIssue.rule_id == rule.id,
                QualityIssue.vessel_call_id == vc_id,
            )
        ).scalar_one_or_none()
        if not existing_issue:
            issue = QualityIssue(
                rule_id=rule.id,
                vessel_call_id=vc_id,
                record_reference=ref,
                issue_status="RESOLVED" if severity == "CRITICAL" else "OPEN",
            )
            self.db.add(issue)

    def auto_merge_candidates(self) -> list[MergeDecision]:
        """
        Auto-merges all candidates meeting the >= 0.98 threshold without key conflicts.
        """
        candidates = self.generate_candidates()
        merge_decisions = []

        for cand in candidates:
            if cand.status == "AUTO_MERGE_CANDIDATE" and not cand.conflict_detected:
                try:
                    decision = MergerService.execute_merge(
                        self.db,
                        candidate_id=str(cand.id),
                        actor="system:auto_merge",
                        manual=False,
                    )
                    merge_decisions.append(decision)
                except Exception as e:
                    print(f"Error auto-merging candidate {cand.id}: {e}")

        return merge_decisions

    def get_consolidated_population_count(self) -> int:
        """
        Returns the count of consolidated, active vessel calls (excluding merged records).
        """
        query = select(VesselCall).where(VesselCall.is_merged == False)
        if self.tenant_id:
            query = query.where(VesselCall.tenant_id == self.tenant_id)
        calls = self.db.execute(query).scalars().all()
        return len(calls)
