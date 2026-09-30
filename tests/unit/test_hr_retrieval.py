"""Unit tests for deterministic HR semantic retrieval orchestration."""

from collections.abc import Sequence
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from app.domain.retrieval import SemanticSearchRecord
from app.repositories.embeddings import EmbeddingRepository
from app.services.hr_retrieval import (
    DEFAULT_TOP_K,
    HRRetrievalError,
    HRRetrievalErrorCode,
    HRSemanticRetrievalResult,
    retrieve_hr_chunks,
)

TENANT_ID = "tenant-synthetic"


class _RecordingProvider:
    """Provider stub that records the texts it received, in order."""

    def __init__(
        self,
        *,
        vectors: Sequence[Sequence[object]],
        dimension: int,
        model_name: str = "stub-provider",
        model_version: str = "0.0.1",
    ) -> None:
        self._vectors = vectors
        self._dimension = dimension
        self._model_name = model_name
        self._model_version = model_version
        self.received_texts: tuple[str, ...] = ()
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.received_texts = tuple(texts)
        self.call_count += 1
        return self._vectors  # type: ignore[return-value]


def _provider(**overrides: object) -> _RecordingProvider:
    settings: dict[str, object] = {"vectors": [(0.1, 0.2)], "dimension": 2}
    settings.update(overrides)
    return _RecordingProvider(**settings)  # type: ignore[arg-type]


def _record(
    *,
    chunk_index: int,
    distance: float,
    document_id: UUID | None = None,
) -> SemanticSearchRecord:
    return SemanticSearchRecord(
        chunk_id=uuid4(),
        document_id=document_id or uuid4(),
        document_version_id=uuid4(),
        embedding_set_id=uuid4(),
        document_key=f"DOC-{chunk_index:03d}",
        document_title="Synthetic Leave Policy",
        chunk_index=chunk_index,
        heading_path=f"Synthetic Leave Policy > Section {chunk_index}",
        content_text=f"Synthetic chunk {chunk_index}.",
        distance=distance,
    )


def _repository(records: Sequence[SemanticSearchRecord] = ()) -> Mock:
    repository = Mock(spec=EmbeddingRepository)
    repository.search_similar_chunks.return_value = tuple(records)
    return repository


def test_provider_is_called_once_with_exactly_one_unchanged_query() -> None:
    provider = _provider()
    query = "  What is the synthetic leave policy?  "

    retrieve_hr_chunks(
        query=query,
        tenant_id=TENANT_ID,
        provider=provider,
        repository=_repository(),
    )

    assert provider.call_count == 1
    assert provider.received_texts == (query,)


def test_repository_receives_tenant_top_k_model_and_query_vector() -> None:
    provider = _provider(
        vectors=[(0.1, 0.2)],
        dimension=2,
        model_name="synthetic-model",
        model_version="2.1.0",
    )
    repository = _repository()

    retrieve_hr_chunks(
        query="synthetic query",
        tenant_id=TENANT_ID,
        provider=provider,
        repository=repository,
        top_k=3,
    )

    repository.search_similar_chunks.assert_called_once_with(
        tenant_id=TENANT_ID,
        query_vector=(0.1, 0.2),
        top_k=3,
        model_name="synthetic-model",
        model_version="2.1.0",
        document_type=None,
    )


def test_optional_document_type_is_forwarded_to_repository() -> None:
    repository = _repository()

    retrieve_hr_chunks(
        query="synthetic query",
        tenant_id=TENANT_ID,
        provider=_provider(),
        repository=repository,
        document_type="CV",
    )

    assert repository.search_similar_chunks.call_args.kwargs["document_type"] == "CV"


def test_default_top_k_is_applied() -> None:
    repository = _repository()

    retrieve_hr_chunks(
        query="synthetic query",
        tenant_id=TENANT_ID,
        provider=_provider(),
        repository=repository,
    )

    assert repository.search_similar_chunks.call_args.kwargs["top_k"] == DEFAULT_TOP_K
    assert DEFAULT_TOP_K == 5


def test_repository_result_order_is_preserved() -> None:
    records = (
        _record(chunk_index=7, distance=0.05),
        _record(chunk_index=2, distance=0.40),
        _record(chunk_index=4, distance=0.40),
    )

    results = retrieve_hr_chunks(
        query="synthetic query",
        tenant_id=TENANT_ID,
        provider=_provider(),
        repository=_repository(records),
    )

    assert [result.chunk_index for result in results] == [7, 2, 4]
    assert [result.distance for result in results] == [0.05, 0.40, 0.40]


