"""Retire legacy unnumbered KPI definitions while preserving provenance.

Revision ID: m1n2o3p4q5r6
Revises: l0m1n2o3p4q5
"""

from alembic import op
import sqlalchemy as sa


revision = "m1n2o3p4q5r6"
down_revision = "l0m1n2o3p4q5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("kpi", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), schema="analytics")
    op.add_column("kpi", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True), schema="analytics")
    op.add_column("kpi", sa.Column("retirement_reason", sa.Text(), nullable=True), schema="analytics")
    op.add_column("kpi", sa.Column("governed_kpi_id", sa.UUID(), nullable=True), schema="analytics")
    op.create_foreign_key("fk_kpi_governed_kpi_id", "kpi", "kpi", ["governed_kpi_id"], ["id"], source_schema="analytics", referent_schema="analytics", ondelete="SET NULL")
    op.create_index("ix_analytics_kpi_active_number", "kpi", ["is_active", "kpi_number"], schema="analytics")

    # Code-bearing rows are the authoritative FRD registry. Unnumbered rows are
    # retained for historical KPIResult/audit linkage but cannot enter new
    # scorecards or calculations.
    op.execute("""
        UPDATE analytics.kpi
           SET is_active = FALSE,
               retired_at = COALESCE(retired_at, now()),
               retirement_reason = COALESCE(retirement_reason, 'Pre-governance KPI definition; retained for historical lineage')
         WHERE code IS NULL
    """)
    # Only link names whose semantic equivalence is explicit; generic KPI_# rows
    # are intentionally left unlinked rather than guessing their meaning.
    op.execute("""
        UPDATE analytics.kpi legacy
           SET governed_kpi_id = governed.id
          FROM analytics.kpi governed
         WHERE legacy.code IS NULL
           AND governed.code IS NOT NULL
           AND ((legacy.name = 'Anchorage Wait' AND governed.code = 'KPI-03')
             OR (legacy.name = 'Berth Stay' AND governed.code = 'KPI-15')
             OR (legacy.name = 'Turnaround' AND governed.code = 'KPI-41'))
    """)
    op.alter_column("kpi", "is_active", server_default=None, schema="analytics")


def downgrade():
    # Provenance rows were never removed. Downgrade only removes retirement
    # metadata after the application has been rolled back.
    op.drop_index("ix_analytics_kpi_active_number", table_name="kpi", schema="analytics")
    op.drop_constraint("fk_kpi_governed_kpi_id", "kpi", schema="analytics", type_="foreignkey")
    op.drop_column("kpi", "governed_kpi_id", schema="analytics")
    op.drop_column("kpi", "retirement_reason", schema="analytics")
    op.drop_column("kpi", "retired_at", schema="analytics")
    op.drop_column("kpi", "is_active", schema="analytics")
