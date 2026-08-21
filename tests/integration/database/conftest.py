"""Fixtures for an explicitly configured disposable PostgreSQL database."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings


def _test_database_url() -> str:
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip(
            "TEST_DATABASE_URL is required for real PostgreSQL/pgvector integration tests",
            allow_module_level=True,
        )
    if not value.startswith("postgresql+psycopg://"):
        pytest.fail("TEST_DATABASE_URL must use postgresql+psycopg")
    return value


@pytest.fixture(scope="session")
def postgres_url() -> str:
    return _test_database_url()


@pytest.fixture(scope="session")
def postgres_engine(postgres_url: str) -> Iterator[Engine]:
    engine = create_engine(postgres_url, pool_pre_ping=True, hide_parameters=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as error:
        engine.dispose()
        pytest.fail(f"Configured PostgreSQL test database is unavailable: {type(error).__name__}")
    yield engine
    engine.dispose()


def _redirect_settings_to(url_value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point application settings at the disposable test database.

    Alembic reads its URL from the same ``Settings`` object as the application,
    which now builds that URL from the separate DB_* values. Setting
    DATABASE_URL here would be silently ignored and the migration commands
    below would run ``downgrade base`` against the developer's own local
    database, so every part is redirected explicitly.
    """
    url = make_url(url_value)
    monkeypatch.setenv("DB_HOST", url.host or "localhost")
    monkeypatch.setenv("DB_PORT", str(url.port or 5432))
    monkeypatch.setenv("DB_NAME", url.database or "")
    monkeypatch.setenv("DB_USER", url.username or "")
    monkeypatch.setenv("DB_PASSWORD", url.password or "")
    get_settings.cache_clear()


@pytest.fixture()
def database_settings_environment(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Expose the redirect on its own for tests that drive Alembic directly."""
    _redirect_settings_to(postgres_url, monkeypatch)
    yield
    get_settings.cache_clear()


@pytest.fixture()
def migrated_engine(
    postgres_engine: Engine,
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Engine]:
    _redirect_settings_to(postgres_url, monkeypatch)
    configuration = Config("alembic.ini")
    command.downgrade(configuration, "base")
    command.upgrade(configuration, "head")
    yield postgres_engine
    command.downgrade(configuration, "base")
    get_settings.cache_clear()
