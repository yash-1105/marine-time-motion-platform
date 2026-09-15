"""Copilot conversations, messages, and feedback (Phase 14A)."""
from alembic import op
import sqlalchemy as sa
revision = "i7j8k9l0m1n2"; down_revision = "h6i7j8k9l0m1"; branch_labels = None; depends_on = None
BASE = [sa.Column("id", sa.UUID(), primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False), sa.Column("created_by", sa.String()), sa.Column("updated_by", sa.String()), sa.Column("source_lineage_id", sa.String()), sa.Column("version", sa.Integer(), server_default="1", nullable=False)]
def upgrade():
 op.create_table("copilot_conversation", *BASE, sa.Column("conversation_id", sa.String(100), unique=True, nullable=False), sa.Column("tenant_id", sa.String(100), nullable=False), sa.Column("port_id", sa.String(100)), sa.Column("terminal_id", sa.String(100)), sa.Column("owner_id", sa.String(100), nullable=False), sa.Column("title", sa.String(255)), schema="analytics")
 op.create_table("copilot_message", *BASE, sa.Column("conversation_id", sa.UUID(), sa.ForeignKey("analytics.copilot_conversation.id", ondelete="CASCADE"), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("response_data", sa.JSON()), sa.Column("tool_audit", sa.JSON()), schema="analytics")
 op.create_table("copilot_feedback", *BASE, sa.Column("message_id", sa.UUID(), sa.ForeignKey("analytics.copilot_message.id", ondelete="CASCADE"), nullable=False), sa.Column("rating", sa.String(20), nullable=False), sa.Column("comment", sa.Text()), schema="analytics")
def downgrade():
 [op.drop_table(x, schema="analytics") for x in ["copilot_feedback", "copilot_message", "copilot_conversation"]]
