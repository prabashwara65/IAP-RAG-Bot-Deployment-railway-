"""Add generic document type metadata and tenant/type index.

Revision ID: 0005_document_type
Revises: 0004_totp_two_factor
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_document_type"
down_revision: str | None = "0004_totp_two_factor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("document_type", sa.String(length=80), nullable=True),
    )
    op.execute("UPDATE documents SET document_type = 'Other' WHERE document_type IS NULL")
    op.alter_column("documents", "document_type", nullable=False)
    op.create_index(
        "ix_documents_tenant_document_type",
        "documents",
        ["tenant_id", "document_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_tenant_document_type", table_name="documents")
    op.drop_column("documents", "document_type")