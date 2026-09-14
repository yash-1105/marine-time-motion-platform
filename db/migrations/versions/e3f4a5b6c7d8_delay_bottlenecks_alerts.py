"""Delay analysis, bottlenecks, outliers, criticality, and operational alerts (Phase 09)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-14 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, Sequence[str], None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend canonical.delay
    op.add_column('delay', sa.Column('source_delay_id', sa.String(length=50), nullable=True), schema='canonical')
    op.add_column('delay', sa.Column('scheduled_time', sa.DateTime(timezone=True), nullable=True), schema='canonical')
    op.add_column('delay', sa.Column('served_time', sa.DateTime(timezone=True), nullable=True), schema='canonical')
    op.add_column('delay', sa.Column('delay_hours', sa.Float(), nullable=True), schema='canonical')
    op.add_column('delay', sa.Column('recalculated_delay_hours', sa.Float(), nullable=True), schema='canonical')
    op.add_column('delay', sa.Column('delay_reason', sa.String(length=255), nullable=True), schema='canonical')
    op.add_column('delay', sa.Column('source_category', sa.String(length=100), nullable=True), schema='canonical')
    op.add_column('delay', sa.Column('canonical_category', sa.String(length=100), nullable=True), schema='canonical')
    op.add_column('delay', sa.Column('cause_status', sa.String(length=50), server_default='Confirmed', nullable=False), schema='canonical')
    op.add_column('delay', sa.Column('confidence', sa.String(length=50), server_default='High', nullable=True), schema='canonical')
    op.add_column('delay', sa.Column('resolution_status', sa.String(length=50), server_default='Open', nullable=False), schema='canonical')
    op.add_column('delay', sa.Column('has_reconciliation_mismatch', sa.Boolean(), server_default=sa.text('false'), nullable=False), schema='canonical')
    op.add_column('delay', sa.Column('reconciliation_notes', sa.Text(), nullable=True), schema='canonical')
    op.add_column('delay', sa.Column('requires_reason_review', sa.Boolean(), server_default=sa.text('false'), nullable=False), schema='canonical')

    # 2. Extend canonical.delay_allocation
    op.add_column('delay_allocation', sa.Column('canonical_category', sa.String(length=100), nullable=True), schema='canonical')
    op.add_column('delay_allocation', sa.Column('reason', sa.String(length=255), nullable=True), schema='canonical')
    op.add_column('delay_allocation', sa.Column('confidence', sa.Float(), nullable=True), schema='canonical')
    op.add_column('delay_allocation', sa.Column('human_review_state', sa.String(length=50), server_default='APPROVED', nullable=False), schema='canonical')

    # 3. Create analytics.bottleneck_record
    op.create_table(
        'bottleneck_record',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('stage_or_resource', sa.String(length=100), nullable=False),
        sa.Column('bottleneck_type', sa.String(length=50), nullable=False),
        sa.Column('duration_score', sa.Float(), nullable=False),
        sa.Column('frequency_score', sa.Float(), nullable=False),
        sa.Column('variability_score', sa.Float(), nullable=False),
        sa.Column('tail_risk_score', sa.Float(), nullable=False),
        sa.Column('turnaround_contribution', sa.Float(), nullable=False),
        sa.Column('repeated_target_breach_rate', sa.Float(), nullable=False),
        sa.Column('business_criticality_score', sa.Float(), nullable=False),
        sa.Column('overall_bottleneck_score', sa.Float(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='analytics'
    )

    # 4. Create analytics.outlier_record
    op.create_table(
        'outlier_record',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('vessel_call_id', sa.UUID(), nullable=False),
        sa.Column('vcn', sa.String(length=100), nullable=False),
        sa.Column('outlier_type', sa.String(length=100), nullable=False),
        sa.Column('metric_name', sa.String(length=100), nullable=False),
        sa.Column('observed_value', sa.Float(), nullable=False),
        sa.Column('benchmark_or_p90', sa.Float(), nullable=True),
        sa.Column('divergence', sa.Float(), nullable=True),
        sa.Column('is_excluded_from_kpi', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('exclusion_rationale', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(length=20), server_default='MEDIUM', nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.ForeignKeyConstraint(['vessel_call_id'], ['canonical.vessel_call.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='analytics'
    )

    # 5. Create analytics.alert_rule
    op.create_table(
        'alert_rule',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('rule_code', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('threshold_config', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('suppression_window_minutes', sa.Integer(), server_default=sa.text('60'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rule_code'),
        schema='analytics'
    )

    # 6. Create analytics.operational_alert
    op.create_table(
        'operational_alert',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('alert_rule_id', sa.UUID(), nullable=True),
        sa.Column('rule_code', sa.String(length=100), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('vessel_call_id', sa.UUID(), nullable=True),
        sa.Column('vcn', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='NEW', nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.String(length=100), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.String(length=100), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('linked_entity_type', sa.String(length=100), nullable=True),
        sa.Column('linked_entity_id', sa.String(length=100), nullable=True),
        sa.Column('evidence', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.ForeignKeyConstraint(['alert_rule_id'], ['analytics.alert_rule.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['vessel_call_id'], ['canonical.vessel_call.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='analytics'
    )

    # 7. Create analytics.action_item
    op.create_table(
        'action_item',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('alert_id', sa.UUID(), nullable=True),
        sa.Column('vessel_call_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('assigned_to', sa.String(length=100), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=50), server_default='OPEN', nullable=False),
        sa.Column('priority', sa.String(length=20), server_default='MEDIUM', nullable=False),
        sa.Column('comments', sa.JSON(), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.ForeignKeyConstraint(['alert_id'], ['analytics.operational_alert.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['vessel_call_id'], ['canonical.vessel_call.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='analytics'
    )


def downgrade() -> None:
    op.drop_table('action_item', schema='analytics')
    op.drop_table('operational_alert', schema='analytics')
    op.drop_table('alert_rule', schema='analytics')
    op.drop_table('outlier_record', schema='analytics')
    op.drop_table('bottleneck_record', schema='analytics')

    op.drop_column('delay_allocation', 'human_review_state', schema='canonical')
    op.drop_column('delay_allocation', 'confidence', schema='canonical')
    op.drop_column('delay_allocation', 'reason', schema='canonical')
    op.drop_column('delay_allocation', 'canonical_category', schema='canonical')

    op.drop_column('delay', 'requires_reason_review', schema='canonical')
    op.drop_column('delay', 'reconciliation_notes', schema='canonical')
    op.drop_column('delay', 'has_reconciliation_mismatch', schema='canonical')
    op.drop_column('delay', 'resolution_status', schema='canonical')
    op.drop_column('delay', 'confidence', schema='canonical')
    op.drop_column('delay', 'cause_status', schema='canonical')
    op.drop_column('delay', 'canonical_category', schema='canonical')
    op.drop_column('delay', 'source_category', schema='canonical')
    op.drop_column('delay', 'delay_reason', schema='canonical')
    op.drop_column('delay', 'recalculated_delay_hours', schema='canonical')
    op.drop_column('delay', 'delay_hours', schema='canonical')
    op.drop_column('delay', 'served_time', schema='canonical')
    op.drop_column('delay', 'scheduled_time', schema='canonical')
    op.drop_column('delay', 'source_delay_id', schema='canonical')
