"""Alembic migration tests against PostgreSQL with pgvector."""

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text

EXPECTED_TABLES = {
    "alembic_version",
    "approval_decisions",
    "audit_events",
    "chunks",
    "document_versions",
    "documents",
    "embedding_sets",
    "embeddings",
}


def test_migration_upgrade_and_pgvector_extension(
    postgres_engine: Engine,
    database_settings_environment: None,
) -> None:
    configuration = Config("alembic.ini")
    command.downgrade(configuration, "base")
    command.upgrade(configuration, "head")

    assert EXPECTED_TABLES <= set(inspect(postgres_engine).get_table_names())
    with postgres_engine.connect() as connection:
        extension_version = connection.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
    assert extension_version is not None

    command.downgrade(configuration, "base")
    assert not (EXPECTED_TABLES - {"alembic_version"}) & set(
        inspect(postgres_engine).get_table_names()
    )
