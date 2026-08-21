"""Integration tests for HR chunk embedding persistence against PostgreSQL/pgvector."""

from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.database import create_session_factory, session_scope
from app.models.documents import ChunkModel, EmbeddingModel, EmbeddingSetModel
from app.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from app.repositories.postgres.documents import PostgresDocumentRepository
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.schemas.hr_documents import HRDocumentMetadata
from app.services.hr_chunking import chunk_hr_markdown
from app.services.hr_embedding import (
    HREmbeddingError,
    HREmbeddingErrorCode,
    embed_hr_chunks,
    persist_hr_chunk_embeddings,
)
from app.services.hr_markdown import render_hr_document_markdown

EMBEDDING_DIMENSION = 8


def _valid_payload() -> dict[str, Any]:
    return {
        "document_title": "Synthetic Leave Policy",
        "document_type": "Policy",
        "department": "Human Resources",
        "summary_purpose": "Explains synthetic leave rules for demonstration.",
        "language": "English",
        "version": "1.0",
        "effective_date": "2026-08-01",
        "content_owner": "Synthetic HR Team",
        "approval_status": "Approved",
        "approved_for_rag": "Approved",
        "document_status": "Approved",
        "access_level": "Internal General",
        "contains_personal_data": "No",
        "contains_confidential_data": "No",
        "synthetic": True,
        "official_company_document": False,
        "data_mode": "synthetic_demo",
        "document_content": "This is synthetic HR policy content.",
    }


def _prepare_version(
    session: Session,
    *,
    document_key: str,
    provider: DeterministicEmbeddingProvider,
) -> tuple[dict[int, Any], EmbeddingSetModel, tuple[Any, ...]]:
    document_repository = PostgresDocumentRepository(session)
    document = document_repository.create_document(
        tenant_id="tenant-test",
        document_key=document_key,
        title="Synthetic Leave Policy",
    )
    version = document_repository.create_candidate_version(
        document_id=document.id,
        version_label="1.0",
        content_hash=f"content-hash-{document_key}",
    )

    metadata = HRDocumentMetadata.model_validate(_valid_payload())
    chunks = chunk_hr_markdown(render_hr_document_markdown(metadata))
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
        model_name=provider.model_name,
        model_version=provider.model_version,
        dimension=provider.dimension,
        status="candidate",
    )
    session.add_all([*chunk_models, embedding_set])
    session.flush()

    chunk_ids = {model.chunk_index: model.id for model in chunk_models}
    return chunk_ids, embedding_set, chunks


def test_generated_hr_chunk_embeddings_are_persisted_for_every_chunk(
    migrated_engine: Engine,
) -> None:
    provider = DeterministicEmbeddingProvider(dimension=EMBEDDING_DIMENSION)
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        chunk_ids, embedding_set, chunks = _prepare_version(
            session,
            document_key="DOC-EMBED-001",
            provider=provider,
        )
        embeddings = embed_hr_chunks(chunks, provider)

        embedding_ids = persist_hr_chunk_embeddings(
            PostgresEmbeddingRepository(session),
            embedding_set_id=embedding_set.id,
            embeddings=embeddings,
            chunk_ids=chunk_ids,
        )

        assert len(embedding_ids) == len(chunks)
        assert len(set(embedding_ids)) == len(chunks)
        for embedding, embedding_id in zip(embeddings, embedding_ids, strict=True):
            stored = session.get(EmbeddingModel, embedding_id)
            assert stored is not None
            assert stored.chunk_id == chunk_ids[embedding.chunk_index]
            assert stored.embedding_set_id == embedding_set.id
            assert list(stored.embedding) == pytest.approx(list(embedding.values))


def test_persistence_is_rejected_before_any_write_when_a_chunk_id_is_missing(
    migrated_engine: Engine,
) -> None:
    provider = DeterministicEmbeddingProvider(dimension=EMBEDDING_DIMENSION)
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        chunk_ids, embedding_set, chunks = _prepare_version(
            session,
            document_key="DOC-EMBED-002",
            provider=provider,
        )
        embeddings = embed_hr_chunks(chunks, provider)
        incomplete_chunk_ids = {
            index: chunk_id
            for index, chunk_id in chunk_ids.items()
            if index != chunks[-1].chunk_index
        }

        with pytest.raises(HREmbeddingError) as exc_info:
            persist_hr_chunk_embeddings(
                PostgresEmbeddingRepository(session),
                embedding_set_id=embedding_set.id,
                embeddings=embeddings,
                chunk_ids=incomplete_chunk_ids,
            )

        assert exc_info.value.code is HREmbeddingErrorCode.CHUNK_ID_MISSING
        session.flush()
        stored = session.scalars(
            select(EmbeddingModel).where(
                EmbeddingModel.embedding_set_id == embedding_set.id
            )
        ).all()
        assert stored == []
