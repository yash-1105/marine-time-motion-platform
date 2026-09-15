"""Add dashboard_snapshot table and is_active flag to batch

Revision ID: a2b3c4d5e6f7
Revises: f4a5b6c7d8e9
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add is_active column to raw.batch
    op.add_column(
        'batch',
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        schema='raw'
    )

    # 2. Create analytics.dashboard_snapshot table
    op.create_table(
        'dashboard_snapshot',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.String(length=100), nullable=False),
        sa.Column('batch_id', sa.String(length=100), nullable=False),
        sa.Column('file_checksum', sa.String(length=64), nullable=False),
        sa.Column('filters_hash', sa.String(length=64), server_default='unfiltered', nullable=False),
        sa.Column('snapshot_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='analytics'
    )
    op.create_index(
        'ix_dashboard_snapshot_tenant_active',
        'dashboard_snapshot',
        ['tenant_id', 'is_active'],
        schema='analytics'
    )
    op.create_index(
        'ix_dashboard_snapshot_batch_id',
        'dashboard_snapshot',
        ['batch_id'],
        schema='analytics'
    )


def downgrade() -> None:
    op.drop_index('ix_dashboard_snapshot_batch_id', table_name='dashboard_snapshot', schema='analytics')
    op.drop_index('ix_dashboard_snapshot_tenant_active', table_name='dashboard_snapshot', schema='analytics')
    op.drop_table('dashboard_snapshot', schema='analytics')
    op.drop_column('batch', 'is_active', schema='raw')
