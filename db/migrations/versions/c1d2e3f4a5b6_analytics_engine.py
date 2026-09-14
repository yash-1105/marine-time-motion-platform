"""Analytics engine models (Phase 07)

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-09-14 19:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend canonical.service_request
    op.add_column('service_request', sa.Column('movement_type', sa.String(), nullable=True), schema='canonical')
    op.add_column('service_request', sa.Column('submission_time', sa.DateTime(timezone=True), nullable=True), schema='canonical')

    # 2. Extend analytics.lead_time_definition
    op.add_column('lead_time_definition', sa.Column('description', sa.Text(), nullable=True), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('formula_version', sa.String(), server_default='1.0', nullable=False), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('unit', sa.String(), server_default='hours', nullable=False), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('eligibility_criteria', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('null_handling', sa.String(), server_default='UNAVAILABLE', nullable=False), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('occurrence_selection', sa.String(), server_default='first', nullable=False), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('availability_status', sa.String(), server_default='COMPUTABLE', nullable=False), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('required_events', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('custom_builder', sa.Boolean(), server_default=sa.text('false'), nullable=False), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('created_by_user', sa.String(), nullable=True), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('is_execution_delay', sa.Boolean(), server_default=sa.text('false'), nullable=False), schema='analytics')
    op.add_column('lead_time_definition', sa.Column('execution_delay_movement', sa.String(), nullable=True), schema='analytics')

    # 3. Extend analytics.lead_time_result
    op.add_column('lead_time_result', sa.Column('status', sa.String(), server_default='UNAVAILABLE', nullable=False), schema='analytics')
    op.add_column('lead_time_result', sa.Column('unavailable_reason', sa.Text(), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('formula_version', sa.String(), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('source_record_ids', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('filter_context', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('exclusions_applied', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('dq_status', sa.String(), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('start_event_occurrence_id', sa.UUID(), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('end_event_occurrence_id', sa.UUID(), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('start_time', sa.DateTime(timezone=True), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('end_time', sa.DateTime(timezone=True), nullable=True), schema='analytics')
    op.add_column('lead_time_result', sa.Column('vcn', sa.String(), nullable=True), schema='analytics')
    op.create_foreign_key(
        'fk_ltr_start_event_occ', 'lead_time_result', 'event_occurrence',
        ['start_event_occurrence_id'], ['id'],
        source_schema='analytics', referent_schema='canonical',
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_ltr_end_event_occ', 'lead_time_result', 'event_occurrence',
        ['end_event_occurrence_id'], ['id'],
        source_schema='analytics', referent_schema='canonical',
        ondelete='SET NULL',
    )

    # 4. Create analytics.statistical_aggregate
    op.create_table(
        'statistical_aggregate',
        sa.Column('definition_id', sa.UUID(), nullable=False),
        sa.Column('cohort_key', sa.String(), server_default='all', nullable=False),
        sa.Column('cohort_filters', sa.JSON(), nullable=True),
        sa.Column('observation_count', sa.Integer(), nullable=True),
        sa.Column('missing_count', sa.Integer(), nullable=True),
        sa.Column('mean_hours', sa.Float(), nullable=True),
        sa.Column('median_hours', sa.Float(), nullable=True),
        sa.Column('std_hours', sa.Float(), nullable=True),
        sa.Column('cv', sa.Float(), nullable=True),
        sa.Column('min_hours', sa.Float(), nullable=True),
        sa.Column('max_hours', sa.Float(), nullable=True),
        sa.Column('p25_hours', sa.Float(), nullable=True),
        sa.Column('p75_hours', sa.Float(), nullable=True),
        sa.Column('p90_hours', sa.Float(), nullable=True),
        sa.Column('p95_hours', sa.Float(), nullable=True),
        sa.Column('fastest_vcn', sa.String(), nullable=True),
        sa.Column('slowest_vcn', sa.String(), nullable=True),
        sa.Column('tail_risk_ratio', sa.Float(), nullable=True),
        sa.Column('right_skew_flag', sa.Boolean(), nullable=True),
        sa.Column('percentile_method', sa.String(), server_default='linear_interpolation', nullable=False),
        sa.Column('small_sample_warning', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('outlier_vcns', sa.JSON(), nullable=True),
        sa.Column('formula_version', sa.String(), nullable=True),
        sa.Column('quarantine_excluded', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['definition_id'], ['analytics.lead_time_definition.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('definition_id', 'cohort_key', name='uq_stat_agg_def_cohort'),
        schema='analytics',
    )


def downgrade() -> None:
    op.drop_table('statistical_aggregate', schema='analytics')

    op.drop_constraint('fk_ltr_end_event_occ', 'lead_time_result', schema='analytics', type_='foreignkey')
    op.drop_constraint('fk_ltr_start_event_occ', 'lead_time_result', schema='analytics', type_='foreignkey')
    for col in ['vcn', 'end_time', 'start_time', 'end_event_occurrence_id', 'start_event_occurrence_id',
                'calculated_at', 'dq_status', 'exclusions_applied', 'filter_context',
                'source_record_ids', 'formula_version', 'unavailable_reason', 'status']:
        op.drop_column('lead_time_result', col, schema='analytics')

    for col in ['execution_delay_movement', 'is_execution_delay', 'created_by_user', 'custom_builder',
                'required_events', 'availability_status', 'occurrence_selection', 'null_handling',
                'eligibility_criteria', 'unit', 'formula_version', 'description']:
        op.drop_column('lead_time_definition', col, schema='analytics')

    op.drop_column('service_request', 'submission_time', schema='canonical')
    op.drop_column('service_request', 'movement_type', schema='canonical')
