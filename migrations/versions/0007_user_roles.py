"""Add roles to users.

Revision ID: 0007_user_roles
Revises: 0006_hybrid_search
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007_user_roles"
down_revision: str | None = "0006_hybrid_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="user",
        ),
    )

    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('user', 'admin', 'hr', 'employee', 'student')",
    )

    op.create_index(
        "ix_users_role",
        "users",
        ["role"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_role", table_name="users")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")
