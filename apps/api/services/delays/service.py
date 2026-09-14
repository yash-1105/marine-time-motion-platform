"""Delay management and reconciliation service (spec §10.4, Phase 09).

Manages:
- Delay listing, filtering, search, sorting, pagination
- Pareto cause distribution
- Duration allocation and unallocated duration tracking
- Stated vs recalculated duration reconciliation
- Missing reason review (DQ-007)
"""
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from sqlalchemy import desc, func, or_, select, text
from sqlalchemy.orm import Session

from apps.api.models.canonical import Delay, DelayAllocation, VesselCall
from apps.api.models.audit import AuditEvent
from apps.api.services.delays.mapping import map_to_canonical_category, CANONICAL_DELAY_CATEGORIES


class DelayService:
    def __init__(self, db: Session, tenant_id: str = "default-tenant"):
        self.db = db
        self.tenant_id = tenant_id

    def list_delays(
        self,
        movement_stage: Optional[str] = None,
        canonical_category: Optional[str] = None,
        cause_status: Optional[str] = None,
        resolution_status: Optional[str] = None,
        search: Optional[str] = None,
        has_mismatch: Optional[bool] = None,
        requires_review: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
        sort_by: str = "delay_hours",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """List delays with filtering, pagination, and multi-field search."""
        query = select(Delay, VesselCall.vcn, VesselCall.vessel_name).join(
            VesselCall, Delay.vessel_call_id == VesselCall.id
        )

        if movement_stage:
            query = query.where(Delay.movement_stage.ilike(f"%{movement_stage}%"))
        if canonical_category:
            query = query.where(Delay.canonical_category == canonical_category)
        if cause_status:
            query = query.where(Delay.cause_status.ilike(cause_status))
        if resolution_status:
            query = query.where(Delay.resolution_status.ilike(resolution_status))
        if has_mismatch is not None:
            query = query.where(Delay.has_reconciliation_mismatch == has_mismatch)
        if requires_review is not None:
            query = query.where(Delay.requires_reason_review == requires_review)
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    VesselCall.vcn.ilike(search_pattern),
                    VesselCall.vessel_name.ilike(search_pattern),
                    Delay.source_delay_id.ilike(search_pattern),
                    Delay.delay_reason.ilike(search_pattern),
                    Delay.source_category.ilike(search_pattern),
                    Delay.canonical_category.ilike(search_pattern),
                )
            )

        # Count total matching
        count_query = select(func.count()).select_from(query.subquery())
        total = self.db.execute(count_query).scalar_one()

        # Sorting
        sort_col = getattr(Delay, sort_by, Delay.total_duration_hours)
        if sort_order.lower() == "desc":
            query = query.order_by(desc(sort_col))
        else:
            query = query.order_by(sort_col)

        rows = self.db.execute(query.offset(skip).limit(limit)).all()

        items = []
        for delay, vcn, vessel_name in rows:
            allocations = self.db.execute(
                select(DelayAllocation).where(DelayAllocation.delay_id == delay.id)
            ).scalars().all()

            allocated_sum = sum(a.duration_hours for a in allocations)
            unallocated = max(0.0, round(delay.total_duration_hours - allocated_sum, 4))

            items.append({
                "id": str(delay.id),
                "source_delay_id": delay.source_delay_id,
                "vessel_call_id": str(delay.vessel_call_id),
                "vcn": vcn,
                "vessel_name": vessel_name,
                "movement_stage": delay.movement_stage,
                "total_duration_hours": delay.total_duration_hours,
                "is_early_service": delay.is_early_service,
                "scheduled_time": delay.scheduled_time.isoformat() if delay.scheduled_time else None,
                "served_time": delay.served_time.isoformat() if delay.served_time else None,
                "delay_hours": delay.delay_hours,
                "recalculated_delay_hours": delay.recalculated_delay_hours,
                "delay_reason": delay.delay_reason,
                "source_category": delay.source_category,
                "canonical_category": delay.canonical_category,
                "cause_status": delay.cause_status,
                "confidence": delay.confidence,
                "resolution_status": delay.resolution_status,
                "has_reconciliation_mismatch": delay.has_reconciliation_mismatch,
                "reconciliation_notes": delay.reconciliation_notes,
                "requires_reason_review": delay.requires_reason_review,
                "allocated_duration_hours": round(allocated_sum, 4),
                "unallocated_duration_hours": unallocated,
                "allocations_count": len(allocations),
            })

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": items,
        }

    def get_delay_detail(self, delay_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get complete detail of a delay record with all cause allocations and reconciliation."""
        row = self.db.execute(
            select(Delay, VesselCall.vcn, VesselCall.vessel_name)
            .join(VesselCall, Delay.vessel_call_id == VesselCall.id)
            .where(Delay.id == delay_id)
        ).first()

        if not row:
            return None

        delay, vcn, vessel_name = row

        allocations = self.db.execute(
            select(DelayAllocation)
            .where(DelayAllocation.delay_id == delay.id)
            .order_by(desc(DelayAllocation.is_primary), desc(DelayAllocation.duration_hours))
        ).scalars().all()

        allocated_sum = sum(a.duration_hours for a in allocations)
        unallocated = max(0.0, round(delay.total_duration_hours - allocated_sum, 4))

        return {
            "id": str(delay.id),
            "source_delay_id": delay.source_delay_id,
            "vessel_call_id": str(delay.vessel_call_id),
            "vcn": vcn,
            "vessel_name": vessel_name,
            "movement_stage": delay.movement_stage,
            "total_duration_hours": delay.total_duration_hours,
            "is_early_service": delay.is_early_service,
            "scheduled_time": delay.scheduled_time.isoformat() if delay.scheduled_time else None,
            "served_time": delay.served_time.isoformat() if delay.served_time else None,
            "delay_hours": delay.delay_hours,
            "recalculated_delay_hours": delay.recalculated_delay_hours,
            "delay_reason": delay.delay_reason,
            "source_category": delay.source_category,
            "canonical_category": delay.canonical_category,
            "cause_status": delay.cause_status,
            "confidence": delay.confidence,
            "resolution_status": delay.resolution_status,
            "has_reconciliation_mismatch": delay.has_reconciliation_mismatch,
            "reconciliation_notes": delay.reconciliation_notes,
            "requires_reason_review": delay.requires_reason_review,
            "allocated_duration_hours": round(allocated_sum, 4),
            "unallocated_duration_hours": unallocated,
            "allocations": [
                {
                    "id": str(a.id),
                    "cause": a.cause,
                    "canonical_category": a.canonical_category,
                    "reason": a.reason,
                    "duration_hours": a.duration_hours,
                    "is_primary": a.is_primary,
                    "cause_status": a.cause_status,
                    "confidence": a.confidence,
                    "inference_evidence": a.inference_evidence,
                    "human_review_state": a.human_review_state,
                }
                for a in allocations
            ],
        }

    def get_delays_summary(self) -> Dict[str, Any]:
        """
        Produce Pareto distribution of delay causes, stage breakdown,
        confirmed vs inferred counts, and total unallocated time.
        """
        delays = self.db.execute(select(Delay)).scalars().all()
        allocations = self.db.execute(select(DelayAllocation)).scalars().all()

        total_delays = len(delays)
        total_delay_hours = round(sum(d.total_duration_hours for d in delays), 2)

        # Pareto by Canonical Category
        category_map = {}
        for c in CANONICAL_DELAY_CATEGORIES:
            category_map[c] = {"category": c, "count": 0, "total_hours": 0.0}

        for d in delays:
            cat = d.canonical_category or "Other"
            if cat not in category_map:
                category_map[cat] = {"category": cat, "count": 0, "total_hours": 0.0}
            category_map[cat]["count"] += 1
            category_map[cat]["total_hours"] = round(category_map[cat]["total_hours"] + d.total_duration_hours, 2)

        # Pareto sorted
        pareto_categories = sorted(
            [v for v in category_map.values() if v["count"] > 0],
            key=lambda x: x["total_hours"],
            reverse=True,
        )

        running_sum = 0.0
        for item in pareto_categories:
            running_sum += item["total_hours"]
            item["cumulative_percentage"] = (
                round((running_sum / total_delay_hours) * 100, 1) if total_delay_hours > 0 else 0.0
            )

        # Stage breakdown
        stage_map = {}
        for d in delays:
            stg = d.movement_stage or "Unknown"
            if stg not in stage_map:
                stage_map[stg] = {"stage": stg, "count": 0, "total_hours": 0.0}
            stage_map[stg]["count"] += 1
            stage_map[stg]["total_hours"] = round(stage_map[stg]["total_hours"] + d.total_duration_hours, 2)

        stage_breakdown = list(stage_map.values())

        # Cause status breakdown (Confirmed vs Inferred)
        confirmed_count = sum(1 for d in delays if (d.cause_status or "").lower() == "confirmed")
        inferred_count = sum(1 for d in delays if (d.cause_status or "").lower() == "inferred")

        # Unallocated calculation
        total_allocated_hours = sum(a.duration_hours for a in allocations)
        total_unallocated_hours = max(0.0, round(total_delay_hours - total_allocated_hours, 2))

        # Reconciliation mismatches count
        mismatches_count = sum(1 for d in delays if d.has_reconciliation_mismatch)

        # Reviews needed count (DQ-007)
        review_required_count = sum(1 for d in delays if d.requires_reason_review)

        return {
            "total_delays": total_delays,
            "total_delay_hours": total_delay_hours,
            "confirmed_count": confirmed_count,
            "inferred_count": inferred_count,
            "total_allocated_hours": round(total_allocated_hours, 2),
            "total_unallocated_hours": total_unallocated_hours,
            "reconciliation_mismatches_count": mismatches_count,
            "review_required_count": review_required_count,
            "pareto_categories": pareto_categories,
            "stage_breakdown": stage_breakdown,
        }

    def allocate_causes(
        self,
        delay_id: uuid.UUID,
        allocations_data: List[Dict[str, Any]],
        actor: str = "system",
        rationale: str = "Manual delay cause allocation",
    ) -> Dict[str, Any]:
        """
        Configure multiple causes for a delay with durations and primary/secondary designations.
        Allocations must sum to the delay duration or the remainder is explicitly unallocated.
        """
        delay = self.db.execute(select(Delay).where(Delay.id == delay_id)).scalar_one_or_none()
        if not delay:
            raise ValueError(f"Delay {delay_id} not found")

        # Check total allocation does not exceed delay duration
        sum_hours = round(sum(float(a.get("duration_hours", 0.0)) for a in allocations_data), 4)
        if sum_hours > round(delay.total_duration_hours, 4) + 0.01:
            raise ValueError(
                f"Sum of allocations ({sum_hours}h) exceeds delay total duration ({delay.total_duration_hours}h)"
            )

        # Delete existing allocations
        existing = self.db.execute(
            select(DelayAllocation).where(DelayAllocation.delay_id == delay_id)
        ).scalars().all()
        for e in existing:
            self.db.delete(e)

        primary_found = False
        new_allocs = []
        for a_data in allocations_data:
            dur = float(a_data.get("duration_hours", 0.0))
            is_prim = bool(a_data.get("is_primary", False))
            if is_prim and not primary_found:
                primary_found = True
            elif is_prim and primary_found:
                is_prim = False  # only one primary

            rsn = a_data.get("reason")
            canon_cat = a_data.get("canonical_category") or map_to_canonical_category(None, rsn)

            alloc = DelayAllocation(
                delay_id=delay.id,
                cause=canon_cat,
                canonical_category=canon_cat,
                reason=rsn,
                duration_hours=dur,
                is_primary=is_prim,
                cause_status=a_data.get("cause_status", "CONFIRMED"),
                confidence=a_data.get("confidence", 1.0),
                inference_evidence=a_data.get("inference_evidence"),
                human_review_state=a_data.get("human_review_state", "APPROVED"),
            )
            self.db.add(alloc)
            new_allocs.append(alloc)

        # If no primary designated, make the first one primary
        if new_allocs and not primary_found:
            new_allocs[0].is_primary = True

        # Audit event
        audit = AuditEvent(
            actor_id=actor,
            actor_email=f"{actor}@port.local",
            actor_role="lead_analyst",
            action="ALLOCATE_CAUSES",
            resource_type="delay_allocation",
            resource_id=str(delay.id),
            entity_name="canonical.delay_allocation",
            entity_id=str(delay.id),
            details={
                "delay_id": str(delay.id),
                "total_duration": delay.total_duration_hours,
                "allocations_count": len(new_allocs),
                "allocated_hours": sum_hours,
                "unallocated_hours": max(0.0, round(delay.total_duration_hours - sum_hours, 4)),
                "rationale": rationale,
            },
        )
        self.db.add(audit)
        self.db.commit()

        return self.get_delay_detail(delay.id)

    def review_delay_reason(
        self,
        delay_id: uuid.UUID,
        canonical_category: str,
        reason: str,
        actor: str = "lead_analyst",
        decision: str = "APPROVED",
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Review and resolve a missing reason or inferred delay (e.g. DQ-007 review).
        """
        delay = self.db.execute(select(Delay).where(Delay.id == delay_id)).scalar_one_or_none()
        if not delay:
            raise ValueError(f"Delay {delay_id} not found")

        delay.canonical_category = canonical_category
        delay.delay_reason = reason
        delay.requires_reason_review = False
        delay.resolution_status = "Closed" if decision == "APPROVED" else "Under Review"

        # Update primary allocation
        alloc = self.db.execute(
            select(DelayAllocation)
            .where(DelayAllocation.delay_id == delay.id, DelayAllocation.is_primary == True)
        ).scalar_one_or_none()

        if alloc:
            alloc.canonical_category = canonical_category
            alloc.cause = canonical_category
            alloc.reason = reason
            alloc.human_review_state = decision
            if decision == "APPROVED":
                alloc.cause_status = "CONFIRMED"
        else:
            alloc = DelayAllocation(
                delay_id=delay.id,
                cause=canonical_category,
                canonical_category=canonical_category,
                reason=reason,
                duration_hours=delay.total_duration_hours,
                is_primary=True,
                cause_status="CONFIRMED" if decision == "APPROVED" else "INFERRED",
                confidence=1.0,
                human_review_state=decision,
            )
            self.db.add(alloc)

        # Audit
        audit = AuditEvent(
            actor_id=actor,
            actor_email=f"{actor}@port.local",
            actor_role="lead_analyst",
            action="REVIEW_DELAY_REASON",
            resource_type="delay",
            resource_id=str(delay.id),
            entity_name="canonical.delay",
            entity_id=str(delay.id),
            details={
                "decision": decision,
                "canonical_category": canonical_category,
                "reason": reason,
                "notes": notes,
            },
        )
        self.db.add(audit)
        self.db.commit()

        return self.get_delay_detail(delay.id)
