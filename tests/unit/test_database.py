"""Unit tests for safe database engine behavior."""

from typing import Any, cast

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.database import (
    DatabaseUnavailableError,
    create_database_engine,
    verify_database_connection,
)


def test_engine_configuration_hides_password_and_parameters() -> None:
    password = "engine-secret"
    engine = create_database_engine(
        Settings(_env_file=None, db_password=SecretStr(password))  # type: ignore[call-arg]
    )
    try:
        assert password not in repr(engine.url)
        assert engine.hide_parameters is True
    finally:
        engine.dispose()


def test_the_engine_receives_the_generated_url_intact() -> None:
    """The settings-built URL survives the round trip into the engine."""
    password = "engine[]:#%secret"
    engine = create_database_engine(
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            db_host="db.example.test",
            db_port=6543,
            db_name="oiap_test",
            db_user="oiap_app",
            db_password=SecretStr(password),
        )
    )
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.host == "db.example.test"
        assert engine.url.port == 6543
        assert engine.url.database == "oiap_test"
        assert engine.url.username == "oiap_app"
        assert engine.url.password == password
    finally:
        engine.dispose()


def test_database_unavailable_error_is_credential_safe() -> None:
    class UnavailableEngine:
        def connect(self) -> Any:
            raise OperationalError(
                "connect",
                {},
                RuntimeError("postgresql+psycopg://user:secret@localhost/oiap"),
            )

    with pytest.raises(DatabaseUnavailableError) as captured:
        verify_database_connection(cast(Engine, UnavailableEngine()))

    assert str(captured.value) == "PostgreSQL is unavailable"
    assert "secret" not in str(captured.value)
