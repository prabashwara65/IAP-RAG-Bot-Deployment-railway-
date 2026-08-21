"""PostgreSQL mappings for the Phase 1 document foundation."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentModel(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_key", name="uq_documents_tenant_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(120), nullable=False)
    document_key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentVersionModel(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "version_label", name="uq_document_versions_document_label"
        ),
        UniqueConstraint(
            "document_id", "content_hash", name="uq_document_versions_document_hash"
        ),
        CheckConstraint(
            "status IN ('candidate', 'approved', 'active', 'superseded', 'archived', 'failed')",
            name="ck_document_versions_status",
        ),
        CheckConstraint(
            "status NOT IN ('approved', 'active') OR approved_at IS NOT NULL",
            name="ck_document_versions_approval_time",
        ),
        Index(
            "uq_document_versions_one_active",
            "document_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="candidate"
    )
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    source_path: Mapped[str | None] = mapped_column(String(500))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChunkModel(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id", "chunk_index", name="uq_chunks_version_index"
        ),
        UniqueConstraint(
            "document_version_id", "content_hash", name="uq_chunks_version_hash"
        ),
        CheckConstraint("chunk_index >= 0", name="ck_chunks_index_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EmbeddingSetModel(Base):
    __tablename__ = "embedding_sets"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "model_name",
            "model_version",
            name="uq_embedding_sets_version_model",
        ),
        CheckConstraint("dimension > 0", name="ck_embedding_sets_dimension_positive"),
        CheckConstraint(
            "status IN ('candidate', 'active', 'archived', 'failed')",
            name="ck_embedding_sets_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(120), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="candidate"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EmbeddingModel(Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "embedding_set_id", name="uq_embeddings_chunk_set"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    chunk_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    embedding_set_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("embedding_sets.id", ondelete="CASCADE"), nullable=False
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApprovalDecisionModel(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved', 'rejected', 'changes_requested')",
            name="ck_approval_decisions_decision",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_actor_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_notes: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEventModel(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("jsonb_typeof(metadata) = 'object'", name="ck_audit_metadata_object"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    actor_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome_status: Mapped[str] = mapped_column(String(80), nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
