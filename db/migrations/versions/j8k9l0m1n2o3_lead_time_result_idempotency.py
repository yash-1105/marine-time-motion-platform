"""Enforce one governed lead-time result per call and definition."""
from alembic import op
import sqlalchemy as sa
revision = "j8k9l0m1n2o3"
down_revision = "i7j8k9l0m1n2"
branch_labels = None
depends_on = None
def upgrade():
    # Retain the newest recalculation before enforcing the governed 1:1 key.
    op.execute("""
      DELETE FROM analytics.lead_time_result a
      USING analytics.lead_time_result b
      WHERE a.vessel_call_id = b.vessel_call_id AND a.definition_id = b.definition_id
        AND (a.calculated_at, a.created_at, a.id) < (b.calculated_at, b.created_at, b.id)
    """)
    op.create_unique_constraint("uq_lead_time_result_call_definition", "lead_time_result", ["vessel_call_id", "definition_id"], schema="analytics")
def downgrade():
    op.drop_constraint("uq_lead_time_result_call_definition", "lead_time_result", schema="analytics", type_="unique")
