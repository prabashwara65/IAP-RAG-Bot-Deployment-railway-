"""Create the Phase 1 PostgreSQL and pgvector document foundation.

Revision ID: 0001_phase1_document_foundation
Revises: None
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase1_document_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable pgvector and create the initial document schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=120), nullable=False),
        sa.Column("document_key", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint(
            "tenant_id", "document_key", name="uq_documents_tenant_key"
        ),
    )

    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_label", sa.String(length=80), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="candidate", nullable=False
        ),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("source_path", sa.String(length=500), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'approved', 'active', 'superseded', 'archived', 'failed')",
            name="ck_document_versions_status",
        ),
        sa.CheckConstraint(
            "status NOT IN ('approved', 'active') OR approved_at IS NOT NULL",
            name="ck_document_versions_approval_time",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.UniqueConstraint(
            "document_id",
            "version_label",
            name="uq_document_versions_document_label",
        ),
        sa.UniqueConstraint(
            "document_id",
            "content_hash",
            name="uq_document_versions_document_hash",
        ),
    )
    op.create_index(
        "uq_document_versions_one_active",
        "document_versions",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_version_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.String(length=500), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_chunks_index_nonnegative"),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunks"),
        sa.UniqueConstraint(
            "document_version_id", "chunk_index", name="uq_chunks_version_index"
        ),
        sa.UniqueConstraint(
            "document_version_id", "content_hash", name="uq_chunks_version_hash"
        ),
    )

    op.create_table(
        "embedding_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_version_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("model_version", sa.String(length=120), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="candidate", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dimension > 0", name="ck_embedding_sets_dimension_positive"
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'active', 'archived', 'failed')",
            name="ck_embedding_sets_status",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_embedding_sets"),
        sa.UniqueConstraint(
            "document_version_id",
            "model_name",
            "model_version",
            name="uq_embedding_sets_version_model",
        ),
    )

    op.create_table(
        "embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["embedding_set_id"], ["embedding_sets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_embeddings"),
        sa.UniqueConstraint(
            "chunk_id", "embedding_set_id", name="uq_embeddings_chunk_set"
        ),
    )

    op.create_table(
        "approval_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "document_version_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("reviewer_actor_ref", sa.String(length=200), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason_notes", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('approved', 'rejected', 'changes_requested')",
            name="ck_approval_decisions_decision",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_decisions"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_ref", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("target_entity_type", sa.String(length=80), nullable=False),
        sa.Column("target_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("outcome_status", sa.String(length=80), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'", name="ck_audit_metadata_object"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )


def downgrade() -> None:
    """Remove OIAP-owned tables while retaining the shared vector extension."""
    op.drop_table("audit_events")
    op.drop_table("approval_decisions")
    op.drop_table("embeddings")
    op.drop_table("embedding_sets")
    op.drop_table("chunks")
    op.drop_index(
        "uq_document_versions_one_active", table_name="document_versions"
    )
    op.drop_table("document_versions")
    op.drop_table("documents")
