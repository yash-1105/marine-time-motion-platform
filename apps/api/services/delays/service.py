"""Delay management and reconciliation service (spec §10.4, Phase 09).

Manages:
- Delay listing, filtering, search, sorting, pagination
- Pareto cause distribution
- Duration allocation and unallocated duration tracking
- Stated vs recalculated duration reconciliation
- Missing reason review (DQ-007)
"""
import uuid
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from apps.api.models.audit import AuditEvent
from apps.api.models.canonical import Delay, DelayAllocation, ServiceAssignment, ServiceExecution, ServiceRequest, VesselCall
from apps.api.services.analytics.duration_semantics import (
    compute_execution_delay,
    compute_planning_lead_time,
    compute_scheduling_gap,
)
from apps.api.services.delays.mapping import CANONICAL_DELAY_CATEGORIES, map_to_canonical_category


class DelayService:
    def __init__(self, db: Session, tenant_id: str = "default-tenant"):
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def _leg(movement_type: str | None) -> str:
        """Map source movement without collapsing SHIFTING into an arrival/departure leg."""
        value = (movement_type or "").strip().upper()
        if value in {"ARRIVAL", "INWARD"}:
            return "ARRIVAL_INWARD"
        if value in {"SAILING", "OUTWARD", "DEPARTURE"}:
            return "SAILING_OUTWARD"
        if value == "SHIFTING":
            return "SHIFTING"
        return "UNCLASSIFIED"

    def list_service_timings(self, leg: str = "ALL") -> dict[str, Any]:
        """Expose governed service timing semantics without treating duration as delay.

        Service end timestamps are not supplied by the current source contract, so
        `service_duration_hours` is deliberately UNAVAILABLE rather than inferred.
        """
        stmt = (
            select(ServiceRequest, ServiceAssignment, ServiceExecution, VesselCall)
            .outerjoin(ServiceAssignment, ServiceAssignment.service_request_id == ServiceRequest.id)
            .outerjoin(ServiceExecution, ServiceExecution.service_assignment_id == ServiceAssignment.id)
            .join(VesselCall, VesselCall.id == ServiceRequest.vessel_call_id)
            .where(VesselCall.is_merged.is_(False))
        )
        if self.tenant_id != "*":
            stmt = stmt.where(VesselCall.tenant_id == self.tenant_id)

        rows = []
        for request, assignment, execution, vessel_call in self.db.execute(stmt).all():
            movement_leg = self._leg(request.movement_type)
            if leg != "ALL" and movement_leg != leg:
                continue

            planning_result = compute_planning_lead_time(request.submission_time, request.requested_time)
            scheduled_time = assignment.scheduled_time if assignment else None
            served_time = execution.served_time if execution else None
            scheduling_result = compute_scheduling_gap(request.requested_time, scheduled_time)
            execution_result = compute_execution_delay(scheduled_time, served_time)
            planning = planning_result.value_hours
            scheduling = scheduling_result.value_hours
            execution_delay = execution_result.value_hours
            dq_status = "CLEAN"
            unavailable = []
            if request.requested_time is None:
                unavailable.append("requested_time missing")
            if scheduled_time is None:
                unavailable.append("scheduled_time missing")
            if served_time is None:
                unavailable.append("served_time missing")
            if scheduling is not None and scheduling < 0:
                dq_status = "DQ_SCHEDULE_BEFORE_REQUEST"
            elif unavailable:
                dq_status = "MISSING_DATA"
            delay_status = (
                "UNAVAILABLE" if execution_delay is None else "EARLY" if execution_delay < 0 else "ON_TIME" if execution_delay == 0 else "LATE"
            )
            rows.append({
                "service_request_id": str(request.id), "service_assignment_id": str(assignment.id) if assignment else None, "service_execution_id": str(execution.id) if execution else None,
                "vessel_call_id": str(vessel_call.id), "vcn": vessel_call.vcn, "vessel_name": vessel_call.vessel_name,
                "movement": request.movement_type, "leg": movement_leg, "service_type": request.service_type,
                "submission_time": request.submission_time.isoformat() if request.submission_time else None,
                "requested_time": request.requested_time.isoformat() if request.requested_time else None,
                "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
                "served_time": served_time.isoformat() if served_time else None,
                "planning_lead_time_hours": planning, "scheduling_gap_hours": scheduling,
                "execution_delay_hours": execution_delay, "service_duration_hours": None,
                "service_duration_status": "UNAVAILABLE", "service_duration_reason": "No service-end timestamp is supplied by the source contract.",
                "execution_delay_status": delay_status, "formula_version": "service-timing-v1.0",
                "source_record_ids": [str(record.id) for record in (request, assignment, execution) if record],
                "data_quality_status": dq_status, "unavailable_inputs": unavailable,
            })
        return {"leg": leg, "formula_version": "service-timing-v1.0", "items": rows, "total": len(rows)}

    def list_delays(
        self,
        leg: str = "ALL",
        movement_stage: str | None = None,
        canonical_category: str | None = None,
        cause_status: str | None = None,
        resolution_status: str | None = None,
        search: str | None = None,
        has_mismatch: bool | None = None,
        requires_review: bool | None = None,
        skip: int = 0,
        limit: int = 50,
        sort_by: str = "delay_hours",
        sort_order: str = "desc"
    ) -> dict[str, Any]:
        """List delays with filtering, pagination, and multi-field search."""
        query = select(Delay, VesselCall.vcn, VesselCall.vessel_name).join(
            VesselCall, Delay.vessel_call_id == VesselCall.id
        )

        if movement_stage:
            query = query.where(Delay.movement_stage.ilike(f"%{movement_stage}%"))
        if leg != "ALL":
            if leg == "ARRIVAL_INWARD":
                query = query.where(or_(Delay.movement_stage.ilike("%Arrival%"), Delay.movement_stage.ilike("%Inward%")))
            elif leg == "SAILING_OUTWARD":
                query = query.where(or_(Delay.movement_stage.ilike("%Sailing%"), Delay.movement_stage.ilike("%Outward%")))
            elif leg == "SHIFTING":
                query = query.where(Delay.movement_stage.ilike("%Shifting%"))
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

    def get_delay_detail(self, delay_id: uuid.UUID) -> dict[str, Any] | None:
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

    def get_delays_summary(self, leg: str = "ALL") -> dict[str, Any]:
        """
        Produce Pareto distribution of delay causes, stage breakdown,
        confirmed vs inferred counts, and total unallocated time.
        """
        delays = self.db.execute(select(Delay)).scalars().all()
        if leg != "ALL":
            delays = [delay for delay in delays if self._leg(delay.movement_stage) == leg]
        delay_ids = {delay.id for delay in delays}
        allocations = [
            allocation for allocation in self.db.execute(select(DelayAllocation)).scalars().all()
            if allocation.delay_id in delay_ids
        ]

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
            "leg": leg,
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
        allocations_data: list[dict[str, Any]],
        actor: str = "system",
        rationale: str = "Manual delay cause allocation",
    ) -> dict[str, Any]:
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
        notes: str | None = None,
    ) -> dict[str, Any]:
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
