"""Add roles to users.

Revision ID: 0008_user_roles
Revises: 0007_merge_heads
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "0008_user_roles"
down_revision: str | None = "0007_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # Add role column only if missing
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    if "role" not in user_cols:
        op.add_column(
            "users",
            sa.Column(
                "role",
                sa.String(length=20),
                nullable=False,
                server_default="user",
            ),
        )

    # Add check constraint only if missing
    constraint_names = {c["name"] for c in inspector.get_check_constraints("users")}
    if "ck_users_role" not in constraint_names:
        op.create_check_constraint(
            "ck_users_role",
            "users",
            "role IN ('user', 'admin', 'hr', 'employee', 'student')",
        )

    # Add index only if missing
    index_names = {i["name"] for i in inspector.get_indexes("users")}
    if "ix_users_role" not in index_names:
        op.create_index(
            "ix_users_role",
            "users",
            ["role"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    index_names = {i["name"] for i in inspector.get_indexes("users")}
    if "ix_users_role" in index_names:
        op.drop_index("ix_users_role", table_name="users")

    constraint_names = {c["name"] for c in inspector.get_check_constraints("users")}
    if "ck_users_role" in constraint_names:
        op.drop_constraint("ck_users_role", "users", type_="check")

    user_cols = {c["name"] for c in inspector.get_columns("users")}
    if "role" in user_cols:
        op.drop_column("users", "role")