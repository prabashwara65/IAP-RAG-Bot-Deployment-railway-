"""merge hybrid_search and saved_chats heads

Revision ID: 255b7f56af2b
Revises: 0006_hybrid_search, 0006_saved_chats
Create Date: 2026-10-02 16:53:54.045779
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '0007_merge_hybrid_and_saved_chats'
down_revision: str | None = ('0006_hybrid_search', '0006_saved_chats')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
