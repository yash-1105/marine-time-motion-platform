"""Add high-volume DQ lineage lookup indexes without altering source evidence.

Revision ID: l0m1n2o3p4q5
Revises: k9l0m1n2o3p4
"""

from alembic import op


revision = "l0m1n2o3p4q5"
down_revision = "k9l0m1n2o3p4"
branch_labels = None
depends_on = None


def upgrade():
    # Canonical-to-staging traceability and analytical exclusions resolve a record
    # by exact source file/sheet/row. Both indexes are additive and non-unique.
    op.create_index(
        "ix_raw_record_source_file_sheet_row",
        "record",
        ["source_file_id", "worksheet_name", "row_number"],
        schema="raw",
    )
    op.create_index(
        "ix_staging_record_source_file_sheet_row",
        "record",
        ["source_file_id", "worksheet_name", "row_number"],
        schema="staging",
    )


def downgrade():
    # Index-only rollback: raw/staging lineage data is deliberately preserved.
    op.drop_index("ix_staging_record_source_file_sheet_row", table_name="record", schema="staging")
    op.drop_index("ix_raw_record_source_file_sheet_row", table_name="record", schema="raw")
