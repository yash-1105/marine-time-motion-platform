"""Multi-dimensional bottleneck detection and scoring engine (spec §10.5, Phase 09).

Scoring components:
1. Duration: Mean or total duration
2. Frequency: Proportion of vessel calls affected
3. Variability: Coefficient of variation (stddev / mean)
4. Tail Risk: P90 / median ratio
5. Turnaround Contribution: Stage duration / total turnaround
6. Repeated Target Breach: Frequency of exceeding SLA / target threshold
7. Business Criticality: Governed impact score

HARD REQUIREMENT: Never label the longest stage alone as the bottleneck.
A long-but-stable stage (e.g. Berth Stay with low CV and zero breaches) must
rank LOWER than a shorter-but-highly-variable stage with high tail risk and frequent breaches.
"""
import math
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.models.analytics import BottleneckRecord, LeadTimeResult, LeadTimeDefinition
from apps.api.models.canonical import Delay, ServiceAssignment, ServiceExecution, ServiceRequest, VesselCall


class BottleneckEngine:
    def __init__(self, db: Session, tenant_id: str = "default-tenant"):
        self.db = db
        self.tenant_id = tenant_id

    def calculate_bottlenecks(
        self,
        weights: Optional[Dict[str, float]] = None,
        persist: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Calculate and rank operational bottlenecks across both process stages
        and operational resources.
        """
        default_weights = {
            "duration": 0.15,        # Deliberately non-dominant
            "frequency": 0.20,
            "variability": 0.20,
            "tail_risk": 0.20,
            "turnaround_contribution": 0.10,
            "repeated_target_breach": 0.15,
        }
        w = {**default_weights, **(weights or {})}
        total_w = sum(w.values())
        norm_w = {k: v / total_w for k, v in w.items()}

        candidates: List[Dict[str, Any]] = []

        # 1. Process Stages from LeadTimeResult
        stage_names = [
            ("Anchorage Wait", "PROCESS_BOTTLENECK", 2.0, 4.0),     # target 2.0h, biz_crit 4.0
            ("Inward Movement", "PROCESS_BOTTLENECK", 2.5, 3.5),
            ("Berth Stay", "PROCESS_BOTTLENECK", 48.0, 3.0),
            ("Cargo Working", "PROCESS_BOTTLENECK", 36.0, 3.5),
            ("Outward Movement", "PROCESS_BOTTLENECK", 2.0, 3.0),
        ]

        # Calculate mean turnaround for contribution calculation
        turnaround_results = self.db.execute(
            select(LeadTimeResult.duration_hours)
            .join(LeadTimeDefinition, LeadTimeResult.definition_id == LeadTimeDefinition.id)
            .where(
                LeadTimeDefinition.name == "Turnaround",
                LeadTimeResult.status == "AVAILABLE",
                LeadTimeResult.duration_hours.isnot(None),
            )
        ).scalars().all()
        mean_turnaround = (sum(turnaround_results) / len(turnaround_results)) if turnaround_results else 50.0

        for stage_name, b_type, target_hours, biz_crit in stage_names:
            results = self.db.execute(
                select(LeadTimeResult.duration_hours)
                .join(LeadTimeDefinition, LeadTimeResult.definition_id == LeadTimeDefinition.id)
                .where(
                    LeadTimeDefinition.name == stage_name,
                    LeadTimeResult.status == "AVAILABLE",
                    LeadTimeResult.duration_hours.isnot(None),
                )
            ).scalars().all()

            if not results:
                continue

            scores = self._compute_metrics_and_scores(
                values=results,
                target_threshold=target_hours,
                biz_crit=biz_crit,
                mean_turnaround=mean_turnaround,
                is_delay=False
            )
            scores["stage_or_resource"] = stage_name
            scores["bottleneck_type"] = b_type
            candidates.append(scores)

        # 2. Resource Dimensions from Delays & Service Execution
        # Pilotage Delay
        pilot_delays = self.db.execute(
            select(Delay.total_duration_hours).where(
                Delay.canonical_category == "Pilot",
                Delay.total_duration_hours > 0
            )
        ).scalars().all()

        if not pilot_delays:
            # Check services
            pilot_services = self.db.execute(
                select(ServiceExecution.served_time, ServiceAssignment.scheduled_time)
                .join(ServiceAssignment, ServiceExecution.service_assignment_id == ServiceAssignment.id)
                .join(ServiceRequest, ServiceAssignment.service_request_id == ServiceRequest.id)
                .where(ServiceRequest.service_type.ilike("%pilot%"))
            ).all()
            pilot_delays = [
                (serv - sched).total_seconds() / 3600.0
                for serv, sched in pilot_services
                if serv and sched and (serv - sched).total_seconds() > 0
            ]

        if pilot_delays:
            p_scores = self._compute_metrics_and_scores(
                values=pilot_delays,
                target_threshold=0.5,
                biz_crit=4.5,
                mean_turnaround=mean_turnaround,
                is_delay=True
            )
            p_scores["stage_or_resource"] = "Pilot Availability / Shortage"
            p_scores["bottleneck_type"] = "RESOURCE_BOTTLENECK"
            candidates.append(p_scores)

        # Tug Delay
        tug_delays = self.db.execute(
            select(Delay.total_duration_hours).where(
                Delay.canonical_category == "Tug",
                Delay.total_duration_hours > 0
            )
        ).scalars().all()

        if not tug_delays:
            tug_services = self.db.execute(
                select(ServiceExecution.served_time, ServiceAssignment.scheduled_time)
                .join(ServiceAssignment, ServiceExecution.service_assignment_id == ServiceAssignment.id)
                .join(ServiceRequest, ServiceAssignment.service_request_id == ServiceRequest.id)
                .where(ServiceRequest.service_type.ilike("%tug%"))
            ).all()
            tug_delays = [
                (serv - sched).total_seconds() / 3600.0
                for serv, sched in tug_services
                if serv and sched and (serv - sched).total_seconds() > 0
            ]

        if tug_delays:
            t_scores = self._compute_metrics_and_scores(
                values=tug_delays,
                target_threshold=0.5,
                biz_crit=4.0,
                mean_turnaround=mean_turnaround,
                is_delay=True
            )
            t_scores["stage_or_resource"] = "Tug Availability / Shortage"
            t_scores["bottleneck_type"] = "RESOURCE_BOTTLENECK"
            candidates.append(t_scores)

        # Berth Congestion Delay
        berth_delays = self.db.execute(
            select(Delay.total_duration_hours).where(
                Delay.canonical_category == "Berth Non-Availability",
                Delay.total_duration_hours > 0
            )
        ).scalars().all()

        if berth_delays:
            b_scores = self._compute_metrics_and_scores(
                values=berth_delays,
                target_threshold=1.0,
                biz_crit=4.5,
                mean_turnaround=mean_turnaround,
                is_delay=True
            )
            b_scores["stage_or_resource"] = "Berth Non-Availability / Congestion"
            b_scores["bottleneck_type"] = "RESOURCE_BOTTLENECK"
            candidates.append(b_scores)

        # 3. Calculate Overall Bottleneck Score using weights
        for c in candidates:
            # Composite score (0 - 100)
            overall = (
                norm_w["duration"] * c["duration_score"] +
                norm_w["frequency"] * c["frequency_score"] +
                norm_w["variability"] * c["variability_score"] +
                norm_w["tail_risk"] * c["tail_risk_score"] +
                norm_w["turnaround_contribution"] * c["turnaround_contribution_score"] +
                norm_w["repeated_target_breach"] * c["target_breach_score"]
            )
            c["overall_bottleneck_score"] = round(overall, 2)

        # 4. Rank candidates by overall_bottleneck_score DESC
        candidates.sort(key=lambda x: x["overall_bottleneck_score"], reverse=True)

        for idx, c in enumerate(candidates):
            c["rank"] = idx + 1

        # 5. Persist to analytics.bottleneck_record if requested
        if persist and candidates:
            self.db.execute(BottleneckRecord.__table__.delete())
            for c in candidates:
                rec = BottleneckRecord(
                    stage_or_resource=c["stage_or_resource"],
                    bottleneck_type=c["bottleneck_type"],
                    duration_score=c["duration_score"],
                    frequency_score=c["frequency_score"],
                    variability_score=c["variability_score"],
                    tail_risk_score=c["tail_risk_score"],
                    turnaround_contribution=c["turnaround_contribution"],
                    repeated_target_breach_rate=c["repeated_target_breach_rate"],
                    business_criticality_score=c["business_criticality_score"],
                    overall_bottleneck_score=c["overall_bottleneck_score"],
                    rank=c["rank"],
                    details={
                        "mean_hours": c["mean_hours"],
                        "median_hours": c["median_hours"],
                        "p90_hours": c["p90_hours"],
                        "cv": c["cv"],
                        "tail_risk_ratio": c["tail_risk_ratio"],
                        "target_breach_count": c["target_breach_count"],
                        "total_observations": c["total_observations"],
                    }
                )
                self.db.add(rec)
            self.db.commit()

        return candidates

    def _compute_metrics_and_scores(
        self,
        values: List[float],
        target_threshold: float,
        biz_crit: float,
        mean_turnaround: float,
        is_delay: bool
    ) -> Dict[str, Any]:
        """Compute statistics and normalized 0-100 scores for each component."""
        n = len(values)
        sorted_vals = sorted(values)
        mean_val = sum(values) / n
        median_val = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0

        p90_idx = int(math.ceil(0.90 * n)) - 1
        p90_idx = max(0, min(n - 1, p90_idx))
        p90_val = sorted_vals[p90_idx]

        variance = sum((x - mean_val) ** 2 for x in values) / (n - 1) if n > 1 else 0.0
        std_val = math.sqrt(variance)

        # 1. Variability (CV)
        cv = (std_val / mean_val) if mean_val > 0.0001 else 0.0
        # CV > 1.0 is high variability, normalize up to 2.0
        variability_score = min(100.0, round((cv / 1.5) * 100.0, 2))

        # 2. Tail Risk Ratio
        trr = (p90_val / median_val) if median_val > 0.0001 else (p90_val if p90_val > 1.0 else 1.0)
        # TRR > 3.0 indicates severe tail risk
        tail_risk_score = min(100.0, round(((trr - 1.0) / 2.5) * 100.0, 2)) if trr >= 1.0 else 0.0

        # 3. Frequency & Target Breaches
        breaches = [x for x in values if x > target_threshold]
        breach_rate = len(breaches) / n
        target_breach_score = round(breach_rate * 100.0, 2)

        # Vessel count total (72 base calls)
        total_calls = 72
        frequency_score = min(100.0, round((n / total_calls) * 100.0, 2))

        # 4. Turnaround Contribution
        contribution = (mean_val / mean_turnaround) if mean_turnaround > 0 else 0.0
        turnaround_contribution_score = min(100.0, round(contribution * 100.0, 2))

        # 5. Duration Score (normalized, non-dominant)
        # We normalize against 48 hours for process stages, 10 hours for delays
        max_bench = 10.0 if is_delay else 48.0
        duration_score = min(100.0, round((mean_val / max_bench) * 100.0, 2))

        return {
            "mean_hours": round(mean_val, 2),
            "median_hours": round(median_val, 2),
            "p90_hours": round(p90_val, 2),
            "std_hours": round(std_val, 2),
            "cv": round(cv, 3),
            "tail_risk_ratio": round(trr, 2),
            "turnaround_contribution": round(contribution, 3),
            "repeated_target_breach_rate": round(breach_rate, 3),
            "target_breach_count": len(breaches),
            "total_observations": n,
            "business_criticality_score": biz_crit,
            "duration_score": duration_score,
            "frequency_score": frequency_score,
            "variability_score": variability_score,
            "tail_risk_score": tail_risk_score,
            "turnaround_contribution_score": turnaround_contribution_score,
            "target_breach_score": target_breach_score,
        }
