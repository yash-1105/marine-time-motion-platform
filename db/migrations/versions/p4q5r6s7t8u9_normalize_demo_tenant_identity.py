"""Normalize the legacy governed-demo tenant identity.

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8

The authenticated development/demo principal has always been seeded as
``tenant-synthetic-01``. Earlier ingestion routers rewrote that identity to
``synthetic-tenant`` before persistence. This migration repairs only that known
legacy boundary error and retains all primary keys, source records, batch IDs,
checksums, and downstream foreign-key lineage.
"""

import sqlalchemy as sa
from alembic import op


revision = "p4q5r6s7t8u9"
down_revision = "o3p4q5r6s7t8"
branch_labels = None
depends_on = None

LEGACY_TENANT = "synthetic-tenant"
CANONICAL_TENANT = "tenant-synthetic-01"


def upgrade():
    # Refuse an ambiguous merge if both identities already own datasets. A
    # mixed installation needs a reviewed, dataset-by-dataset reconciliation.
    op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM raw.batch WHERE tenant_id = '{LEGACY_TENANT}'
          ) AND EXISTS (
            SELECT 1 FROM raw.batch WHERE tenant_id = '{CANONICAL_TENANT}'
          ) THEN
            RAISE EXCEPTION 'Both legacy and canonical demo tenants own ingestion batches; manual reconciliation required';
          END IF;
        END $$;
    """)

    for schema, table in (
        ("raw", "batch"),
        ("canonical", "vessel_call"),
        ("analytics", "dashboard_snapshot"),
        ("analytics", "report_run"),
        ("analytics", "report_schedule"),
        ("analytics", "copilot_conversation"),
    ):
        op.execute(
            f"UPDATE {schema}.{table} SET tenant_id = '{CANONICAL_TENANT}' "
            f"WHERE tenant_id = '{LEGACY_TENANT}'"
        )

    # Aggregate rows historically lacked tenant ownership. They can be safely
    # attributed only when there is one successful dataset tenant. Failed test
    # batches and unrelated hand-built vessel rows do not own persisted cohorts.
    op.execute("""
        DO $$
        BEGIN
          IF (SELECT count(DISTINCT tenant_id) FROM raw.batch WHERE status IN ('COMMITTED', 'PROCESSING')) > 1
             AND (EXISTS (SELECT 1 FROM analytics.statistical_aggregate)
                  OR EXISTS (SELECT 1 FROM analytics.kpi_result WHERE vessel_call_id IS NULL)) THEN
            RAISE EXCEPTION 'Unscoped aggregate history spans multiple tenants; reviewed attribution required';
          END IF;
        END $$;
    """)

    op.add_column("statistical_aggregate", sa.Column("tenant_id", sa.String(length=100), nullable=True), schema="analytics")
    op.add_column("kpi_result", sa.Column("tenant_id", sa.String(length=100), nullable=True), schema="analytics")
    op.execute(f"""
        UPDATE analytics.statistical_aggregate
        SET tenant_id = COALESCE(
          (SELECT min(tenant_id) FROM raw.batch WHERE status IN ('COMMITTED', 'PROCESSING')),
          (SELECT min(tenant_id) FROM canonical.vessel_call),
          '{CANONICAL_TENANT}'
        )
        WHERE tenant_id IS NULL
    """)
    op.execute(f"""
        UPDATE analytics.kpi_result kr
        SET tenant_id = COALESCE(
          (SELECT vc.tenant_id FROM canonical.vessel_call vc WHERE vc.id = kr.vessel_call_id),
          (SELECT min(tenant_id) FROM raw.batch WHERE status IN ('COMMITTED', 'PROCESSING')),
          (SELECT min(tenant_id) FROM canonical.vessel_call),
          '{CANONICAL_TENANT}'
        )
        WHERE tenant_id IS NULL
    """)
    op.alter_column("statistical_aggregate", "tenant_id", nullable=False, schema="analytics")
    op.alter_column("kpi_result", "tenant_id", nullable=False, schema="analytics")
    op.create_index("ix_statistical_aggregate_tenant_id", "statistical_aggregate", ["tenant_id"], schema="analytics")
    op.create_index("ix_kpi_result_tenant_id", "kpi_result", ["tenant_id"], schema="analytics")
    op.drop_constraint("uq_stat_agg_def_cohort", "statistical_aggregate", schema="analytics", type_="unique")
    op.create_unique_constraint(
        "uq_stat_agg_tenant_def_cohort",
        "statistical_aggregate",
        ["tenant_id", "definition_id", "cohort_key"],
        schema="analytics",
    )
    op.drop_index("ix_kpi_result_scorecard_snapshot_latest", table_name="kpi_result", schema="analytics")
    op.execute("""
        CREATE INDEX ix_kpi_result_scorecard_snapshot_latest
        ON analytics.kpi_result (tenant_id, kpi_id, calculated_at DESC)
        WHERE period_start IS NULL
          AND period_end IS NULL
          AND grain = 'ALL'
          AND cohort_key = 'all'
          AND (cohort_filters IS NULL OR cohort_filters::text = 'null')
          AND is_recalculation = FALSE
    """)


def downgrade():
    # Schema rollback is supported, but tenant values are intentionally not
    # renamed back to the invalid alias. No business or lineage rows are deleted.
    op.drop_index("ix_kpi_result_scorecard_snapshot_latest", table_name="kpi_result", schema="analytics")
    op.execute("""
        CREATE INDEX ix_kpi_result_scorecard_snapshot_latest
        ON analytics.kpi_result (kpi_id, calculated_at DESC)
        WHERE period_start IS NULL
          AND period_end IS NULL
          AND grain = 'ALL'
          AND cohort_key = 'all'
          AND (cohort_filters IS NULL OR cohort_filters::text = 'null')
          AND is_recalculation = FALSE
    """)
    op.drop_constraint("uq_stat_agg_tenant_def_cohort", "statistical_aggregate", schema="analytics", type_="unique")
    op.create_unique_constraint(
        "uq_stat_agg_def_cohort",
        "statistical_aggregate",
        ["definition_id", "cohort_key"],
        schema="analytics",
    )
    op.drop_index("ix_kpi_result_tenant_id", table_name="kpi_result", schema="analytics")
    op.drop_index("ix_statistical_aggregate_tenant_id", table_name="statistical_aggregate", schema="analytics")
    op.drop_column("kpi_result", "tenant_id", schema="analytics")
    op.drop_column("statistical_aggregate", "tenant_id", schema="analytics")
