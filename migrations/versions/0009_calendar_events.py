"""Create owner-scoped calendar events.

Revision ID: 0009_calendar_events
Revises: 0008_user_roles
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_calendar_events"
down_revision: str | None = "0008_user_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.Time(timezone=False), nullable=True),
        sa.Column("completed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("cancelled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "confirmation_email_sent",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calendar_events"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_calendar_events_user_id_users",
        ),
        sa.CheckConstraint(
            "length(trim(title)) BETWEEN 1 AND 200",
            name="ck_calendar_events_title",
        ),
        sa.CheckConstraint(
            "NOT confirmation_email_sent OR completed",
            name="ck_calendar_events_email_completed",
        ),
    )
    op.create_index("ix_calendar_events_user_date", "calendar_events", ["user_id", "event_date"])


def downgrade() -> None:
    # Destructive to calendar data only. Never run against company data casually.
    op.drop_index("ix_calendar_events_user_date", table_name="calendar_events")
    op.drop_table("calendar_events")
