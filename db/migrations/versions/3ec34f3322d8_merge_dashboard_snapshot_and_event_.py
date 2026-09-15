"""merge_dashboard_snapshot_and_event_definitions

Revision ID: 3ec34f3322d8
Revises: a2b3c4d5e6f7, g5b6c7d8e9f0
Create Date: 2026-09-15 12:39:42.132287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ec34f3322d8'
down_revision: Union[str, Sequence[str], None] = ('a2b3c4d5e6f7', 'g5b6c7d8e9f0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
