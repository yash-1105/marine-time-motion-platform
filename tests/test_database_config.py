"""Database URL compatibility checks for the deployed SQLAlchemy driver."""
from apps.api.core.config import Settings


def test_postgresql_urls_select_the_installed_psycopg2_driver():
    assert Settings.assemble_db_url("postgres://user:pass@db:5432/name") == (
        "postgresql+psycopg2://user:pass@db:5432/name"
    )
    assert Settings.assemble_db_url("postgresql://user:pass@db:5432/name") == (
        "postgresql+psycopg2://user:pass@db:5432/name"
    )
    assert Settings.assemble_db_url("postgresql+psycopg2://user:pass@db:5432/name") == (
        "postgresql+psycopg2://user:pass@db:5432/name"
    )