def test_every_repository_field_is_mapped_onto_the_retrieval_result() -> None:
    record = _record(chunk_index=1, distance=0.25)

    (result,) = retrieve_hr_chunks(
        query="synthetic query",
        tenant_id=TENANT_ID,
        provider=_provider(),
        repository=_repository((record,)),
    )

    assert result == HRSemanticRetrievalResult(
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


def test_empty_search_results_are_valid() -> None:
    results = retrieve_hr_chunks(
        query="synthetic query",
        tenant_id=TENANT_ID,
        provider=_provider(),
        repository=_repository(),
    )

    assert results == ()


@pytest.mark.parametrize("query", ["", "   ", "\n\t "])
def test_blank_query_is_rejected(query: str) -> None:
    provider = _provider()
    repository = _repository()

    with pytest.raises(HRRetrievalError) as exc_info:
        retrieve_hr_chunks(
            query=query,
            tenant_id=TENANT_ID,
            provider=provider,
            repository=repository,
        )

    assert exc_info.value.code is HRRetrievalErrorCode.BLANK_QUERY
    assert str(exc_info.value)
    assert provider.call_count == 0
    repository.search_similar_chunks.assert_not_called()


@pytest.mark.parametrize("tenant_id", ["", "   "])
def test_blank_tenant_id_is_rejected(tenant_id: str) -> None:
    provider = _provider()
    repository = _repository()

    with pytest.raises(HRRetrievalError) as exc_info:
        retrieve_hr_chunks(
            query="synthetic query",
            tenant_id=tenant_id,
            provider=provider,
            repository=repository,
        )

    assert exc_info.value.code is HRRetrievalErrorCode.BLANK_TENANT_ID
    assert provider.call_count == 0
    repository.search_similar_chunks.assert_not_called()


@pytest.mark.parametrize("top_k", [0, -1])
def test_non_positive_top_k_is_rejected(top_k: int) -> None:
    provider = _provider()
    repository = _repository()

    with pytest.raises(HRRetrievalError) as exc_info:
        retrieve_hr_chunks(
            query="synthetic query",
            tenant_id=TENANT_ID,
            provider=provider,
            repository=repository,
            top_k=top_k,
        )

    assert exc_info.value.code is HRRetrievalErrorCode.INVALID_TOP_K
    assert provider.call_count == 0
    repository.search_similar_chunks.assert_not_called()


@pytest.mark.parametrize("dimension", [0, -1])
def test_invalid_provider_dimension_is_rejected(dimension: int) -> None:
    provider = _provider(vectors=[()], dimension=dimension)
    repository = _repository()

    with pytest.raises(HRRetrievalError) as exc_info:
        retrieve_hr_chunks(
            query="synthetic query",
            tenant_id=TENANT_ID,
            provider=provider,
            repository=repository,
        )

    assert exc_info.value.code is HRRetrievalErrorCode.INVALID_PROVIDER_DIMENSION
    assert provider.call_count == 0
    repository.search_similar_chunks.assert_not_called()


@pytest.mark.parametrize("vectors", [[], [(0.1, 0.2), (0.3, 0.4)]])
def test_provider_result_count_mismatch_is_rejected(
    vectors: list[tuple[float, ...]],
) -> None:
    repository = _repository()

    with pytest.raises(HRRetrievalError) as exc_info:
        retrieve_hr_chunks(
            query="synthetic query",
            tenant_id=TENANT_ID,
            provider=_provider(vectors=vectors),
            repository=repository,
        )

    assert exc_info.value.code is HRRetrievalErrorCode.PROVIDER_RESULT_COUNT_MISMATCH
    repository.search_similar_chunks.assert_not_called()


@pytest.mark.parametrize("vector", [(), (0.1,), (0.1, 0.2, 0.3)])
def test_query_vector_dimension_mismatch_is_rejected(
    vector: tuple[float, ...],
) -> None:
    repository = _repository()

    with pytest.raises(HRRetrievalError) as exc_info:
        retrieve_hr_chunks(
            query="synthetic query",
            tenant_id=TENANT_ID,
            provider=_provider(vectors=[vector]),
            repository=repository,
        )

    assert exc_info.value.code is HRRetrievalErrorCode.QUERY_VECTOR_DIMENSION_MISMATCH
    repository.search_similar_chunks.assert_not_called()


@pytest.mark.parametrize("component", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_query_vector_values_are_rejected(component: float) -> None:
    repository = _repository()

    with pytest.raises(HRRetrievalError) as exc_info:
        retrieve_hr_chunks(
            query="synthetic query",
            tenant_id=TENANT_ID,
            provider=_provider(vectors=[(0.1, component)]),
            repository=repository,
        )

    assert exc_info.value.code is HRRetrievalErrorCode.NON_FINITE_QUERY_VECTOR
    repository.search_similar_chunks.assert_not_called()


@pytest.mark.parametrize("component", ["0.1", None, True, complex(1, 1)])
def test_malformed_query_vector_values_are_rejected(component: object) -> None:
    repository = _repository()

    with pytest.raises(HRRetrievalError) as exc_info:
        retrieve_hr_chunks(
            query="synthetic query",
            tenant_id=TENANT_ID,
            provider=_provider(vectors=[(0.1, component)]),
            repository=repository,
        )

    assert exc_info.value.code is HRRetrievalErrorCode.MALFORMED_QUERY_VECTOR
    repository.search_similar_chunks.assert_not_called()


def test_integer_query_vector_components_are_normalized_to_floats() -> None:
    repository = _repository()

    retrieve_hr_chunks(
        query="synthetic query",
        tenant_id=TENANT_ID,
        provider=_provider(vectors=[(0, 1)]),
        repository=repository,
    )

    query_vector = repository.search_similar_chunks.call_args.kwargs["query_vector"]
    assert query_vector == (0.0, 1.0)
    assert all(isinstance(value, float) for value in query_vector)
