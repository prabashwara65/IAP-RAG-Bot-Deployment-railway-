"""PostgreSQL persistence and pgvector semantic search for embedding values."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Float, Integer, cast, func, literal, select, union_all
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

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


def _rrf_contribution(
    rank_position: ColumnElement[int], *, rrf_k: int
) -> ColumnElement[float]:
    return literal(1.0, type_=Float()) / (
        literal(rrf_k, type_=Integer()) + rank_position
    )


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
        document_type: str | None = None,
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
        if document_type is not None:
            statement = statement.where(DocumentModel.document_type == document_type)

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

    def search_similar_chunks_hybrid(
        self,
        *,
        tenant_id: str,
        query_vector: Sequence[float],
        query_text: str,
        top_k: int,
        model_name: str,
        model_version: str,
        document_type: str | None = None,
        rrf_k: int = 10,
        candidate_pool: int = 50,
    ) -> tuple[SemanticSearchRecord, ...]:
        """Fuse cosine and PostgreSQL full-text ranks for eligible HR chunks."""
        if not tenant_id:
            raise SemanticSearchArgumentError("Hybrid search requires a tenant id")
        if not query_text.strip():
            raise SemanticSearchArgumentError("Hybrid search requires query text")
        if top_k <= 0:
            raise SemanticSearchArgumentError("top_k must be greater than zero")
        if candidate_pool <= 0:
            raise SemanticSearchArgumentError("candidate_pool must be greater than zero")
        if rrf_k < 0:
            raise SemanticSearchArgumentError("rrf_k must not be negative")

        values = [float(value) for value in query_vector]
        dimension = len(values)
        if dimension == 0:
            raise SemanticSearchArgumentError("The query vector must not be empty")

        eligible_statement = (
            select(
                ChunkModel.id.label("chunk_id"),
                ChunkModel.document_version_id.label("chunk_version_id"),
                ChunkModel.chunk_index.label("chunk_index"),
                ChunkModel.heading_path.label("heading_path"),
                ChunkModel.content_text.label("content_text"),
                ChunkModel.content_tsv.label("content_tsv"),
                EmbeddingModel.embedding.label("embedding"),
                EmbeddingModel.embedding_set_id.label("embedding_set_id"),
                DocumentModel.id.label("document_id"),
                DocumentModel.document_key.label("document_key"),
                DocumentModel.title.label("document_title"),
                DocumentVersionModel.id.label("document_version_id"),
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
        )
        if document_type is not None:
            eligible_statement = eligible_statement.where(
                DocumentModel.document_type == document_type
            )
        eligible = eligible_statement.cte("eligible").prefix_with("NOT MATERIALIZED")

        stable_order = (
            eligible.c.document_id,
            eligible.c.document_version_id,
            eligible.c.chunk_index,
            eligible.c.chunk_id,
        )
        vector_distance = eligible.c.embedding.cosine_distance(values)
        vector_ranked = (
            select(
                eligible.c.chunk_id,
                vector_distance.label("distance"),
                func.row_number().over(
                    order_by=(vector_distance, *stable_order)
                ).label("rank_position"),
            )
            .order_by(vector_distance, *stable_order)
            .limit(candidate_pool)
            .cte("vector_ranked")
        )

        text_query = func.plainto_tsquery("english", query_text)
        text_rank = func.ts_rank_cd(eligible.c.content_tsv, text_query, 32)
        text_ranked = (
            select(
                eligible.c.chunk_id,
                text_rank.label("text_rank"),
                func.row_number().over(
                    order_by=(text_rank.desc(), *stable_order)
                ).label("rank_position"),
            )
            .where(eligible.c.content_tsv.op("@@")(text_query))
            .order_by(text_rank.desc(), *stable_order)
            .limit(candidate_pool)
            .cte("text_ranked")
        )
        ranked_candidates = union_all(
            select(
                vector_ranked.c.chunk_id,
                vector_ranked.c.rank_position,
                vector_ranked.c.distance.label("vector_distance"),
            ),
            select(
                text_ranked.c.chunk_id,
                text_ranked.c.rank_position,
                cast(None, Float()).label("vector_distance"),
            ),
        ).cte("ranked_candidates")
        fused = (
            select(
                ranked_candidates.c.chunk_id,
                func.sum(
                    _rrf_contribution(
                        cast(ranked_candidates.c.rank_position, Integer()),
                        rrf_k=rrf_k,
                    )
                ).label("rrf_score"),
                func.max(ranked_candidates.c.vector_distance).label("distance"),
            )
            .group_by(ranked_candidates.c.chunk_id)
            .cte("fused")
        )
        statement = (
            select(
                eligible.c.chunk_id,
                eligible.c.document_id,
                eligible.c.document_version_id,
                eligible.c.embedding_set_id,
                eligible.c.document_key,
                eligible.c.document_title,
                eligible.c.chunk_index,
                eligible.c.heading_path,
                eligible.c.content_text,
                fused.c.distance,
            )
            .select_from(fused)
            .join(eligible, eligible.c.chunk_id == fused.c.chunk_id)
            .order_by(
                fused.c.rrf_score.desc(),
                eligible.c.document_id,
                eligible.c.document_version_id,
                eligible.c.chunk_index,
                eligible.c.chunk_id,
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
                distance=float(row.distance)
                if row.distance is not None
                else float("inf"),
            )
            for row in self._session.execute(statement).all()
        )