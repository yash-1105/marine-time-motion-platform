"""Validation harness oracle summary and run history (Phase 10)

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-14 22:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, Sequence[str], None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create testkit.validation_summary table
    op.create_table(
        'validation_summary',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('metric_name', sa.String(length=255), nullable=False),
        sa.Column('expected_value', sa.String(length=255), nullable=False),
        sa.Column('interpretation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='testkit',
    )

    # 2. Create testkit.validation_run_history table
    op.create_table(
        'validation_run_history',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('execution_time_seconds', sa.Float(), nullable=False),
        sa.Column('app_version', sa.String(length=50), nullable=False),
        sa.Column('rule_version', sa.String(length=50), nullable=False),
        sa.Column('formula_version', sa.String(length=50), nullable=False),
        sa.Column('dataset_checksum', sa.String(length=64), nullable=False),
        sa.Column('overall_status', sa.String(length=50), nullable=False),
        sa.Column('report_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='testkit',
    )


def downgrade() -> None:
    op.drop_table('validation_run_history', schema='testkit')
    op.drop_table('validation_summary', schema='testkit')
