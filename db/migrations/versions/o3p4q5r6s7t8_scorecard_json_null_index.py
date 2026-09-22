"""Match the scorecard snapshot index to JSON-null persistence semantics.

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
"""

from alembic import op


revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index(
        "ix_kpi_result_scorecard_snapshot_latest",
        table_name="kpi_result",
        schema="analytics",
    )
    # JSON columns persist Python None as JSON `null` in this schema.  Retain
    # the SQL-NULL arm for legacy/manual rows while matching current snapshots.
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


def downgrade():
    op.drop_index(
        "ix_kpi_result_scorecard_snapshot_latest",
        table_name="kpi_result",
        schema="analytics",
    )
    op.execute("""
        CREATE INDEX ix_kpi_result_scorecard_snapshot_latest
        ON analytics.kpi_result (kpi_id, calculated_at DESC)
        WHERE period_start IS NULL
          AND period_end IS NULL
          AND grain = 'ALL'
          AND cohort_key = 'all'
          AND cohort_filters IS NULL
          AND is_recalculation = FALSE
    """)
