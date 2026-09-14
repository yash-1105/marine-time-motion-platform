"""Identity resolution and merge models

Revision ID: a1b2c3d4e5f6
Revises: 9f5f942e63de
Create Date: 2026-09-14 16:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '9f5f942e63de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update canonical.vessel_call with merge tracking
    op.add_column(
        'vessel_call',
        sa.Column('is_merged', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        schema='canonical'
    )
    op.add_column(
        'vessel_call',
        sa.Column('merged_into_id', sa.UUID(), sa.ForeignKey('canonical.vessel_call.id', ondelete='SET NULL'), nullable=True),
        schema='canonical'
    )
    op.create_index(
        op.f('ix_canonical_vessel_call_is_merged'),
        'vessel_call',
        ['is_merged'],
        schema='canonical'
    )

    # 2. Update identity.match_candidate with match type & conflict tracking
    op.add_column(
        'match_candidate',
        sa.Column('match_type', sa.String(), nullable=True),
        schema='identity'
    )
    op.add_column(
        'match_candidate',
        sa.Column('conflict_detected', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        schema='identity'
    )
    op.add_column(
        'match_candidate',
        sa.Column('conflict_reasons', sa.JSON(), nullable=True),
        schema='identity'
    )

    # 3. Update identity.merge_decision with snapshots and provenance
    op.add_column(
        'merge_decision',
        sa.Column('survivor_record_id', sa.String(), nullable=True),
        schema='identity'
    )
    op.add_column(
        'merge_decision',
        sa.Column('merged_record_id', sa.String(), nullable=True),
        schema='identity'
    )
    op.add_column(
        'merge_decision',
        sa.Column('evidence_snapshot', sa.JSON(), nullable=True),
        schema='identity'
    )
    op.add_column(
        'merge_decision',
        sa.Column('prior_state_snapshot', sa.JSON(), nullable=True),
        schema='identity'
    )
    op.add_column(
        'merge_decision',
        sa.Column('rule_version', sa.String(), nullable=True),
        schema='identity'
    )
    op.add_column(
        'merge_decision',
        sa.Column('actor', sa.String(), nullable=True),
        schema='identity'
    )
    op.add_column(
        'merge_decision',
        sa.Column('notes', sa.String(), nullable=True),
        schema='identity'
    )


def downgrade() -> None:
    # 3. Revert merge_decision
    op.drop_column('merge_decision', 'notes', schema='identity')
    op.drop_column('merge_decision', 'actor', schema='identity')
    op.drop_column('merge_decision', 'rule_version', schema='identity')
    op.drop_column('merge_decision', 'prior_state_snapshot', schema='identity')
    op.drop_column('merge_decision', 'evidence_snapshot', schema='identity')
    op.drop_column('merge_decision', 'merged_record_id', schema='identity')
    op.drop_column('merge_decision', 'survivor_record_id', schema='identity')

    # 2. Revert match_candidate
    op.drop_column('match_candidate', 'conflict_reasons', schema='identity')
    op.drop_column('match_candidate', 'conflict_detected', schema='identity')
    op.drop_column('match_candidate', 'match_type', schema='identity')

    # 1. Revert vessel_call
    op.drop_index(op.f('ix_canonical_vessel_call_is_merged'), table_name='vessel_call', schema='canonical')
    op.drop_column('vessel_call', 'merged_into_id', schema='canonical')
    op.drop_column('vessel_call', 'is_merged', schema='canonical')
