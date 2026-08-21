"""PostgreSQL persistence and pgvector semantic search for embedding values."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.documents import DocumentVersionStatus, EmbeddingSetStatus
from app.domain.retrieval import SemanticSearchRecord
from app.models.documents import (
    ChunkModel,
    DocumentModel,
    DocumentVersionModel,
    EmbeddingModel,
    EmbeddingSetModel,
)


class EmbeddingCompatibilityError(ValueError):
    """Raised when an embedding cannot belong to the requested set."""


class SemanticSearchArgumentError(ValueError):
    """Raised when a semantic search request cannot be executed safely."""


class PostgresEmbeddingRepository:
    """Persist vectors only after deterministic dimension and ownership checks."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_embedding(
        self,
        *,
        chunk_id: UUID,
        embedding_set_id: UUID,
        values: Sequence[float],
    ) -> UUID:
        chunk = self._session.get(ChunkModel, chunk_id)
        embedding_set = self._session.get(EmbeddingSetModel, embedding_set_id)
        if chunk is None or embedding_set is None:
            raise EmbeddingCompatibilityError("Chunk or embedding set does not exist")
        if chunk.document_version_id != embedding_set.document_version_id:
            raise EmbeddingCompatibilityError(
                "Chunk and embedding set must belong to the same document version"
            )
        if len(values) != embedding_set.dimension:
            raise EmbeddingCompatibilityError(
                "Embedding dimension does not match the embedding set"
            )

        model = EmbeddingModel(
            chunk_id=chunk_id,
            embedding_set_id=embedding_set_id,
            embedding=[float(value) for value in values],
        )
        self._session.add(model)
        self._session.flush()
        return model.id

    def search_similar_chunks(
        self,
        *,
        tenant_id: str,
        query_vector: Sequence[float],
        top_k: int,
        model_name: str,
        model_version: str,
    ) -> tuple[SemanticSearchRecord, ...]:
        """Rank chunks by pgvector cosine distance inside PostgreSQL.

        Only active embedding sets of active document versions are searchable.
        Every candidate row is filtered before the distance is ordered, so the
        cosine operator only ever sees embedding sets of the query dimension.
        """
        if not tenant_id:
            raise SemanticSearchArgumentError("Semantic search requires a tenant id")
        if top_k <= 0:
            raise SemanticSearchArgumentError("top_k must be greater than zero")

        values = [float(value) for value in query_vector]
        dimension = len(values)
        if dimension == 0:
            raise SemanticSearchArgumentError("The query vector must not be empty")

        distance = EmbeddingModel.embedding.cosine_distance(values).label("distance")
        statement = (
            select(
                ChunkModel.id.label("chunk_id"),
                DocumentModel.id.label("document_id"),
                DocumentVersionModel.id.label("document_version_id"),
                EmbeddingModel.embedding_set_id.label("embedding_set_id"),
                DocumentModel.document_key.label("document_key"),
                DocumentModel.title.label("document_title"),
                ChunkModel.chunk_index.label("chunk_index"),
                ChunkModel.heading_path.label("heading_path"),
                ChunkModel.content_text.label("content_text"),
                distance,
            )
            .select_from(EmbeddingModel)
            .join(ChunkModel, ChunkModel.id == EmbeddingModel.chunk_id)
            .join(
                EmbeddingSetModel,
                EmbeddingSetModel.id == EmbeddingModel.embedding_set_id,
            )
            .join(
                DocumentVersionModel,
                DocumentVersionModel.id == ChunkModel.document_version_id,
            )
            .join(DocumentModel, DocumentModel.id == DocumentVersionModel.document_id)
            .where(
                DocumentModel.tenant_id == tenant_id,
                DocumentVersionModel.status == DocumentVersionStatus.ACTIVE.value,
                EmbeddingSetModel.status == EmbeddingSetStatus.ACTIVE.value,
                EmbeddingSetModel.model_name == model_name,
                EmbeddingSetModel.model_version == model_version,
                EmbeddingSetModel.dimension == dimension,
                EmbeddingSetModel.document_version_id
                == ChunkModel.document_version_id,
            )
            .order_by(
                distance,
                DocumentModel.id,
                DocumentVersionModel.id,
                ChunkModel.chunk_index,
                ChunkModel.id,
            )
            .limit(top_k)
        )

        return tuple(
            SemanticSearchRecord(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                document_version_id=row.document_version_id,
                embedding_set_id=row.embedding_set_id,
                document_key=row.document_key,
                document_title=row.document_title,
                chunk_index=row.chunk_index,
                heading_path=row.heading_path,
                content_text=row.content_text,
                distance=float(row.distance),
            )
            for row in self._session.execute(statement).all()
        )
