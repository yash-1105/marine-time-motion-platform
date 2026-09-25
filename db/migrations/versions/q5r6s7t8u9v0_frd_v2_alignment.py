"""FRD v2 canonical attributes and governed outlier evidence.

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "q5r6s7t8u9v0"
down_revision: Union[str, Sequence[str], None] = "p4q5r6s7t8u9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vessel_call", sa.Column("license_number", sa.String(), nullable=True), schema="canonical")
    op.add_column("event_occurrence", sa.Column("operation_type", sa.String(), nullable=True), schema="canonical")
    op.add_column("event_occurrence", sa.Column("attributes", sa.JSON(), nullable=True), schema="canonical")
    op.add_column("cargo_operation", sa.Column("attributes", sa.JSON(), nullable=True), schema="canonical")

    op.add_column("outlier_record", sa.Column("tenant_id", sa.String(length=100), nullable=True), schema="analytics")
    op.add_column("outlier_record", sa.Column("rule_id", sa.String(length=100), nullable=True), schema="analytics")
    op.alter_column("outlier_record", "observed_value", existing_type=sa.Float(), nullable=True, schema="analytics")
    op.add_column("outlier_record", sa.Column("issue_text", sa.Text(), nullable=True), schema="analytics")
    op.add_column("outlier_record", sa.Column("threshold_label", sa.String(length=100), nullable=True), schema="analytics")
    op.add_column("outlier_record", sa.Column("reason", sa.Text(), nullable=True), schema="analytics")
    op.add_column("outlier_record", sa.Column("movement_leg", sa.String(length=50), nullable=True), schema="analytics")
    op.add_column("outlier_record", sa.Column("source_record_ids", sa.JSON(), nullable=True), schema="analytics")
    op.execute(sa.text(
        "UPDATE analytics.outlier_record AS o SET tenant_id = v.tenant_id "
        "FROM canonical.vessel_call AS v WHERE v.id = o.vessel_call_id AND o.tenant_id IS NULL"
    ))
    op.execute(sa.text(
        "UPDATE analytics.outlier_record SET tenant_id = 'default-tenant' WHERE tenant_id IS NULL"
    ))
    op.alter_column("outlier_record", "tenant_id", existing_type=sa.String(length=100), nullable=False, schema="analytics")
    op.create_index("ix_outlier_record_tenant_id", "outlier_record", ["tenant_id"], schema="analytics")


def downgrade() -> None:
    op.drop_index("ix_outlier_record_tenant_id", table_name="outlier_record", schema="analytics")
    # Data-quality outlier projections can legitimately have no numeric value;
    # the underlying DQ issues remain authoritative and these derived rows are
    # safely regenerated if the downgrade is later reversed.
    op.execute(sa.text("DELETE FROM analytics.outlier_record WHERE observed_value IS NULL"))
    for column in ("source_record_ids", "movement_leg", "reason", "threshold_label", "issue_text", "rule_id", "tenant_id"):
        op.drop_column("outlier_record", column, schema="analytics")
    op.alter_column("outlier_record", "observed_value", existing_type=sa.Float(), nullable=False, schema="analytics")
    op.drop_column("cargo_operation", "attributes", schema="canonical")
    op.drop_column("event_occurrence", "attributes", schema="canonical")
    op.drop_column("event_occurrence", "operation_type", schema="canonical")
    op.drop_column("vessel_call", "license_number", schema="canonical")
