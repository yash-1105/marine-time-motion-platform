from sqlalchemy import text
from sqlalchemy.orm import Session


def reset_tenant_dataset(db: Session, tenant_id: str, keep_batches: bool = False):
    """Purges all ingested/derived data for a tenant, returning it to a clean,
    no-dataset-loaded state. Used both to reset before loading a fresh dataset
    and to implement the user-facing "Remove Dataset" action."""

    if not keep_batches:
        # Staging has no database FK to raw.batch, so it must be removed while the
        # tenant batch identifiers still exist.  Deleting raw.batch first left
        # stale staging rows behind across dataset replacements and test reruns.
        db.execute(
            text(
                "DELETE FROM staging.record WHERE ingestion_batch_id IN (SELECT batch_id FROM raw.batch WHERE tenant_id = :t)"
            ),
            {"t": tenant_id},
        )
        db.execute(
            text(
                "DELETE FROM raw.record WHERE ingestion_batch_id IN (SELECT batch_id FROM raw.batch WHERE tenant_id = :t)"
            ),
            {"t": tenant_id},
        )
        db.execute(text("DELETE FROM raw.batch WHERE tenant_id = :t"), {"t": tenant_id})
        db.execute(text("DELETE FROM analytics.dashboard_snapshot WHERE tenant_id = :t"), {"t": tenant_id})

    db.execute(text("DELETE FROM identity.merge_decision"))
    db.execute(text("DELETE FROM identity.match_evidence"))
    db.execute(text("DELETE FROM identity.match_candidate"))

    # Phase 09 and Analytics data must be cleared before its FK-referenced canonical rows
    db.execute(text("DELETE FROM analytics.action_item"))
    db.execute(text("DELETE FROM analytics.operational_alert"))
    db.execute(text("DELETE FROM analytics.outlier_record"))
    db.execute(text("DELETE FROM analytics.bottleneck_record"))
    db.execute(text("DELETE FROM analytics.kpi_result WHERE tenant_id = :t"), {"t": tenant_id})
    db.execute(text("DELETE FROM analytics.statistical_aggregate WHERE tenant_id = :t"), {"t": tenant_id})
    db.execute(
        text(
            "DELETE FROM analytics.lead_time_result WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )

    # Canonical delay allocations and cargo operations
    db.execute(
        text(
            "DELETE FROM canonical.delay_allocation WHERE delay_id IN (SELECT id FROM canonical.delay WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t))"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM canonical.cargo_operation WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )

    # Journey reconstruction data must be cleared before its FK-referenced canonical/quality rows.
    db.execute(
        text(
            "DELETE FROM journey.reconstruction_history WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM journey.journey_narrative WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM journey.observation_correction WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM journey.canonical_observation WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM journey.handover WHERE from_stage_occurrence_id IN (SELECT id FROM journey.stage_occurrence WHERE journey_instance_id IN (SELECT id FROM journey.journey_instance WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)))"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM journey.stage_occurrence WHERE journey_instance_id IN (SELECT id FROM journey.journey_instance WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t))"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM journey.journey_instance WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )

    db.execute(
        text(
            "DELETE FROM quality.quality_issue WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM canonical.event_occurrence WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM canonical.service_execution WHERE service_assignment_id IN (SELECT id FROM canonical.service_assignment WHERE service_request_id IN (SELECT id FROM canonical.service_request WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)))"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM canonical.service_assignment WHERE service_request_id IN (SELECT id FROM canonical.service_request WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t))"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM canonical.service_request WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )
    db.execute(
        text(
            "DELETE FROM canonical.delay WHERE vessel_call_id IN (SELECT id FROM canonical.vessel_call WHERE tenant_id = :t)"
        ),
        {"t": tenant_id},
    )
    # Clear self-referential foreign key before deletion
    db.execute(text("UPDATE canonical.vessel_call SET merged_into_id = NULL WHERE tenant_id = :t"), {"t": tenant_id})
    db.execute(text("DELETE FROM canonical.vessel_call WHERE tenant_id = :t"), {"t": tenant_id})

    db.commit()
