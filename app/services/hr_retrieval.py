"""Deterministic HR semantic retrieval over persisted chunk embeddings.

The service embeds one query through the configured provider and delegates the
vector search to the repository. It performs no answer generation, no prompt
construction, no reranking, and no language-model call.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.retrieval import SemanticSearchRecord
from app.providers.embeddings import EmbeddingProvider
from app.repositories.embeddings import EmbeddingRepository
from app.services.vector_validation import (
    VectorIssue,
    VectorValidationError,
    validate_vector,
)

DEFAULT_TOP_K = 5


class HRRetrievalErrorCode(StrEnum):
    """Stable retrieval failure codes for later API and agent layers."""

    BLANK_QUERY = "blank_query"
    BLANK_TENANT_ID = "blank_tenant_id"
    INVALID_TOP_K = "invalid_top_k"
    INVALID_PROVIDER_DIMENSION = "invalid_provider_dimension"
    PROVIDER_RESULT_COUNT_MISMATCH = "provider_result_count_mismatch"
    QUERY_VECTOR_DIMENSION_MISMATCH = "query_vector_dimension_mismatch"
    MALFORMED_QUERY_VECTOR = "malformed_query_vector"
    NON_FINITE_QUERY_VECTOR = "non_finite_query_vector"


class HRRetrievalError(ValueError):
    """Raised when an HR semantic retrieval request cannot be served safely."""

    def __init__(self, code: HRRetrievalErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class HRSemanticRetrievalResult:
    """One retrieved HR chunk with the context a caller needs to cite it."""

    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    embedding_set_id: UUID
    document_key: str
    document_title: str
    chunk_index: int
    heading_path: str
    content_text: str
    distance: float


_QUERY_VECTOR_ISSUE_CODES: dict[VectorIssue, HRRetrievalErrorCode] = {
    VectorIssue.DIMENSION_MISMATCH: HRRetrievalErrorCode.QUERY_VECTOR_DIMENSION_MISMATCH,
    VectorIssue.MALFORMED_VALUE: HRRetrievalErrorCode.MALFORMED_QUERY_VECTOR,
    VectorIssue.NON_FINITE_VALUE: HRRetrievalErrorCode.NON_FINITE_QUERY_VECTOR,
}


def _to_result(record: SemanticSearchRecord) -> HRSemanticRetrievalResult:
    return HRSemanticRetrievalResult(
        chunk_id=record.chunk_id,
        document_id=record.document_id,
        document_version_id=record.document_version_id,
        embedding_set_id=record.embedding_set_id,
        document_key=record.document_key,
        document_title=record.document_title,
        chunk_index=record.chunk_index,
        heading_path=record.heading_path,
        content_text=record.content_text,
        distance=record.distance,
    )


def embed_hr_query(query: str, provider: EmbeddingProvider) -> tuple[float, ...]:
    """Embed exactly one query string and validate the returned vector.

    The query text reaches the provider unchanged so a caller can reproduce the
    vector from the original input.
    """
    if not query.strip():
        raise HRRetrievalError(
            HRRetrievalErrorCode.BLANK_QUERY,
            "The retrieval query must contain non-whitespace characters.",
        )

    dimension = provider.dimension
    if dimension <= 0:
        raise HRRetrievalError(
            HRRetrievalErrorCode.INVALID_PROVIDER_DIMENSION,
            "Embedding provider dimension must be greater than zero.",
        )

    vectors = tuple(provider.embed_texts((query,)))
    if len(vectors) != 1:
        raise HRRetrievalError(
            HRRetrievalErrorCode.PROVIDER_RESULT_COUNT_MISMATCH,
            f"Provider returned {len(vectors)} vectors for one query.",
        )

    try:
        return validate_vector(vectors[0], dimension=dimension)
    except VectorValidationError as error:
        raise HRRetrievalError(
            _QUERY_VECTOR_ISSUE_CODES[error.issue],
            str(error),
        ) from error


def retrieve_hr_chunks(
    *,
    query: str,
    tenant_id: str,
    provider: EmbeddingProvider,
    repository: EmbeddingRepository,
    top_k: int = DEFAULT_TOP_K,
    document_type: str | None = None,
) -> tuple[HRSemanticRetrievalResult, ...]:
    """Return the closest active HR chunks for one tenant, closest first.

    Repository ordering is preserved exactly; the service never reorders,
    reranks, or filters the matches it receives.
    """
    if not tenant_id.strip():
        raise HRRetrievalError(
            HRRetrievalErrorCode.BLANK_TENANT_ID,
            "The retrieval tenant id must contain non-whitespace characters.",
        )
    if top_k <= 0:
        raise HRRetrievalError(
            HRRetrievalErrorCode.INVALID_TOP_K,
            "top_k must be greater than zero.",
        )

    query_vector = embed_hr_query(query, provider)
    records = repository.search_similar_chunks(
        tenant_id=tenant_id,
        query_vector=query_vector,
        top_k=top_k,
        model_name=provider.model_name,
        model_version=provider.model_version,
        document_type=document_type,
    )
    return tuple(_to_result(record) for record in records)
