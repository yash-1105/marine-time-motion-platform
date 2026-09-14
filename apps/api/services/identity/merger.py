import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from apps.api.models.canonical import VesselCall, EventOccurrence, ServiceRequest, Delay
from apps.api.models.identity import MatchCandidate, MatchEvidence, MergeDecision
from apps.api.models.audit import AuditEvent
from apps.api.services.identity.survivorship import SurvivorshipEngine


class MergerService:
    @staticmethod
    def _serialize_vessel_call(vc: VesselCall) -> Dict[str, Any]:
        data = {}
        for col in vc.__table__.columns:
            val = getattr(vc, col.name, None)
            if isinstance(val, datetime):
                data[col.name] = val.isoformat()
            elif val is not None:
                data[col.name] = str(val) if col.name == "id" or "uuid" in str(col.type).lower() else val
            else:
                data[col.name] = None
        return data

    @staticmethod
    def _apply_serialized_fields(vc: VesselCall, data: Dict[str, Any]):
        for col in vc.__table__.columns:
            if col.name in ["id", "created_at"]:
                continue
            if col.name in data:
                setattr(vc, col.name, data[col.name])

    @classmethod
    def execute_merge(
        cls,
        db: Session,
        candidate_id: str,
        actor: str = "system",
        manual: bool = False,
        custom_survivorship: Optional[Dict[str, Any]] = None,
    ) -> MergeDecision:
        candidate = db.execute(
            select(MatchCandidate).where(MatchCandidate.id == candidate_id)
        ).scalar_one_or_none()
        if not candidate:
            raise ValueError(f"MatchCandidate {candidate_id} not found")

        # Hard rule: Any conflicting IMO or VCN must never auto-merge regardless of score
        if candidate.conflict_detected and not manual:
            raise ValueError(
                f"Cannot auto-merge candidate {candidate_id} with conflicting identifiers: "
                f"{', '.join(candidate.conflict_reasons or [])}"
            )

        v1 = db.execute(select(VesselCall).where(VesselCall.id == candidate.source_record_1_id)).scalar_one_or_none()
        v2 = db.execute(select(VesselCall).where(VesselCall.id == candidate.source_record_2_id)).scalar_one_or_none()
        if not v1 or not v2:
            raise ValueError("One or both candidate vessel calls could not be found in canonical store")

        survivor, merged = SurvivorshipEngine.determine_survivor_record(v1, v2)

        # 1. Capture full prior state snapshot
        survivor_prior = cls._serialize_vessel_call(survivor)
        merged_prior = cls._serialize_vessel_call(merged)

        # 2. Transfer child records from merged to survivor, recording their IDs
        transferred_children = {
            "event_occurrences": [],
            "service_requests": [],
            "delays": []
        }

        # Events
        events = db.execute(select(EventOccurrence).where(EventOccurrence.vessel_call_id == merged.id)).scalars().all()
        for ev in events:
            transferred_children["event_occurrences"].append(str(ev.id))
            ev.vessel_call_id = survivor.id

        # Services
        services = db.execute(select(ServiceRequest).where(ServiceRequest.vessel_call_id == merged.id)).scalars().all()
        for srv in services:
            transferred_children["service_requests"].append(str(srv.id))
            srv.vessel_call_id = survivor.id

        # Delays
        delays = db.execute(select(Delay).where(Delay.vessel_call_id == merged.id)).scalars().all()
        for dl in delays:
            transferred_children["delays"].append(str(dl.id))
            dl.vessel_call_id = survivor.id

        # 3. Apply consolidated attributes to survivor
        preview = SurvivorshipEngine.generate_preview(v1, v2)
        consolidated = preview["consolidated_preview"]
        if custom_survivorship:
            consolidated.update(custom_survivorship)

        for field_name, val in consolidated.items():
            if hasattr(survivor, field_name) and field_name not in ["id", "created_at", "tenant_id"]:
                setattr(survivor, field_name, val)

        # 4. Mark merged record
        merged.is_merged = True
        merged.merged_into_id = survivor.id

        # 5. Snapshot evidence
        evidence_list = db.execute(
            select(MatchEvidence).where(MatchEvidence.match_candidate_id == candidate.id)
        ).scalars().all()
        evidence_snapshot = [
            {"type": ev.evidence_type, "detail": ev.evidence_detail} for ev in evidence_list
        ]

        prior_snapshot = {
            "survivor_id": str(survivor.id),
            "survivor_fields": survivor_prior,
            "merged_id": str(merged.id),
            "merged_fields": merged_prior,
            "transferred_children": transferred_children,
        }

        # 6. Create MergeDecision
        decision = MergeDecision(
            match_candidate_id=candidate.id,
            decision="MERGED",
            is_reversible=True,
            survivor_record_id=str(survivor.id),
            merged_record_id=str(merged.id),
            evidence_snapshot=evidence_snapshot,
            prior_state_snapshot=prior_snapshot,
            rule_version="1.0",
            actor=actor,
            notes=f"Merged {merged.vessel_name} ({merged.vcn}) into {survivor.vessel_name} ({survivor.vcn})",
        )
        db.add(decision)

        # Update candidate status
        candidate.status = "MERGED"

        # 7. Audit log
        audit_entry = AuditEvent(
            action="IDENTITY_MERGE",
            resource_type="vessel_call",
            resource_id=str(survivor.id),
            actor_id=actor,
            actor_role="DATA_STEWARD" if manual else "SYSTEM",
            details={
                "candidate_id": str(candidate.id),
                "survivor_id": str(survivor.id),
                "survivor_vcn": survivor.vcn,
                "merged_id": str(merged.id),
                "merged_vcn": merged.vcn,
                "match_score": candidate.match_score,
                "manual_override": manual,
            },
        )
        db.add(audit_entry)

        db.commit()
        db.refresh(decision)
        return decision

    @classmethod
    def execute_unmerge(
        cls,
        db: Session,
        decision_id: str,
        actor: str = "system",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        decision = db.execute(
            select(MergeDecision).where(MergeDecision.id == decision_id)
        ).scalar_one_or_none()
        if not decision:
            raise ValueError(f"MergeDecision {decision_id} not found")
        if decision.decision != "MERGED":
            raise ValueError(f"Decision {decision_id} has status '{decision.decision}', cannot unmerge")

        snapshot = decision.prior_state_snapshot or {}
        survivor_id = snapshot.get("survivor_id") or decision.survivor_record_id
        merged_id = snapshot.get("merged_id") or decision.merged_record_id

        survivor = db.execute(select(VesselCall).where(VesselCall.id == survivor_id)).scalar_one_or_none()
        merged = db.execute(select(VesselCall).where(VesselCall.id == merged_id)).scalar_one_or_none()
        if not survivor or not merged:
            raise ValueError("Survivor or merged record missing, unmerge aborted")

        # 1. Restore survivor attributes
        if "survivor_fields" in snapshot:
            cls._apply_serialized_fields(survivor, snapshot["survivor_fields"])

        # 2. Restore merged attributes
        if "merged_fields" in snapshot:
            cls._apply_serialized_fields(merged, snapshot["merged_fields"])

        # 3. Unmark merged record
        merged.is_merged = False
        merged.merged_into_id = None

        # 4. Restore transferred child records
        transferred = snapshot.get("transferred_children", {})
        for ev_id in transferred.get("event_occurrences", []):
            ev = db.execute(select(EventOccurrence).where(EventOccurrence.id == ev_id)).scalar_one_or_none()
            if ev:
                ev.vessel_call_id = merged.id

        for srv_id in transferred.get("service_requests", []):
            srv = db.execute(select(ServiceRequest).where(ServiceRequest.id == srv_id)).scalar_one_or_none()
            if srv:
                srv.vessel_call_id = merged.id

        for dl_id in transferred.get("delays", []):
            dl = db.execute(select(Delay).where(Delay.id == dl_id)).scalar_one_or_none()
            if dl:
                dl.vessel_call_id = merged.id

        # 5. Update decision and candidate
        decision.decision = "UNMERGED"
        decision.is_reversible = False
        decision.notes = (decision.notes or "") + f" | Unmerged by {actor}: {notes or 'no notes'}"

        candidate = db.execute(
            select(MatchCandidate).where(MatchCandidate.id == decision.match_candidate_id)
        ).scalar_one_or_none()
        if candidate:
            candidate.status = "STEWARD_REVIEW"

        # 6. Audit log
        audit_entry = AuditEvent(
            action="IDENTITY_UNMERGE",
            resource_type="vessel_call",
            resource_id=str(survivor.id),
            actor_id=actor,
            actor_role="DATA_STEWARD",
            details={
                "decision_id": str(decision.id),
                "survivor_id": str(survivor.id),
                "merged_id": str(merged.id),
                "reason": notes,
            },
        )
        db.add(audit_entry)

        db.commit()

        return {
            "status": "success",
            "message": "Unmerge completed successfully. Records and children restored to prior state.",
            "survivor_id": str(survivor.id),
            "merged_id": str(merged.id),
            "is_merged": False,
        }
