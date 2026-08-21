"""PostgreSQL engine and transactional session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


class DatabaseUnavailableError(RuntimeError):
    """Raised when PostgreSQL cannot be reached without leaking connection details."""


def create_database_engine(settings: Settings) -> Engine:
    """Create the configured PostgreSQL engine without opening a connection."""
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        connect_args={
            "connect_timeout": settings.database_connect_timeout_seconds,
        },
        hide_parameters=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create sessions whose writes remain explicit and transaction-scoped."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Commit a successful unit of work and roll back every failure."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def verify_database_connection(engine: Engine) -> None:
    """Verify PostgreSQL availability while returning a credential-safe error."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as error:
        raise DatabaseUnavailableError("PostgreSQL is unavailable") from error
