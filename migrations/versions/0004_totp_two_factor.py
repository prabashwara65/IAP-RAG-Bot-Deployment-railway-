"""Store the account's single two-factor method and authenticator secret.

Revision ID: 0004_totp_two_factor
Revises: 0003_smtp_otp_passwords
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_totp_two_factor"
down_revision: str | None = "0003_smtp_otp_passwords"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "two_factor_method",
            sa.String(length=20),
            nullable=False,
            server_default="email_otp",
        ),
    )
    op.add_column("users", sa.Column("totp_secret", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_pending_secret", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_users_two_factor_method",
        "users",
        "two_factor_method IN ('none', 'email_otp', 'totp')",
    )
    op.drop_constraint("ck_otp_challenges_purpose", "otp_challenges", type_="check")
    op.create_check_constraint(
        "ck_otp_challenges_purpose",
        "otp_challenges",
        "purpose IN ('signup', 'login', 'totp_login')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_otp_challenges_purpose", "otp_challenges", type_="check")
    op.create_check_constraint(
        "ck_otp_challenges_purpose",
        "otp_challenges",
        "purpose IN ('signup', 'login')",
    )
    op.drop_constraint("ck_users_two_factor_method", "users", type_="check")
    op.drop_column("users", "totp_pending_secret")
    op.drop_column("users", "totp_secret")
    op.drop_column("users", "two_factor_method")
