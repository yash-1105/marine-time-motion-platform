"""audit_trigger

Revision ID: 384d7f763123
Revises: 106b006549ce
Create Date: 2026-09-14 14:57:20.414714

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '384d7f763123'
down_revision: Union[str, Sequence[str], None] = '106b006549ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
    CREATE OR REPLACE FUNCTION audit.reject_update_delete()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'audit_event is append-only. Updates and deletes are not allowed.';
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER trg_audit_append_only
    BEFORE UPDATE OR DELETE ON audit.audit_event
    FOR EACH ROW EXECUTE FUNCTION audit.reject_update_delete();
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_audit_append_only ON audit.audit_event;")
    op.execute("DROP FUNCTION IF EXISTS audit.reject_update_delete();")
