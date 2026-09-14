"""Journey reconstruction models (Phase 06)

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-14 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. canonical.event_occurrence: verification status + supersession chain
    op.add_column(
        'event_occurrence',
        sa.Column('verification_status', sa.String(), nullable=True),
        schema='canonical'
    )
    op.add_column(
        'event_occurrence',
        sa.Column('superseded_by_id', sa.UUID(), nullable=True),
        schema='canonical'
    )
    op.create_foreign_key(
        'fk_event_occurrence_superseded_by',
        'event_occurrence', 'event_occurrence',
        ['superseded_by_id'], ['id'],
        source_schema='canonical', referent_schema='canonical',
        ondelete='SET NULL'
    )
    op.add_column(
        'event_occurrence',
        sa.Column('is_superseded', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        schema='canonical'
    )

    # 2. journey.journey_template: rule_version
    op.add_column(
        'journey_template',
        sa.Column('rule_version', sa.String(), server_default='1.0', nullable=False),
        schema='journey'
    )

    # 3. journey.journey_stage: full stage catalogue columns
    op.add_column('journey_stage', sa.Column('sequence_index', sa.Integer(), server_default='0', nullable=False), schema='journey')
    op.add_column('journey_stage', sa.Column('start_event_name', sa.String(), nullable=True), schema='journey')
    op.add_column('journey_stage', sa.Column('end_event_name', sa.String(), nullable=True), schema='journey')
    op.add_column('journey_stage', sa.Column('time_category', sa.String(), server_default='UNCLASSIFIED', nullable=False), schema='journey')
    op.add_column('journey_stage', sa.Column('actor_from', sa.String(), nullable=True), schema='journey')
    op.add_column('journey_stage', sa.Column('actor_to', sa.String(), nullable=True), schema='journey')
    op.add_column('journey_stage', sa.Column('is_optional', sa.Boolean(), server_default=sa.text('false'), nullable=False), schema='journey')
    op.add_column('journey_stage', sa.Column('is_repeatable', sa.Boolean(), server_default=sa.text('false'), nullable=False), schema='journey')

    # 4. journey.journey_instance: reconstruction metadata
    op.add_column('journey_instance', sa.Column('reconstruction_version', sa.Integer(), server_default='1', nullable=False), schema='journey')
    op.add_column('journey_instance', sa.Column('rule_version', sa.String(), nullable=True), schema='journey')
    op.add_column('journey_instance', sa.Column('computed_at', sa.DateTime(timezone=True), nullable=True), schema='journey')
    op.add_column('journey_instance', sa.Column('coverage_summary', sa.JSON(), nullable=True), schema='journey')
    op.add_column('journey_instance', sa.Column('time_decomposition', sa.JSON(), nullable=True), schema='journey')
    op.add_column('journey_instance', sa.Column('deviation_report', sa.JSON(), nullable=True), schema='journey')
    op.create_unique_constraint('uq_journey_instance_vessel_call', 'journey_instance', ['vessel_call_id'], schema='journey')

    # 5. journey.stage_occurrence: full occurrence detail
    op.add_column('stage_occurrence', sa.Column('stage_name', sa.String(), server_default='', nullable=False), schema='journey')
    op.add_column('stage_occurrence', sa.Column('sequence_index', sa.Integer(), server_default='0', nullable=False), schema='journey')
    op.add_column('stage_occurrence', sa.Column('shift_occurrence_index', sa.Integer(), server_default='0', nullable=False), schema='journey')
    op.add_column('stage_occurrence', sa.Column('start_event_occurrence_id', sa.UUID(), nullable=True), schema='journey')
    op.add_column('stage_occurrence', sa.Column('end_event_occurrence_id', sa.UUID(), nullable=True), schema='journey')
    op.create_foreign_key(
        'fk_stage_occurrence_start_event', 'stage_occurrence', 'event_occurrence',
        ['start_event_occurrence_id'], ['id'], source_schema='journey', referent_schema='canonical',
    )
    op.create_foreign_key(
        'fk_stage_occurrence_end_event', 'stage_occurrence', 'event_occurrence',
        ['end_event_occurrence_id'], ['id'], source_schema='journey', referent_schema='canonical',
    )
    op.add_column('stage_occurrence', sa.Column('start_time', sa.DateTime(timezone=True), nullable=True), schema='journey')
    op.add_column('stage_occurrence', sa.Column('end_time', sa.DateTime(timezone=True), nullable=True), schema='journey')
    op.add_column('stage_occurrence', sa.Column('duration_hours', sa.Float(), nullable=True), schema='journey')
    op.add_column('stage_occurrence', sa.Column('availability', sa.String(), server_default='UNAVAILABLE', nullable=False), schema='journey')
    op.add_column('stage_occurrence', sa.Column('is_missing', sa.Boolean(), server_default=sa.text('false'), nullable=False), schema='journey')
    op.add_column('stage_occurrence', sa.Column('is_inferred', sa.Boolean(), server_default=sa.text('false'), nullable=False), schema='journey')
    op.add_column('stage_occurrence', sa.Column('inference_reason', sa.String(), nullable=True), schema='journey')
    op.add_column('stage_occurrence', sa.Column('time_category', sa.String(), server_default='UNCLASSIFIED', nullable=False), schema='journey')
    op.add_column('stage_occurrence', sa.Column('deviation_type', sa.String(), nullable=True), schema='journey')
    op.add_column('stage_occurrence', sa.Column('deviation_detail', sa.JSON(), nullable=True), schema='journey')

    # 6. journey.handover: actor + wait detail
    op.add_column('handover', sa.Column('from_actor', sa.String(), nullable=True), schema='journey')
    op.add_column('handover', sa.Column('to_actor', sa.String(), nullable=True), schema='journey')
    op.add_column('handover', sa.Column('handover_time', sa.DateTime(timezone=True), nullable=True), schema='journey')
    op.add_column('handover', sa.Column('wait_duration_hours', sa.Float(), nullable=True), schema='journey')

    # 7. journey.canonical_observation
    op.create_table(
        'canonical_observation',
        sa.Column('vessel_call_id', sa.UUID(), nullable=False),
        sa.Column('event_definition_id', sa.UUID(), nullable=False),
        sa.Column('candidate_event_occurrence_ids', sa.JSON(), nullable=False),
        sa.Column('selected_event_occurrence_id', sa.UUID(), nullable=True),
        sa.Column('conflict_detected', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('selection_method', sa.String(), server_default='AUTOMATIC', nullable=False),
        sa.Column('selection_reasoning', sa.JSON(), nullable=True),
        sa.Column('quality_issue_id', sa.UUID(), nullable=True),
        sa.Column('decided_by', sa.String(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rule_version', sa.String(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['vessel_call_id'], ['canonical.vessel_call.id']),
        sa.ForeignKeyConstraint(['event_definition_id'], ['config.event_definition.id']),
        sa.ForeignKeyConstraint(['selected_event_occurrence_id'], ['canonical.event_occurrence.id']),
        sa.ForeignKeyConstraint(['quality_issue_id'], ['quality.quality_issue.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='journey'
    )

    # 8. journey.observation_correction
    op.create_table(
        'observation_correction',
        sa.Column('vessel_call_id', sa.UUID(), nullable=False),
        sa.Column('event_definition_id', sa.UUID(), nullable=True),
        sa.Column('prior_event_occurrence_id', sa.UUID(), nullable=True),
        sa.Column('new_event_occurrence_id', sa.UUID(), nullable=True),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('actor', sa.String(), nullable=False),
        sa.Column('approval_state', sa.String(), server_default='PENDING', nullable=False),
        sa.Column('approved_by', sa.String(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('triggers_recalculation', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('recalculated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['vessel_call_id'], ['canonical.vessel_call.id']),
        sa.ForeignKeyConstraint(['event_definition_id'], ['config.event_definition.id']),
        sa.ForeignKeyConstraint(['prior_event_occurrence_id'], ['canonical.event_occurrence.id']),
        sa.ForeignKeyConstraint(['new_event_occurrence_id'], ['canonical.event_occurrence.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='journey'
    )

    # 9. journey.journey_narrative
    op.create_table(
        'journey_narrative',
        sa.Column('vessel_call_id', sa.UUID(), nullable=False),
        sa.Column('journey_instance_id', sa.UUID(), nullable=False),
        sa.Column('narrative_text', sa.String(), nullable=False),
        sa.Column('grounding_record_ids', sa.JSON(), nullable=False),
        sa.Column('model_name', sa.String(), nullable=False),
        sa.Column('is_ai_generated', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('inference_status', sa.String(), server_default='AI_GENERATED', nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['vessel_call_id'], ['canonical.vessel_call.id']),
        sa.ForeignKeyConstraint(['journey_instance_id'], ['journey.journey_instance.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='journey'
    )

    # 10. journey.reconstruction_history
    op.create_table(
        'reconstruction_history',
        sa.Column('journey_instance_id', sa.UUID(), nullable=False),
        sa.Column('vessel_call_id', sa.UUID(), nullable=False),
        sa.Column('run_version', sa.Integer(), nullable=False),
        sa.Column('rule_version', sa.String(), nullable=True),
        sa.Column('triggered_by', sa.String(), server_default='SYSTEM', nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('updated_by', sa.String(), nullable=True),
        sa.Column('source_lineage_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['journey_instance_id'], ['journey.journey_instance.id']),
        sa.ForeignKeyConstraint(['vessel_call_id'], ['canonical.vessel_call.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='journey'
    )


def downgrade() -> None:
    op.drop_table('reconstruction_history', schema='journey')
    op.drop_table('journey_narrative', schema='journey')
    op.drop_table('observation_correction', schema='journey')
    op.drop_table('canonical_observation', schema='journey')

    op.drop_column('handover', 'wait_duration_hours', schema='journey')
    op.drop_column('handover', 'handover_time', schema='journey')
    op.drop_column('handover', 'to_actor', schema='journey')
    op.drop_column('handover', 'from_actor', schema='journey')

    op.drop_column('stage_occurrence', 'deviation_detail', schema='journey')
    op.drop_column('stage_occurrence', 'deviation_type', schema='journey')
    op.drop_column('stage_occurrence', 'time_category', schema='journey')
    op.drop_column('stage_occurrence', 'inference_reason', schema='journey')
    op.drop_column('stage_occurrence', 'is_inferred', schema='journey')
    op.drop_column('stage_occurrence', 'is_missing', schema='journey')
    op.drop_column('stage_occurrence', 'availability', schema='journey')
    op.drop_column('stage_occurrence', 'duration_hours', schema='journey')
    op.drop_column('stage_occurrence', 'end_time', schema='journey')
    op.drop_column('stage_occurrence', 'start_time', schema='journey')
    op.drop_constraint('fk_stage_occurrence_end_event', 'stage_occurrence', schema='journey', type_='foreignkey')
    op.drop_constraint('fk_stage_occurrence_start_event', 'stage_occurrence', schema='journey', type_='foreignkey')
    op.drop_column('stage_occurrence', 'end_event_occurrence_id', schema='journey')
    op.drop_column('stage_occurrence', 'start_event_occurrence_id', schema='journey')
    op.drop_column('stage_occurrence', 'shift_occurrence_index', schema='journey')
    op.drop_column('stage_occurrence', 'sequence_index', schema='journey')
    op.drop_column('stage_occurrence', 'stage_name', schema='journey')

    op.drop_constraint('uq_journey_instance_vessel_call', 'journey_instance', schema='journey', type_='unique')
    op.drop_column('journey_instance', 'deviation_report', schema='journey')
    op.drop_column('journey_instance', 'time_decomposition', schema='journey')
    op.drop_column('journey_instance', 'coverage_summary', schema='journey')
    op.drop_column('journey_instance', 'computed_at', schema='journey')
    op.drop_column('journey_instance', 'rule_version', schema='journey')
    op.drop_column('journey_instance', 'reconstruction_version', schema='journey')

    op.drop_column('journey_stage', 'is_repeatable', schema='journey')
    op.drop_column('journey_stage', 'is_optional', schema='journey')
    op.drop_column('journey_stage', 'actor_to', schema='journey')
    op.drop_column('journey_stage', 'actor_from', schema='journey')
    op.drop_column('journey_stage', 'time_category', schema='journey')
    op.drop_column('journey_stage', 'end_event_name', schema='journey')
    op.drop_column('journey_stage', 'start_event_name', schema='journey')
    op.drop_column('journey_stage', 'sequence_index', schema='journey')

    op.drop_column('journey_template', 'rule_version', schema='journey')

    op.drop_column('event_occurrence', 'is_superseded', schema='canonical')
    op.drop_constraint('fk_event_occurrence_superseded_by', 'event_occurrence', schema='canonical', type_='foreignkey')
    op.drop_column('event_occurrence', 'superseded_by_id', schema='canonical')
    op.drop_column('event_occurrence', 'verification_status', schema='canonical')
