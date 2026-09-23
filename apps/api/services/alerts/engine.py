"""Alerts and action management engine (spec §15, Phase 09).

Manages:
- Governed alert rules evaluation
- Deduplication and alert state machine (NEW -> ACKNOWLEDGED -> RESOLVED)
- Action item lifecycle (OPEN -> IN_PROGRESS -> COMPLETED)
- Audit logging for all actions and acknowledgements
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.models.analytics import ActionItem, AlertRule, BottleneckRecord, OperationalAlert, OutlierRecord
from apps.api.models.audit import AuditEvent
from apps.api.models.canonical import Delay, VesselCall

DEFAULT_ALERT_RULES = [
    {
        "rule_code": "RULE_MISSING_DELAY_REASON",
        "name": "Missing Delay Reason Review (DQ-007)",
        "category": "QUALITY",
        "severity": "MEDIUM",
        "description": "Positive movement execution delay without documented reason or category.",
        "threshold_config": {"delay_hours_min": 0.05},
        "suppression_window_minutes": 120,
    },
    {
        "rule_code": "RULE_CRITICAL_BOTTLENECK",
        "name": "Critical Bottleneck Detected",
        "category": "BOTTLENECK",
        "severity": "HIGH",
        "description": "Operational stage or resource bottleneck score exceeded critical threshold.",
        "threshold_config": {"score_threshold": 65.0},
        "suppression_window_minutes": 240,
    },
    {
        "rule_code": "RULE_EXTREME_P90_OUTLIER",
        "name": "Extreme Outlier / P90 Tail Risk (DQ-008)",
        "category": "OUTLIER",
        "severity": "CRITICAL",
        "description": "Turnaround or stage duration severely diverges from historical P90 or baseline.",
        "threshold_config": {"p90_multiplier": 2.0},
        "suppression_window_minutes": 1440,
    },
    {
        "rule_code": "RULE_RESOURCE_SHORTAGE",
        "name": "Marine Resource Shortage Delay",
        "category": "RESOURCE",
        "severity": "MEDIUM",
        "description": "Pilot or tug service delay caused by resource unavailability or out-of-service condition.",
        "threshold_config": {"delay_hours_min": 1.0},
        "suppression_window_minutes": 180,
    },
    {
        "rule_code": "RULE_BERTH_CONFLICT",
        "name": "Berth Non-Availability Conflict",
        "category": "RESOURCE",
        "severity": "HIGH",
        "description": "Vessel delayed waiting for available berth due to congestion or overstay.",
        "threshold_config": {"delay_hours_min": 1.0},
        "suppression_window_minutes": 180,
    },
]


class AlertEngine:
    def __init__(self, db: Session, tenant_id: str = "default-tenant"):
        self.db = db
        self.tenant_id = tenant_id
        self._open_alerts: dict[tuple[str, str, str], OperationalAlert] | None = None

    def seed_default_rules(self) -> None:
        """Ensure standard alert rules exist in analytics.alert_rule."""
        for r_spec in DEFAULT_ALERT_RULES:
            existing = self.db.execute(
                select(AlertRule).where(AlertRule.rule_code == r_spec["rule_code"])
            ).scalar_one_or_none()

            if not existing:
                rule = AlertRule(
                    rule_code=r_spec["rule_code"],
                    name=r_spec["name"],
                    category=r_spec["category"],
                    severity=r_spec["severity"],
                    description=r_spec["description"],
                    threshold_config=r_spec["threshold_config"],
                    is_active=True,
                    suppression_window_minutes=r_spec["suppression_window_minutes"],
                )
                self.db.add(rule)
        self.db.commit()

    def evaluate_rules(self) -> list[dict[str, Any]]:
        """
        Evaluate operational data against active alert rules.
        Creates alerts with deduplication so existing open alerts are not duplicated.
        """
        self.seed_default_rules()

        active_rules = {
            r.rule_code: r for r in self.db.execute(select(AlertRule).where(AlertRule.is_active)).scalars().all()
        }
        self._open_alerts = {
            (alert.rule_code, alert.linked_entity_type, alert.linked_entity_id): alert
            for alert in self.db.execute(
                select(OperationalAlert).where(OperationalAlert.status.in_(["NEW", "ACKNOWLEDGED"]))
            )
            .scalars()
            .all()
        }

        generated_alerts = []

        # 1. Evaluate RULE_MISSING_DELAY_REASON (DQ-007)
        if "RULE_MISSING_DELAY_REASON" in active_rules:
            rule = active_rules["RULE_MISSING_DELAY_REASON"]
            review_delays = self.db.execute(
                select(Delay, VesselCall.vcn)
                .join(VesselCall, Delay.vessel_call_id == VesselCall.id)
                .where(Delay.requires_reason_review)
            ).all()

            for delay, vcn in review_delays:
                alert = self._create_or_get_alert(
                    rule=rule,
                    vessel_call_id=delay.vessel_call_id,
                    vcn=vcn,
                    title=f"Mandatory Delay Reason Review: {vcn} ({delay.movement_stage})",
                    description=(
                        f"Vessel {vcn} experienced positive execution delay of {delay.total_duration_hours}h "
                        f"on {delay.movement_stage} without documented reason or category. DQ-007 review required."
                    ),
                    linked_entity_type="canonical.delay",
                    linked_entity_id=str(delay.id),
                    evidence={
                        "delay_id": str(delay.id),
                        "movement_stage": delay.movement_stage,
                        "delay_hours": delay.total_duration_hours,
                        "rule_id": "DQ-007",
                    },
                )
                if alert:
                    generated_alerts.append(alert)

            # Also check quality issues flagged as DQ-007
            from apps.api.models.quality import QualityIssue, QualityRule

            dq7_issues = self.db.execute(
                select(QualityIssue, VesselCall.vcn)
                .join(QualityRule, QualityIssue.rule_id == QualityRule.id)
                .join(VesselCall, QualityIssue.vessel_call_id == VesselCall.id)
                .where(QualityRule.rule_id == "DQ-007")
            ).all()

            for issue, vcn in dq7_issues:
                alert = self._create_or_get_alert(
                    rule=rule,
                    vessel_call_id=issue.vessel_call_id,
                    vcn=vcn,
                    title=f"Mandatory Delay Reason Review: {vcn} (DQ-007)",
                    description=(
                        f"Vessel {vcn} experienced positive execution delay without documented reason or category. "
                        f"DQ-007 review required at MEDIUM severity."
                    ),
                    linked_entity_type="quality.quality_issue",
                    linked_entity_id=str(issue.id),
                    evidence={
                        "issue_id": str(issue.id),
                        "rule_id": "DQ-007",
                        "severity": "MEDIUM",
                    },
                )
                if alert:
                    generated_alerts.append(alert)

        # 2. Evaluate RULE_CRITICAL_BOTTLENECK
        if "RULE_CRITICAL_BOTTLENECK" in active_rules:
            rule = active_rules["RULE_CRITICAL_BOTTLENECK"]
            thresh = rule.threshold_config.get("score_threshold", 65.0)
            bottlenecks = (
                self.db.execute(select(BottleneckRecord).where(BottleneckRecord.overall_bottleneck_score >= thresh))
                .scalars()
                .all()
            )

            for bn in bottlenecks:
                alert = self._create_or_get_alert(
                    rule=rule,
                    vessel_call_id=None,
                    vcn=None,
                    title=f"Critical Bottleneck: {bn.stage_or_resource} (Rank #{bn.rank})",
                    description=(
                        f"{bn.stage_or_resource} ({bn.bottleneck_type}) reached bottleneck score "
                        f"{bn.overall_bottleneck_score}/100 with CV {bn.details.get('cv')} and tail risk {bn.details.get('tail_risk_ratio')}."
                    ),
                    linked_entity_type="analytics.bottleneck_record",
                    linked_entity_id=str(bn.id),
                    evidence={
                        "stage_or_resource": bn.stage_or_resource,
                        "overall_score": bn.overall_bottleneck_score,
                        "rank": bn.rank,
                        "details": bn.details,
                    },
                )
                if alert:
                    generated_alerts.append(alert)

        # 3. Evaluate RULE_EXTREME_P90_OUTLIER (DQ-008 & Extreme Outliers)
        if "RULE_EXTREME_P90_OUTLIER" in active_rules:
            rule = active_rules["RULE_EXTREME_P90_OUTLIER"]
            outliers = (
                self.db.execute(select(OutlierRecord).where(OutlierRecord.severity.in_(["HIGH", "CRITICAL"])))
                .scalars()
                .all()
            )

            for outl in outliers:
                alert = self._create_or_get_alert(
                    rule=rule,
                    vessel_call_id=outl.vessel_call_id,
                    vcn=outl.vcn,
                    title=f"Extreme Outlier: {outl.vcn} - {outl.metric_name}",
                    description=(
                        f"Vessel {outl.vcn} observed {outl.metric_name} of {outl.observed_value} "
                        f"(divergence +{outl.divergence} from benchmark {outl.benchmark_or_p90})."
                    ),
                    linked_entity_type="analytics.outlier_record",
                    linked_entity_id=str(outl.id),
                    evidence=outl.evidence,
                )
                if alert:
                    generated_alerts.append(alert)

        # 4. Evaluate RULE_RESOURCE_SHORTAGE
        if "RULE_RESOURCE_SHORTAGE" in active_rules:
            rule = active_rules["RULE_RESOURCE_SHORTAGE"]
            resource_delays = self.db.execute(
                select(Delay, VesselCall.vcn)
                .join(VesselCall, Delay.vessel_call_id == VesselCall.id)
                .where(
                    Delay.canonical_category.in_(["Tug", "Pilot"]),
                    Delay.total_duration_hours >= 1.0,
                )
            ).all()

            for delay, vcn in resource_delays:
                alert = self._create_or_get_alert(
                    rule=rule,
                    vessel_call_id=delay.vessel_call_id,
                    vcn=vcn,
                    title=f"Marine Service Shortage: {vcn} ({delay.canonical_category})",
                    description=(
                        f"Delay of {delay.total_duration_hours}h on {delay.movement_stage} due to "
                        f"{delay.delay_reason or delay.canonical_category}."
                    ),
                    linked_entity_type="canonical.delay",
                    linked_entity_id=str(delay.id),
                    evidence={
                        "reason": delay.delay_reason,
                        "category": delay.canonical_category,
                        "hours": delay.total_duration_hours,
                    },
                )
                if alert:
                    generated_alerts.append(alert)

        # 5. Evaluate RULE_BERTH_CONFLICT
        if "RULE_BERTH_CONFLICT" in active_rules:
            rule = active_rules["RULE_BERTH_CONFLICT"]
            berth_delays = self.db.execute(
                select(Delay, VesselCall.vcn)
                .join(VesselCall, Delay.vessel_call_id == VesselCall.id)
                .where(
                    Delay.canonical_category == "Berth Non-Availability",
                    Delay.total_duration_hours >= 1.0,
                )
            ).all()

            for delay, vcn in berth_delays:
                alert = self._create_or_get_alert(
                    rule=rule,
                    vessel_call_id=delay.vessel_call_id,
                    vcn=vcn,
                    title=f"Berth Unavailable: {vcn} ({delay.total_duration_hours}h)",
                    description=f"Berth non-availability delay of {delay.total_duration_hours}h reported for call {vcn}.",
                    linked_entity_type="canonical.delay",
                    linked_entity_id=str(delay.id),
                    evidence={"hours": delay.total_duration_hours, "movement": delay.movement_stage},
                )
                if alert:
                    generated_alerts.append(alert)

        self.db.commit()
        return self.list_alerts()

    def _create_or_get_alert(
        self,
        rule: AlertRule,
        vessel_call_id: uuid.UUID | None,
        vcn: str | None,
        title: str,
        description: str,
        linked_entity_type: str,
        linked_entity_id: str,
        evidence: dict[str, Any] | None,
    ) -> OperationalAlert | None:
        """Deduplicate active alerts: don't create if an unresolved one exists for same entity."""
        key = (rule.rule_code, linked_entity_type, linked_entity_id)
        existing = (
            self._open_alerts.get(key)
            if self._open_alerts is not None
            else self.db.execute(
                select(OperationalAlert).where(
                    OperationalAlert.rule_code == rule.rule_code,
                    OperationalAlert.linked_entity_type == linked_entity_type,
                    OperationalAlert.linked_entity_id == linked_entity_id,
                    OperationalAlert.status.in_(["NEW", "ACKNOWLEDGED"]),
                )
            ).scalar_one_or_none()
        )

        if existing:
            return existing

        alert = OperationalAlert(
            alert_rule_id=rule.id,
            rule_code=rule.rule_code,
            severity=rule.severity,
            title=title,
            description=description,
            vessel_call_id=vessel_call_id,
            vcn=vcn,
            status="NEW",
            linked_entity_type=linked_entity_type,
            linked_entity_id=linked_entity_id,
            evidence=evidence,
        )
        self.db.add(alert)
        if self._open_alerts is not None:
            self._open_alerts[key] = alert
        return alert

    def list_alerts(
        self,
        status: str | None = None,
        severity: str | None = None,
        rule_code: str | None = None,
        vcn: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List operational alerts with associated actions."""
        query = select(OperationalAlert)
        if status:
            query = query.where(OperationalAlert.status.ilike(status))
        if severity:
            query = query.where(OperationalAlert.severity.ilike(severity))
        if rule_code:
            query = query.where(OperationalAlert.rule_code == rule_code)
        if vcn:
            query = query.where(OperationalAlert.vcn == vcn)

        query = query.order_by(desc(OperationalAlert.created_at)).limit(limit)
        alerts = self.db.execute(query).scalars().all()
        alert_ids = [alert.id for alert in alerts]
        action_counts = {}
        if alert_ids:
            action_counts = dict(
                self.db.execute(
                    select(ActionItem.alert_id, func.count(ActionItem.id))
                    .where(ActionItem.alert_id.in_(alert_ids))
                    .group_by(ActionItem.alert_id)
                ).all()
            )

        results = []
        for a in alerts:
            results.append(
                {
                    "id": str(a.id),
                    "rule_code": a.rule_code,
                    "severity": a.severity,
                    "title": a.title,
                    "description": a.description,
                    "vessel_call_id": str(a.vessel_call_id) if a.vessel_call_id else None,
                    "vcn": a.vcn,
                    "status": a.status,
                    "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
                    "acknowledged_by": a.acknowledged_by,
                    "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
                    "resolved_by": a.resolved_by,
                    "resolution_notes": a.resolution_notes,
                    "linked_entity_type": a.linked_entity_type,
                    "linked_entity_id": a.linked_entity_id,
                    "evidence": a.evidence,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "actions_count": action_counts.get(a.id, 0),
                }
            )
        return results

    def acknowledge_alert(self, alert_id: uuid.UUID, actor: str = "operator") -> dict[str, Any]:
        """Acknowledge an operational alert."""
        alert = self.db.execute(select(OperationalAlert).where(OperationalAlert.id == alert_id)).scalar_one_or_none()
        if not alert:
            raise ValueError(f"Alert {alert_id} not found")

        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_at = datetime.now(UTC)
        alert.acknowledged_by = actor

        audit = AuditEvent(
            actor_id=actor,
            actor_email=f"{actor}@port.local",
            actor_role="operator",
            action="ACKNOWLEDGE_ALERT",
            resource_type="operational_alert",
            resource_id=str(alert.id),
            entity_name="analytics.operational_alert",
            entity_id=str(alert.id),
            details={"status": "ACKNOWLEDGED", "acknowledged_by": actor},
        )
        self.db.add(audit)
        self.db.commit()

        return {
            "id": str(alert.id),
            "status": alert.status,
            "acknowledged_at": alert.acknowledged_at.isoformat(),
            "acknowledged_by": alert.acknowledged_by,
        }

    def resolve_alert(self, alert_id: uuid.UUID, resolution_notes: str, actor: str = "operator") -> dict[str, Any]:
        """Resolve an operational alert with explanation notes."""
        alert = self.db.execute(select(OperationalAlert).where(OperationalAlert.id == alert_id)).scalar_one_or_none()
        if not alert:
            raise ValueError(f"Alert {alert_id} not found")

        alert.status = "RESOLVED"
        alert.resolved_at = datetime.now(UTC)
        alert.resolved_by = actor
        alert.resolution_notes = resolution_notes

        audit = AuditEvent(
            actor_id=actor,
            actor_email=f"{actor}@port.local",
            actor_role="operator",
            action="RESOLVE_ALERT",
            resource_type="operational_alert",
            resource_id=str(alert.id),
            entity_name="analytics.operational_alert",
            entity_id=str(alert.id),
            details={"status": "RESOLVED", "resolved_by": actor, "notes": resolution_notes},
        )
        self.db.add(audit)
        self.db.commit()

        return {
            "id": str(alert.id),
            "status": alert.status,
            "resolved_at": alert.resolved_at.isoformat(),
            "resolved_by": alert.resolved_by,
            "resolution_notes": alert.resolution_notes,
        }

    def create_action_item(
        self,
        title: str,
        description: str,
        assigned_to: str | None = None,
        due_date: datetime | None = None,
        priority: str = "MEDIUM",
        alert_id: uuid.UUID | None = None,
        vessel_call_id: uuid.UUID | None = None,
        created_by: str = "operator",
    ) -> dict[str, Any]:
        """Create an actionable remediation task."""
        action = ActionItem(
            alert_id=alert_id,
            vessel_call_id=vessel_call_id,
            title=title,
            description=description,
            assigned_to=assigned_to,
            due_date=due_date,
            priority=priority,
            status="OPEN",
            comments=[],
            created_by=created_by,
        )
        self.db.add(action)

        audit = AuditEvent(
            actor_id=created_by,
            actor_email=f"{created_by}@port.local",
            actor_role="operator",
            action="CREATE_ACTION_ITEM",
            resource_type="action_item",
            resource_id=str(action.id),
            entity_name="analytics.action_item",
            entity_id=str(action.id),
            details={"title": title, "assigned_to": assigned_to, "priority": priority},
        )
        self.db.add(audit)
        self.db.commit()

        return {
            "id": str(action.id),
            "title": action.title,
            "description": action.description,
            "status": action.status,
            "priority": action.priority,
            "assigned_to": action.assigned_to,
            "due_date": action.due_date.isoformat() if action.due_date else None,
            "created_by": action.created_by,
        }

    def update_action_item(
        self, action_id: uuid.UUID, status: str | None = None, comment: str | None = None, actor: str = "operator"
    ) -> dict[str, Any]:
        """Update action item status or add comment."""
        action = self.db.execute(select(ActionItem).where(ActionItem.id == action_id)).scalar_one_or_none()
        if not action:
            raise ValueError(f"Action item {action_id} not found")

        old_status = action.status
        if status:
            action.status = status

        comments = list(action.comments or [])
        if comment:
            comments.append(
                {
                    "author": actor,
                    "text": comment,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            action.comments = comments

        audit = AuditEvent(
            actor_id=actor,
            actor_email=f"{actor}@port.local",
            actor_role="operator",
            action="UPDATE_ACTION_ITEM",
            resource_type="action_item",
            resource_id=str(action.id),
            entity_name="analytics.action_item",
            entity_id=str(action.id),
            details={"old_status": old_status, "new_status": action.status, "comment_added": bool(comment)},
        )
        self.db.add(audit)
        self.db.commit()

        return {
            "id": str(action.id),
            "status": action.status,
            "priority": action.priority,
            "comments": action.comments,
        }

    def list_action_items(self, status: str | None = None) -> list[dict[str, Any]]:
        """List all action items."""
        query = select(ActionItem)
        if status:
            query = query.where(ActionItem.status.ilike(status))

        query = query.order_by(desc(ActionItem.created_at))
        rows = self.db.execute(query).scalars().all()

        return [
            {
                "id": str(r.id),
                "alert_id": str(r.alert_id) if r.alert_id else None,
                "vessel_call_id": str(r.vessel_call_id) if r.vessel_call_id else None,
                "title": r.title,
                "description": r.description,
                "assigned_to": r.assigned_to,
                "due_date": r.due_date.isoformat() if r.due_date else None,
                "status": r.status,
                "priority": r.priority,
                "comments": r.comments or [],
                "created_by": r.created_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
