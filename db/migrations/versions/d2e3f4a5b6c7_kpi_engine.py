"""KPI engine, governed registry, benchmarks, and canonical cargo operations (Phase 08)

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-14 20:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend analytics.kpi table
    op.add_column('kpi', sa.Column('kpi_number', sa.Integer(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('code', sa.String(length=50), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('category', sa.String(length=100), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('formula', sa.Text(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('numerator', sa.Text(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('denominator', sa.Text(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('unit', sa.String(length=50), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('eligible_population', sa.Text(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('required_events', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('required_fields', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('exclusions', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('aggregation_method', sa.String(length=50), server_default='AVG', nullable=False), schema='analytics')
    op.add_column('kpi', sa.Column('vessel_applicability', sa.String(length=100), server_default='All', nullable=False), schema='analytics')
    op.add_column('kpi', sa.Column('target', sa.Float(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('target_direction', sa.String(length=20), server_default='LOWER_IS_BETTER', nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('thresholds', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('owner', sa.String(length=100), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('effective_from', sa.DateTime(timezone=True), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('is_primary', sa.Boolean(), server_default=sa.text('true'), nullable=False), schema='analytics')
    op.add_column('kpi', sa.Column('alias_of_id', sa.UUID(), nullable=True), schema='analytics')
    op.add_column('kpi', sa.Column('availability_status', sa.String(length=50), server_default='COMPUTED', nullable=False), schema='analytics')
    op.add_column('kpi', sa.Column('required_source_systems', sa.JSON(), nullable=True), schema='analytics')

    op.create_foreign_key(
        'fk_kpi_alias_of', 'kpi', 'kpi',
        ['alias_of_id'], ['id'],
        source_schema='analytics', referent_schema='analytics',
        ondelete='SET NULL'
    )
    op.create_index('ix_analytics_kpi_code', 'kpi', ['code'], unique=False, schema='analytics')

    # 2. Extend analytics.kpi_result table
    op.add_column('kpi_result', sa.Column('period_start', sa.DateTime(timezone=True), nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('period_end', sa.DateTime(timezone=True), nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('grain', sa.String(length=20), server_default='ALL', nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('cohort_key', sa.String(length=100), server_default='all', nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('cohort_filters', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('numerator_value', sa.Float(), nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('denominator_value', sa.Float(), nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('target_value', sa.Float(), nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('band', sa.String(length=20), nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('unavailable_reason', sa.Text(), nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('formula_version', sa.String(length=50), server_default='1.0', nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('data_quality_summary', sa.JSON(), nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=True), schema='analytics')
    op.add_column('kpi_result', sa.Column('is_recalculation', sa.Boolean(), server_default=sa.text('false'), nullable=False), schema='analytics')

    # 3. Create analytics.kpi_benchmark table
    op.create_table(
        'kpi_benchmark',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('kpi_id', sa.UUID(), nullable=False),
        sa.Column('peer_port', sa.String(length=100), nullable=False),
        sa.Column('benchmark_value', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('period', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.ForeignKeyConstraint(['kpi_id'], ['analytics.kpi.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='analytics'
    )

    # 4. Create canonical.cargo_operation table
    op.create_table(
        'cargo_operation',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('vessel_call_id', sa.UUID(), nullable=False),
        sa.Column('operation_id', sa.String(length=100), nullable=True),
        sa.Column('cargo_type', sa.String(length=100), nullable=True),
        sa.Column('operation_type', sa.String(length=100), nullable=True),
        sa.Column('planned_quantity', sa.Float(), nullable=True),
        sa.Column('unit', sa.String(length=50), nullable=True),
        sa.Column('cargo_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cargo_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('working_hours', sa.Float(), nullable=True),
        sa.Column('resources_deployed', sa.Integer(), nullable=True),
        sa.Column('downtime_hours', sa.Float(), nullable=True),
        sa.Column('actual_quantity', sa.Float(), nullable=True),
        sa.Column('data_status', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.ForeignKeyConstraint(['vessel_call_id'], ['canonical.vessel_call.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        schema='canonical'
    )


def downgrade() -> None:
    op.drop_table('cargo_operation', schema='canonical')
    op.drop_table('kpi_benchmark', schema='analytics')

    op.drop_column('kpi_result', 'is_recalculation', schema='analytics')
    op.drop_column('kpi_result', 'calculated_at', schema='analytics')
    op.drop_column('kpi_result', 'data_quality_summary', schema='analytics')
    op.drop_column('kpi_result', 'formula_version', schema='analytics')
    op.drop_column('kpi_result', 'unavailable_reason', schema='analytics')
    op.drop_column('kpi_result', 'band', schema='analytics')
    op.drop_column('kpi_result', 'target_value', schema='analytics')
    op.drop_column('kpi_result', 'denominator_value', schema='analytics')
    op.drop_column('kpi_result', 'numerator_value', schema='analytics')
    op.drop_column('kpi_result', 'cohort_filters', schema='analytics')
    op.drop_column('kpi_result', 'cohort_key', schema='analytics')
    op.drop_column('kpi_result', 'grain', schema='analytics')
    op.drop_column('kpi_result', 'period_end', schema='analytics')
    op.drop_column('kpi_result', 'period_start', schema='analytics')

    op.drop_index('ix_analytics_kpi_code', table_name='kpi', schema='analytics')
    op.drop_constraint('fk_kpi_alias_of', 'kpi', schema='analytics', type_='foreignkey')
    op.drop_column('kpi', 'required_source_systems', schema='analytics')
    op.drop_column('kpi', 'availability_status', schema='analytics')
    op.drop_column('kpi', 'alias_of_id', schema='analytics')
    op.drop_column('kpi', 'is_primary', schema='analytics')
    op.drop_column('kpi', 'effective_to', schema='analytics')
    op.drop_column('kpi', 'effective_from', schema='analytics')
    op.drop_column('kpi', 'owner', schema='analytics')
    op.drop_column('kpi', 'thresholds', schema='analytics')
    op.drop_column('kpi', 'target_direction', schema='analytics')
    op.drop_column('kpi', 'target', schema='analytics')
    op.drop_column('kpi', 'vessel_applicability', schema='analytics')
    op.drop_column('kpi', 'aggregation_method', schema='analytics')
    op.drop_column('kpi', 'exclusions', schema='analytics')
    op.drop_column('kpi', 'required_fields', schema='analytics')
    op.drop_column('kpi', 'required_events', schema='analytics')
    op.drop_column('kpi', 'eligible_population', schema='analytics')
    op.drop_column('kpi', 'unit', schema='analytics')
    op.drop_column('kpi', 'denominator', schema='analytics')
    op.drop_column('kpi', 'numerator', schema='analytics')
    op.drop_column('kpi', 'formula', schema='analytics')
    op.drop_column('kpi', 'category', schema='analytics')
    op.drop_column('kpi', 'code', schema='analytics')
    op.drop_column('kpi', 'kpi_number', schema='analytics')
