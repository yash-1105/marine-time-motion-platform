"""Add governed dataset-group file manifests and per-file raw/staging lineage.

Revision ID: k9l0m1n2o3p4
Revises: j8k9l0m1n2o3
"""
from alembic import op
import sqlalchemy as sa

revision = "k9l0m1n2o3p4"
down_revision = "j8k9l0m1n2o3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "file",
        sa.Column("group_batch_id", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("file_checksum", sa.String(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("storage_reference", sa.String(), nullable=True),
        sa.Column("parse_status", sa.String(), nullable=False),
        sa.Column("validation_status", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("source_lineage_id", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"), schema="raw",
    )
    op.create_index("ix_raw_file_group_batch_id", "file", ["group_batch_id"], schema="raw")
    op.add_column("record", sa.Column("source_file_id", sa.String(), nullable=True), schema="raw")
    op.add_column("record", sa.Column("source_file_id", sa.String(), nullable=True), schema="staging")


def downgrade():
    # Rollback removes only the additive group-manifest/lineage schema. It does
    # not delete raw rows or uploaded objects; archive/export that metadata before
    # downgrade if a pre-group application version must be restored.
    op.drop_column("record", "source_file_id", schema="staging")
    op.drop_column("record", "source_file_id", schema="raw")
    op.drop_index("ix_raw_file_group_batch_id", table_name="file", schema="raw")
    op.drop_table("file", schema="raw")
