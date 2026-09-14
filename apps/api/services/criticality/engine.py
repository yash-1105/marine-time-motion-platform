"""Operational criticality scoring engine (spec §10.8, Phase 09).

Calculates:
1. Duration score (1.0 to 5.0)
2. Variability score (1.0 to 5.0)
3. Tail-Risk score (1.0 to 5.0)
4. Overall score (arithmetic mean of the three by default, or governed weights)
5. Criticality Band:
   - 1.0 - 1.9: Low
   - 2.0 - 2.9: Moderate
   - 3.0 - 3.9: High
   - 4.0 - 5.0: Critical

HARD RULE: Always display the three component scores alongside the overall score.
No black-box score anywhere in the API response or UI.
"""
import math
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.analytics import LeadTimeDefinition, LeadTimeResult


class CriticalityEngine:
    def __init__(self, db: Session, tenant_id: str = "default-tenant"):
        self.db = db
        self.tenant_id = tenant_id

    def compute_component_scores(
        self,
        duration_hours: float,
        cv: float,
        tail_risk_ratio: float,
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Compute the 3 component scores (1.0 to 5.0), overall score, and band.
        Exposes all component scores transparently.
        """
        # 1. Duration Score (1 to 5)
        if duration_hours < 2.0:
            dur_score = 1.0
        elif duration_hours < 6.0:
            dur_score = 2.0
        elif duration_hours < 18.0:
            dur_score = 3.0
        elif duration_hours < 36.0:
            dur_score = 4.0
        else:
            dur_score = 5.0

        # 2. Variability Score (1 to 5 based on CV)
        if cv < 0.20:
            var_score = 1.0
        elif cv < 0.50:
            var_score = 2.0
        elif cv < 0.80:
            var_score = 3.0
        elif cv < 1.20:
            var_score = 4.0
        else:
            var_score = 5.0

        # 3. Tail-Risk Score (1 to 5 based on P90 / Median ratio)
        if tail_risk_ratio < 1.30:
            tail_score = 1.0
        elif tail_risk_ratio < 1.80:
            tail_score = 2.0
        elif tail_risk_ratio < 2.50:
            tail_score = 3.0
        elif tail_risk_ratio < 3.50:
            tail_score = 4.0
        else:
            tail_score = 5.0

        # Governed weights or arithmetic mean
        if weights:
            w_dur = weights.get("duration", 1.0 / 3.0)
            w_var = weights.get("variability", 1.0 / 3.0)
            w_tail = weights.get("tail_risk", 1.0 / 3.0)
            tot_w = w_dur + w_var + w_tail
            overall = (w_dur * dur_score + w_var * var_score + w_tail * tail_score) / tot_w
        else:
            overall = (dur_score + var_score + tail_score) / 3.0

        overall = round(overall, 2)

        # Criticality Band
        if overall < 2.0:
            band = "LOW"
        elif overall < 3.0:
            band = "MODERATE"
        elif overall < 4.0:
            band = "HIGH"
        else:
            band = "CRITICAL"

        return {
            "duration_score": dur_score,
            "variability_score": var_score,
            "tail_risk_score": tail_score,
            "overall_score": overall,
            "band": band,
            "inputs": {
                "duration_hours": round(duration_hours, 2),
                "cv": round(cv, 3),
                "tail_risk_ratio": round(tail_risk_ratio, 2),
            },
        }

    def evaluate_all_stages(self) -> List[Dict[str, Any]]:
        """Evaluate operational criticality for all governed lead times."""
        definitions = self.db.execute(select(LeadTimeDefinition)).scalars().all()
        evaluations: List[Dict[str, Any]] = []

        for defn in definitions:
            results = self.db.execute(
                select(LeadTimeResult.duration_hours)
                .where(
                    LeadTimeResult.definition_id == defn.id,
                    LeadTimeResult.status == "AVAILABLE",
                    LeadTimeResult.duration_hours.isnot(None),
                )
            ).scalars().all()

            if not results:
                continue

            n = len(results)
            sorted_vals = sorted(results)
            mean_val = sum(results) / n
            med_val = sorted_vals[n // 2]
            p90_idx = max(0, min(n - 1, int(math.ceil(0.90 * n)) - 1))
            p90_val = sorted_vals[p90_idx]

            variance = sum((x - mean_val) ** 2 for x in results) / (n - 1) if n > 1 else 0.0
            std_val = math.sqrt(variance)
            cv = (std_val / mean_val) if mean_val > 0 else 0.0
            trr = (p90_val / med_val) if med_val > 0.0001 else 1.0

            crit = self.compute_component_scores(mean_val, cv, trr)
            evaluations.append({
                "stage_name": defn.name,
                "definition_id": str(defn.id),
                "duration_score": crit["duration_score"],
                "variability_score": crit["variability_score"],
                "tail_risk_score": crit["tail_risk_score"],
                "overall_score": crit["overall_score"],
                "band": crit["band"],
                "observations": n,
                "metrics": {
                    "mean_hours": round(mean_val, 2),
                    "median_hours": round(med_val, 2),
                    "p90_hours": round(p90_val, 2),
                    "cv": round(cv, 3),
                    "tail_risk_ratio": round(trr, 2),
                },
            })

        evaluations.sort(key=lambda x: x["overall_score"], reverse=True)
        return evaluations
