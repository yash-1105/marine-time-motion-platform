"""initial schemas

Revision ID: 0001
Revises: 
Create Date: 2026-09-14 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    op.execute("CREATE SCHEMA IF NOT EXISTS staging;")
    op.execute("CREATE SCHEMA IF NOT EXISTS canonical;")
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics;")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit;")
    op.execute("CREATE SCHEMA IF NOT EXISTS config;")
    op.execute("CREATE SCHEMA IF NOT EXISTS testkit;")
    op.execute("CREATE SCHEMA IF NOT EXISTS identity;")
    op.execute("CREATE SCHEMA IF NOT EXISTS quality;")
    op.execute("CREATE SCHEMA IF NOT EXISTS journey;")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS raw CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS staging CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS canonical CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS analytics CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS config CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS testkit CASCADE;")
