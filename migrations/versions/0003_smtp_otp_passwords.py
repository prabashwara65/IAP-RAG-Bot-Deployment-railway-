"""Create password hashes and Gmail SMTP-backed 2FA columns.

Revision ID: 0003_smtp_otp_passwords
Revises: 0002_user_accounts
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_smtp_otp_passwords"
down_revision: str | None = "0002_user_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_hash",
            sa.String(length=255),
            nullable=False,
            server_default="!",
        ),
    )
    op.alter_column("users", "password_hash", server_default=None)
    op.add_column(
        "otp_challenges",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("otp_challenges", "password_hash")
    op.drop_column("users", "password_hash")
