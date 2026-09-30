"""PostgreSQL persistence tests for uploaded document chunks and vectors."""

from sqlalchemy import select

from app.core.database import create_session_factory, session_scope
from app.domain.documents import DocumentVersionStatus, EmbeddingSetStatus
from app.models.documents import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    EmbeddingModel,
    EmbeddingSetModel,
)
from app.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from app.services.document_ingestion import ingest_document, persist_ingested_document


def test_ingested_chunks_and_embeddings_are_stored_as_candidate(migrated_engine) -> None:
    provider = DeterministicEmbeddingProvider(dimension=8)
    factory = create_session_factory(migrated_engine)
    with session_scope(factory) as session:
        document = ingest_document(
            "travel-policy.txt",
            b"Travel must be approved.\n\nReceipts are required.",
        )
        persisted = persist_ingested_document(
            session,
            tenant_id="tenant-synthetic",
            content=b"Travel must be approved.\n\nReceipts are required.",
            document=document,
            embedding_provider=provider,
        )

        stored_document = session.scalar(
            select(DocumentModel).where(DocumentModel.document_key == persisted.document_key)
        )
        version = session.get(DocumentVersionModel, persisted.version_id)
        chunks = session.scalars(
            select(ChunkModel).where(
                ChunkModel.document_version_id == persisted.version_id
            ).order_by(ChunkModel.chunk_index)
        ).all()
        embedding_set = session.scalar(
            select(EmbeddingSetModel).where(
                EmbeddingSetModel.document_version_id == persisted.version_id
            )
        )
        embeddings = session.scalars(
            select(EmbeddingModel).where(
                EmbeddingModel.embedding_set_id == embedding_set.id
            )
        ).all()

        assert stored_document is not None
        assert stored_document.title == "travel-policy.txt"
        assert version is not None
        assert version.status == DocumentVersionStatus.CANDIDATE.value
        assert persisted.version_status is DocumentVersionStatus.CANDIDATE
        assert [chunk.content_text for chunk in chunks] == [
            "Travel must be approved.",
            "Receipts are required.",
        ]
        assert embedding_set is not None
        assert embedding_set.status == EmbeddingSetStatus.CANDIDATE.value
        assert len(embeddings) == len(chunks) == persisted.chunk_count
        assert all(len(embedding.embedding) == provider.dimension for embedding in embeddings)