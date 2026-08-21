"""Deterministic HR chunk embedding generation and persistence orchestration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.providers.embeddings import EmbeddingProvider
from app.repositories.embeddings import EmbeddingRepository
from app.services.hr_chunking import HRDocumentChunk
from app.services.vector_validation import (
    VectorIssue,
    VectorValidationError,
    validate_vector,
)


class HREmbeddingErrorCode(StrEnum):
    """Stable embedding failure codes for later API and agent layers."""

    EMPTY_CHUNKS = "empty_chunks"
    INVALID_PROVIDER_DIMENSION = "invalid_provider_dimension"
    PROVIDER_RESULT_COUNT_MISMATCH = "provider_result_count_mismatch"
    VECTOR_DIMENSION_MISMATCH = "vector_dimension_mismatch"
    MALFORMED_VECTOR_VALUE = "malformed_vector_value"
    NON_FINITE_VECTOR_VALUE = "non_finite_vector_value"
    EMPTY_EMBEDDINGS = "empty_embeddings"
    DUPLICATE_CHUNK_INDEX = "duplicate_chunk_index"
    CHUNK_ID_MISSING = "chunk_id_missing"
    DUPLICATE_CHUNK_ID = "duplicate_chunk_id"


class HREmbeddingError(ValueError):
    """Raised when HR chunk embeddings cannot be produced or persisted safely."""

    def __init__(
        self,
        code: HREmbeddingErrorCode,
        message: str,
        *,
        chunk_index: int | None = None,
    ) -> None:
        self.code = code
        self.chunk_index = chunk_index
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class HRChunkEmbedding:
    """One validated vector bound to the chunk identity that produced it."""

    chunk_index: int
    content_hash: str
    values: tuple[float, ...]


_VECTOR_ISSUE_CODES: dict[VectorIssue, HREmbeddingErrorCode] = {
    VectorIssue.DIMENSION_MISMATCH: HREmbeddingErrorCode.VECTOR_DIMENSION_MISMATCH,
    VectorIssue.MALFORMED_VALUE: HREmbeddingErrorCode.MALFORMED_VECTOR_VALUE,
    VectorIssue.NON_FINITE_VALUE: HREmbeddingErrorCode.NON_FINITE_VECTOR_VALUE,
}


def _validated_vector(
    vector: Sequence[object],
    *,
    dimension: int,
    chunk_index: int,
) -> tuple[float, ...]:
    try:
        return validate_vector(vector, dimension=dimension)
    except VectorValidationError as error:
        raise HREmbeddingError(
            _VECTOR_ISSUE_CODES[error.issue],
            str(error),
            chunk_index=chunk_index,
        ) from error


def embed_hr_chunks(
    chunks: Sequence[HRDocumentChunk],
    provider: EmbeddingProvider,
) -> tuple[HRChunkEmbedding, ...]:
    """Generate one validated vector per chunk without any database or network I/O.

    Chunk order is preserved, the provider receives ``content_text`` in chunk
    order, and every returned vector is validated against ``provider.dimension``
    before it is exposed to callers.
    """
    if not chunks:
        raise HREmbeddingError(
            HREmbeddingErrorCode.EMPTY_CHUNKS,
            "At least one HR document chunk is required to generate embeddings.",
        )

    dimension = provider.dimension
    if dimension <= 0:
        raise HREmbeddingError(
            HREmbeddingErrorCode.INVALID_PROVIDER_DIMENSION,
            "Embedding provider dimension must be greater than zero.",
        )

    texts = tuple(chunk.content_text for chunk in chunks)
    vectors = tuple(provider.embed_texts(texts))
    if len(vectors) != len(chunks):
        raise HREmbeddingError(
            HREmbeddingErrorCode.PROVIDER_RESULT_COUNT_MISMATCH,
            f"Provider returned {len(vectors)} vectors for {len(chunks)} chunks.",
        )

    return tuple(
        HRChunkEmbedding(
            chunk_index=chunk.chunk_index,
            content_hash=chunk.content_hash,
            values=_validated_vector(
                vector,
                dimension=dimension,
                chunk_index=chunk.chunk_index,
            ),
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    )


def persist_hr_chunk_embeddings(
    repository: EmbeddingRepository,
    *,
    embedding_set_id: UUID,
    embeddings: Sequence[HRChunkEmbedding],
    chunk_ids: Mapping[int, UUID],
) -> tuple[UUID, ...]:
    """Persist generated vectors through the embedding repository contract.

    In-memory chunks carry no database identity, so the caller must supply an
    explicit ``chunk_index -> persisted chunk id`` mapping. No positional or
    ordinal relationship between generated chunks and stored rows is assumed.
    The whole request is validated before the first write so a rejected request
    persists nothing. Dimension, ownership, and storage rules stay in the
    repository implementation.
    """
    if not embeddings:
        raise HREmbeddingError(
            HREmbeddingErrorCode.EMPTY_EMBEDDINGS,
            "At least one generated embedding is required for persistence.",
        )

    resolved: list[tuple[UUID, HRChunkEmbedding]] = []
    seen_indexes: set[int] = set()
    seen_chunk_ids: set[UUID] = set()
    for embedding in embeddings:
        if embedding.chunk_index in seen_indexes:
            raise HREmbeddingError(
                HREmbeddingErrorCode.DUPLICATE_CHUNK_INDEX,
                "Each chunk index may be embedded at most once per embedding set.",
                chunk_index=embedding.chunk_index,
            )
        seen_indexes.add(embedding.chunk_index)

        chunk_id = chunk_ids.get(embedding.chunk_index)
        if chunk_id is None:
            raise HREmbeddingError(
                HREmbeddingErrorCode.CHUNK_ID_MISSING,
                "No persisted chunk id was supplied for the chunk index.",
                chunk_index=embedding.chunk_index,
            )
        if chunk_id in seen_chunk_ids:
            raise HREmbeddingError(
                HREmbeddingErrorCode.DUPLICATE_CHUNK_ID,
                "Each persisted chunk id may be mapped to at most one chunk index.",
                chunk_index=embedding.chunk_index,
            )
        seen_chunk_ids.add(chunk_id)
        resolved.append((chunk_id, embedding))

    return tuple(
        repository.add_embedding(
            chunk_id=chunk_id,
            embedding_set_id=embedding_set_id,
            values=embedding.values,
        )
        for chunk_id, embedding in resolved
    )
