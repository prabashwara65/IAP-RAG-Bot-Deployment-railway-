"""Add saved_chats table for saving user conversations.

Revision ID: 0006_saved_chats
Revises: 0005_document_type
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_saved_chats"
down_revision: str | None = "0005_document_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='saved_chats'"
        )
    ).fetchone()
    if exists is None:
        op.create_table(
            "saved_chats",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=False),
            sa.Column("messages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name="pk_saved_chats"),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                name="fk_saved_chats_user_id_users",
                ondelete="CASCADE",
            ),
        )
        op.create_index(
            "ix_saved_chats_user_id",
            "saved_chats",
            ["user_id"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='saved_chats'"
        )
    ).fetchone()
    if exists is not None:
        op.drop_index("ix_saved_chats_user_id", table_name="saved_chats")
        op.drop_table("saved_chats")
