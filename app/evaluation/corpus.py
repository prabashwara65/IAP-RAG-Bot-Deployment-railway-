"""Publish the synthetic evaluation corpus into PostgreSQL through the real pipeline.

Documents travel the production path: deterministic validation, standardized
Markdown rendering, deterministic chunking, embedding, and pgvector
persistence. Only the document, version, and chunk rows are written directly,
because the platform still has no chunk repository; that gap is unchanged by
this module.

This loader is for synthetic evaluation corpora only. It activates document
versions without a human approval decision, so it must never be pointed at a
tenant holding real HR content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.domain.documents import DocumentVersionStatus, EmbeddingSetStatus
from app.evaluation.hr_cases import HR_EVALUATION_DOCUMENTS, HREvaluationDocument
from app.models.documents import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    EmbeddingSetModel,
)
from app.providers.embeddings import EmbeddingProvider
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.services.hr_chunking import chunk_hr_markdown
from app.services.hr_embedding import embed_hr_chunks, persist_hr_chunk_embeddings
from app.services.hr_markdown import render_hr_document_markdown


@dataclass(frozen=True, slots=True)
class LoadedEvaluationCorpus:
    """What the loader wrote, for assertions and reporting."""

    tenant_id: str
    document_count: int
    chunk_count: int
    chunk_texts_by_document_key: dict[str, tuple[str, ...]]


def load_hr_evaluation_corpus(
    session: Session,
    *,
    tenant_id: str,
    embedding_provider: EmbeddingProvider,
    documents: tuple[HREvaluationDocument, ...] = HR_EVALUATION_DOCUMENTS,
) -> LoadedEvaluationCorpus:
    """Publish every synthetic evaluation document as an active, embedded version."""
    repository = PostgresEmbeddingRepository(session)
    now = datetime.now(UTC)
    chunk_texts_by_document_key: dict[str, tuple[str, ...]] = {}
    chunk_count = 0

    for document in documents:
        metadata_document_type = getattr(document.metadata, "document_type", "Other")
        document_model = DocumentModel(
            tenant_id=tenant_id,
            document_key=document.document_key,
            title=document.metadata.document_title,
            document_type=getattr(metadata_document_type, "value", metadata_document_type),
        )
        session.add(document_model)
        session.flush()

        version = DocumentVersionModel(
            document_id=document_model.id,
            version_label=document.metadata.version,
            status=DocumentVersionStatus.ACTIVE.value,
            content_hash=f"evaluation-content-hash-{document.document_key}",
            approved_at=now,
            activated_at=now,
        )
        session.add(version)
        session.flush()

        chunks = chunk_hr_markdown(render_hr_document_markdown(document.metadata))
        chunk_models = [
            ChunkModel(
                document_version_id=version.id,
                chunk_index=chunk.chunk_index,
                heading_path=chunk.heading_path,
                content_text=chunk.content_text,
                content_hash=chunk.content_hash,
            )
            for chunk in chunks
        ]
        embedding_set = EmbeddingSetModel(
            document_version_id=version.id,
            model_name=embedding_provider.model_name,
            model_version=embedding_provider.model_version,
            dimension=embedding_provider.dimension,
            status=EmbeddingSetStatus.ACTIVE.value,
        )
        session.add_all([*chunk_models, embedding_set])
        session.flush()

        persist_hr_chunk_embeddings(
            repository,
            embedding_set_id=embedding_set.id,
            embeddings=embed_hr_chunks(chunks, embedding_provider),
            chunk_ids={model.chunk_index: model.id for model in chunk_models},
        )

        chunk_texts_by_document_key[document.document_key] = tuple(
            chunk.content_text for chunk in chunks
        )
        chunk_count += len(chunks)

    session.flush()
    return LoadedEvaluationCorpus(
        tenant_id=tenant_id,
        document_count=len(documents),
        chunk_count=chunk_count,
        chunk_texts_by_document_key=chunk_texts_by_document_key,
    )
