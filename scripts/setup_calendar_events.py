"""Create only calendar_events on the known legacy database, without stamping.

Run from the repository root: python -m scripts.setup_calendar_events --apply
Without --apply, inspection is read-only. Normal databases should use Alembic.
"""

from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models.events import CalendarEventModel

LEGACY_REVISION = "0006_user_roles"


def revisions(connection: Connection) -> list[str]:
    return list(
        connection.execute(
            text("SELECT version_num FROM alembic_version ORDER BY version_num")
        ).scalars()
    )


def snapshot(connection: Connection, names: list[str]) -> dict[str, Any]:
    inspector = inspect(connection)
    return {
        name: {
            "columns": [
                {**column, "type": str(column["type"])} for column in inspector.get_columns(name)
            ],
            "primary_key": inspector.get_pk_constraint(name),
            "foreign_keys": inspector.get_foreign_keys(name),
            "checks": inspector.get_check_constraints(name),
            "indexes": inspector.get_indexes(name),
            "unique": inspector.get_unique_constraints(name),
        }
        for name in names
    }


def verify_calendar(connection: Connection) -> None:
    inspector = inspect(connection)
    actual = {column["name"]: column for column in inspector.get_columns("calendar_events")}
    expected = CalendarEventModel.__table__
    if set(actual) != set(expected.columns.keys()):
        raise RuntimeError("Existing calendar columns differ; no automatic repair performed.")
    for column in expected.columns:
        found = actual[column.name]
        actual_type = found["type"].compile(dialect=connection.dialect)
        expected_type = column.type.compile(dialect=connection.dialect)
        if actual_type != expected_type or found["nullable"] != column.nullable:
            raise RuntimeError("Calendar column definitions differ; no automatic repair performed.")
    if inspector.get_pk_constraint("calendar_events")["constrained_columns"] != ["id"]:
        raise RuntimeError("Calendar primary key differs.")
    foreign_keys = inspector.get_foreign_keys("calendar_events")
    if not any(
        key["constrained_columns"] == ["user_id"]
        and key["referred_table"] == "users"
        and key["referred_columns"] == ["id"]
        and key["options"].get("ondelete") == "CASCADE"
        for key in foreign_keys
    ):
        raise RuntimeError("Calendar ownership foreign key is missing.")
    checks = {item["name"] for item in inspector.get_check_constraints("calendar_events")}
    if not {"ck_calendar_events_title", "ck_calendar_events_email_completed"} <= checks:
        raise RuntimeError("Calendar checks are missing.")
    if not any(
        index["name"] == "ix_calendar_events_user_date"
        and index["column_names"] == ["user_id", "event_date"]
        for index in inspector.get_indexes("calendar_events")
    ):
        raise RuntimeError("Calendar owner/date index is missing.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create only the calendar table.")
    args = parser.parse_args()
    engine = create_engine(
        get_settings().database_url.get_secret_value(),
        hide_parameters=True,
        poolclass=NullPool,
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.connect() as connection:
            if not args.apply:
                connection = connection.execution_options(postgresql_readonly=True)
            with connection.begin():
                current = revisions(connection)
                print("Database revisions:", current)
                inspector = inspect(connection)
                exists = inspector.has_table("calendar_events")
                print("Calendar table exists:", exists)
                if not args.apply:
                    return
                if current != [LEGACY_REVISION]:
                    raise RuntimeError(
                        "This operator command is limited to the inspected legacy revision."
                    )
                connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                connection.execute(text("SET LOCAL statement_timeout = '30s'"))
                if not connection.execute(
                    text("SELECT pg_try_advisory_xact_lock(726194002)")
                ).scalar_one():
                    raise RuntimeError("Another calendar setup is running.")
                existing_names = inspect(connection).get_table_names()
                before = snapshot(connection, existing_names)
                if not exists:
                    user_columns = {
                        column["name"]: column
                        for column in inspect(connection).get_columns("users")
                    }
                    if "id" not in user_columns or str(user_columns["id"]["type"]) != "UUID":
                        raise RuntimeError("Expected users.id UUID is missing.")
                    path = Path(__file__).resolve().parents[1] / "migrations" / "versions"
                    migration = runpy.run_path(str(path / "0009_calendar_events.py"))
                    if migration["revision"] != "0009_calendar_events":
                        raise RuntimeError("Unexpected calendar migration.")
                    with Operations.context(MigrationContext.configure(connection)):
                        migration["upgrade"]()
                verify_calendar(connection)
                if (
                    revisions(connection) != current
                    or snapshot(connection, existing_names) != before
                ):
                    raise RuntimeError(
                        "Existing schema or revision changed; calendar setup rolled back."
                    )
                after_names = set(inspect(connection).get_table_names())
                if after_names != set(existing_names) | {"calendar_events"}:
                    raise RuntimeError("Unexpected schema changes; calendar setup rolled back.")
        print("Calendar schema verified. Existing tables and Alembic revision remain unchanged.")
        print(
            "Legacy migration history still needs separate reconciliation before Alembic upgrades."
        )
    except (SQLAlchemyError, RuntimeError):
        raise SystemExit(
            "Calendar setup stopped and its transaction rolled back. "
            "Review schema, connection, and permissions. No automatic repair performed."
        ) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
