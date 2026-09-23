"""Pipeline Runner: executes end-to-end analytical pipeline once and persists results (Phase 12 / Data Persistence)."""

import json
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from apps.api.services.alerts.engine import AlertEngine
from apps.api.services.analytics.engine import AnalyticsEngine
from apps.api.services.bottlenecks.engine import BottleneckEngine
from apps.api.services.dashboard.executive import ExecutiveDashboardService
from apps.api.services.identity.engine import IdentityEngine
from apps.api.services.journey.reconstructor import JourneyReconstructionEngine
from apps.api.services.kpi.engine import KPIEngine
from apps.api.services.outliers.engine import OutlierEngine
from apps.api.services.quality.engine import DataQualityEngine


def run_full_analytics_pipeline(
    db: Session,
    tenant_id: str,
    batch_id: str,
    file_checksum: str,
) -> dict[str, Any]:
    """
    Executes the analytical pipeline once and persists results:
    1. Quality Engine (rule evaluation & issue generation)
    2. Identity Engine (deterministic & probabilistic call deduplication)
    3. Journey Reconstruction Engine (temporal stage assembly)
    4. Analytics Engine (lead time durations & statistical aggregates)
    5. Governed KPI Engine (all 55 registered KPIs)
    6. Outlier Engine (Tukey/IQR outlier detection & persistence)
    7. Bottleneck Engine (multi-factor ANOVA operational bottlenecks)
    8. Operational Alert Engine (threshold breach evaluation)
    9. Executive Dashboard Service (computes and persists dashboard snapshot to PostgreSQL)
    """

    def run_stage(name: str, callback):
        started = perf_counter()
        result = callback()
        # Worker stdout is collected by Railway; structured timing makes a real
        # processing bottleneck diagnosable without changing metric semantics.
        print(
            json.dumps(
                {
                    "event": "ingestion_analytics_stage_completed",
                    "batch_id": batch_id,
                    "tenant_id": tenant_id,
                    "stage": name,
                    "elapsed_ms": round((perf_counter() - started) * 1000, 2),
                }
            )
        )
        return result

    # 1. Quality Engine
    quality_engine = DataQualityEngine(db, ingestion_batch_id=batch_id)
    run_stage("quality", quality_engine.run_all)

    # 2. Identity Resolution
    id_engine = IdentityEngine(db, tenant_id=tenant_id)
    run_stage("identity", id_engine.auto_merge_candidates)

    # 3. Journey Reconstruction
    journey_engine = JourneyReconstructionEngine(db, tenant_id=tenant_id)
    run_stage("journey", journey_engine.reconstruct_all)

    # 4. Analytics Engine
    analytics_engine = AnalyticsEngine(db, tenant_id=tenant_id)
    run_stage("metric_calculation", analytics_engine.compute_all_metrics)
    run_stage("statistics", analytics_engine.compute_all_statistics)

    # 5. KPI Engine
    kpi_engine = KPIEngine(db, tenant_id=tenant_id)
    run_stage("kpi_calculation", kpi_engine.calculate_all_kpis)

    # 6. Outlier Engine
    outlier_engine = OutlierEngine(db, tenant_id=tenant_id)
    run_stage("outliers", lambda: outlier_engine.detect_all_outliers(persist=True))

    # 7. Bottleneck Engine
    bottleneck_engine = BottleneckEngine(db, tenant_id=tenant_id)
    run_stage("bottlenecks", lambda: bottleneck_engine.calculate_bottlenecks(persist=True))

    # 8. Alert Engine
    alert_engine = AlertEngine(db, tenant_id=tenant_id)
    run_stage("alerts", alert_engine.evaluate_rules)

    # 9. Executive Dashboard Snapshot Persistence
    dash_svc = ExecutiveDashboardService(db, tenant_id=tenant_id)
    snapshot = run_stage(
        "dashboard_snapshot",
        lambda: dash_svc.compute_and_persist_snapshot(batch_id=batch_id, file_checksum=file_checksum),
    )

    return snapshot
