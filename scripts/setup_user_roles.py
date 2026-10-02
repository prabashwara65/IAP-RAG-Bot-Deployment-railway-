"""Add the roles column and optionally promote an existing first administrator.

Run from the project root: python -m scripts.setup_user_roles --admin-email you@example.com
This is an operator command, never a public API or signup option.
"""

import argparse
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up user roles on the application database.")
    parser.add_argument("--admin-email", help="Existing account to promote to Admin.")
    args = parser.parse_args()
    # Optional override must point to the same database used by the running app.
    database_url = os.environ.get("ROLE_DATABASE_URL")
    if not database_url:
        database_url = get_settings().database_url.get_secret_value()
    engine = create_engine(database_url, hide_parameters=True, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            if not inspector.has_table("users"):
                raise SystemExit("The users table is missing. Run your existing account migrations first.")
            columns = {column["name"] for column in inspector.get_columns("users")}
            if "role" not in columns:
                # Standard SQL supported by MySQL: every existing account becomes User.
                connection.execute(text(
                    "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"
                ))
                connection.commit()
                print("Added role column. Existing accounts start as User.")

            # Recreate the inspector after schema changes to avoid cached metadata.
            inspector = inspect(connection)
            constraint_names = {
                item["name"] for item in inspector.get_check_constraints("users")
            }
            if "ck_users_role" not in constraint_names:
                connection.execute(text(
                    "ALTER TABLE users ADD CONSTRAINT ck_users_role "
                    "CHECK (role IN ('user', 'admin', 'hr', 'employee', 'student'))"
                ))
                connection.commit()
            indexes = {item["name"] for item in inspect(connection).get_indexes("users")}
            if "ix_users_role" not in indexes:
                connection.execute(text("CREATE INDEX ix_users_role ON users (role)"))
                connection.commit()

            if args.admin_email:
                email = args.admin_email.strip().lower()
                account = connection.execute(
                    text("SELECT id FROM users WHERE LOWER(email) = :email"),
                    {"email": email},
                ).first()
                if account is None:
                    raise SystemExit(
                        "Role schema is ready, but that account was not found. "
                        "Sign up and verify the account, then rerun this command."
                    )
                connection.execute(
                    text("UPDATE users SET role = 'admin' WHERE LOWER(email) = :email"),
                    {"email": email},
                )
                connection.commit()
                print("The selected account now has Admin access. Sign in to Manage Users.")
            else:
                print("Role schema is ready. Use --admin-email to choose the first administrator.")
    except SQLAlchemyError:
        raise SystemExit(
            "Could not finish role setup. Check the database connection, schema permissions, "
            "and installed SQLAlchemy driver. You can safely rerun this command."
        ) from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()