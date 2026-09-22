"""Index persisted governed scorecard snapshots for constant-size reads.

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
"""

from alembic import op


revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None


def upgrade():
    # Matches the persisted ALL-grain, unfiltered non-recalculation snapshot
    # predicate used by GET /kpis/scorecard.  It is additive and does not alter
    # historical KPI result rows or formula/version lineage.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_kpi_result_scorecard_snapshot_latest
        ON analytics.kpi_result (kpi_id, calculated_at DESC)
        WHERE period_start IS NULL
          AND period_end IS NULL
          AND grain = 'ALL'
          AND cohort_key = 'all'
          AND cohort_filters IS NULL
          AND is_recalculation = FALSE
    """)


def downgrade():
    op.drop_index(
        "ix_kpi_result_scorecard_snapshot_latest",
        table_name="kpi_result",
        schema="analytics",
    )
