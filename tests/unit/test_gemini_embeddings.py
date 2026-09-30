"""Unit tests for the Gemini embedding provider.

Every test injects a fake client. No test in this module performs network I/O.
"""

from collections.abc import Sequence
from hashlib import sha256
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.config import DEFAULT_GEMINI_EMBEDDING_MODEL, Settings
from app.domain.retrieval import SemanticSearchRecord
from app.providers.deterministic_embeddings import (
    DETERMINISTIC_EMBEDDING_MODEL_NAME,
    DeterministicEmbeddingProvider,
)
from app.providers.embeddings import EmbeddingProvider
from app.providers.gemini_embeddings import (
    GEMINI_PROVIDER_NAME,
    GeminiEmbeddingError,
    GeminiEmbeddingErrorCode,
    GeminiEmbeddingProvider,
    gemini_embedding_provider_from_settings,
)
from app.repositories.embeddings import EmbeddingRepository
from app.services.hr_chunking import HRDocumentChunk
from app.services.hr_embedding import embed_hr_chunks
from app.services.hr_retrieval import retrieve_hr_chunks

API_KEY = "test-api-key-not-a-real-secret"
MODEL = "gemini-embedding-001"
DIMENSION = 4
VECTORS = ((0.1, 0.2, 0.3, 0.4), (0.5, 0.6, 0.7, 0.8))
TEXTS = ("First synthetic HR text.", "Second synthetic HR text.")


class _FakeEmbeddingItem:
    def __init__(self, values: object) -> None:
        self.values = values


class _FakeEmbeddingResponse:
    def __init__(self, embeddings: object) -> None:
        self.embeddings = embeddings


class _FakeModels:
    def __init__(self, *, response: object, error: Exception | None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def embed_content(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


_UNSET = object()


class _FakeGeminiClient:
    """Minimal stand-in exposing only the `models.embed_content` surface we use."""

    def __init__(
        self,
        *,
        vectors: Sequence[Sequence[object]] = VECTORS,
        embeddings: object = _UNSET,
        error: Exception | None = None,
    ) -> None:
        if embeddings is _UNSET:
            embeddings = [_FakeEmbeddingItem(values=list(vector)) for vector in vectors]
        self.models = _FakeModels(
            response=_FakeEmbeddingResponse(embeddings),
            error=error,
        )


def _provider(
    *,
    client: _FakeGeminiClient | None = None,
    api_key: str = API_KEY,
    model: str = MODEL,
    dimension: int = DIMENSION,
) -> GeminiEmbeddingProvider:
    return GeminiEmbeddingProvider(
        api_key=api_key,
        model=model,
        dimension=dimension,
        client=client or _FakeGeminiClient(),
    )


def test_provider_satisfies_the_vendor_neutral_embedding_contract() -> None:
    provider: EmbeddingProvider = _provider()

    assert isinstance(provider, EmbeddingProvider)


def test_model_metadata_is_deterministic_and_matches_the_llm_provider_convention() -> None:
    provider = _provider(model="gemini-embedding-001", dimension=768)

    assert provider.model_name == GEMINI_PROVIDER_NAME == "gemini"
    assert provider.model_version == "gemini-embedding-001"
    assert provider.dimension == 768
    twin = _provider(model="gemini-embedding-001", dimension=768)
    assert (provider.model_name, provider.model_version, provider.dimension) == (
        twin.model_name,
        twin.model_version,
        twin.dimension,
    )


def test_surrounding_whitespace_in_the_model_name_is_ignored() -> None:
    client = _FakeGeminiClient()

    provider = _provider(client=client, model="  gemini-embedding-001  ")
    provider.embed_texts(TEXTS)

    assert provider.model_version == "gemini-embedding-001"
    assert client.models.calls[0]["model"] == "gemini-embedding-001"


def test_the_deterministic_provider_is_left_untouched() -> None:
    deterministic = DeterministicEmbeddingProvider(dimension=8)

    assert deterministic.model_name == DETERMINISTIC_EMBEDDING_MODEL_NAME
    assert deterministic.model_name != GEMINI_PROVIDER_NAME
    assert deterministic.embed_texts(["stable"]) == deterministic.embed_texts(["stable"])


def test_the_configured_model_dimension_and_texts_are_forwarded() -> None:
    client = _FakeGeminiClient()

    _provider(client=client).embed_texts(TEXTS)

    call = client.models.calls[0]
    assert call["model"] == MODEL
    assert call["config"].output_dimensionality == DIMENSION
    assert call["contents"] == list(TEXTS)
    assert set(call) == {"model", "contents", "config"}


def test_input_texts_are_forwarded_unchanged_and_in_order() -> None:
    texts = ["  leading and trailing spaces  ", "second", "third"]
    client = _FakeGeminiClient(vectors=[(0.1, 0.2, 0.3, 0.4)] * 3)

    _provider(client=client).embed_texts(texts)

    assert client.models.calls[0]["contents"] == texts


def test_one_vector_is_returned_for_each_input_in_response_order() -> None:
    client = _FakeGeminiClient()

    vectors = _provider(client=client).embed_texts(TEXTS)

    assert vectors == VECTORS
    assert len(vectors) == len(TEXTS)
    assert all(len(vector) == DIMENSION for vector in vectors)


def test_integer_components_are_normalized_to_floats_without_other_transformation() -> None:
    client = _FakeGeminiClient(vectors=[(0, 1, 2, 3)])

    (vector,) = _provider(client=client).embed_texts(["one text"])

    assert vector == (0.0, 1.0, 2.0, 3.0)
    assert all(isinstance(component, float) for component in vector)


def test_the_client_is_called_exactly_once_per_embed_texts_call() -> None:
    client = _FakeGeminiClient()
    provider = _provider(client=client)

    provider.embed_texts(TEXTS)
    assert len(client.models.calls) == 1

    provider.embed_texts(TEXTS)
    assert len(client.models.calls) == 2


def test_an_empty_collection_returns_no_vectors_without_calling_the_api() -> None:
    client = _FakeGeminiClient()

    assert _provider(client=client).embed_texts([]) == ()
    assert client.models.calls == []


def test_the_api_key_is_never_stored_or_rendered_on_the_provider() -> None:
    provider = GeminiEmbeddingProvider(api_key=API_KEY, model=MODEL, dimension=DIMENSION)

    assert API_KEY not in repr(provider)
    assert API_KEY not in str(provider)
    assert not any(value == API_KEY for value in vars(provider).values())
    assert repr(provider) == (
        f"GeminiEmbeddingProvider(model={MODEL!r}, dimension={DIMENSION})"
    )


def test_the_sdk_failure_message_is_not_interpolated_into_the_provider_error() -> None:
    leak_marker = "credential-marker-that-must-never-be-echoed"
    client = _FakeGeminiClient(error=RuntimeError(leak_marker))

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(TEXTS)

    assert leak_marker not in str(exc_info.value)
    assert leak_marker not in repr(exc_info.value)


@pytest.mark.parametrize("api_key", ["", "   ", "\n\t "])
def test_a_blank_api_key_is_rejected_before_any_request(api_key: str) -> None:
    client = _FakeGeminiClient()

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client, api_key=api_key)

    assert exc_info.value.code is GeminiEmbeddingErrorCode.MISSING_API_KEY
    assert client.models.calls == []


@pytest.mark.parametrize("model", ["", "   ", "\n\t "])
def test_a_blank_model_is_rejected_before_any_request(model: str) -> None:
    client = _FakeGeminiClient()

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client, model=model)

    assert exc_info.value.code is GeminiEmbeddingErrorCode.MISSING_MODEL
    assert client.models.calls == []


@pytest.mark.parametrize("dimension", [0, -1])
def test_a_non_positive_dimension_is_rejected_before_any_request(
    dimension: int,
) -> None:
    client = _FakeGeminiClient()

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client, dimension=dimension)

    assert exc_info.value.code is GeminiEmbeddingErrorCode.INVALID_PROVIDER_DIMENSION
    assert client.models.calls == []


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_a_blank_input_text_is_rejected_before_any_request(blank: str) -> None:
    client = _FakeGeminiClient()

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(["valid text", blank])

    assert exc_info.value.code is GeminiEmbeddingErrorCode.BLANK_INPUT_TEXT
    assert exc_info.value.position == 1
    assert client.models.calls == []


def test_an_sdk_failure_is_surfaced_as_a_provider_error() -> None:
    error = RuntimeError("transport failure")
    client = _FakeGeminiClient(error=error)

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(TEXTS)

    assert exc_info.value.code is GeminiEmbeddingErrorCode.PROVIDER_REQUEST_FAILED
    assert exc_info.value.__cause__ is error
    assert type(error).__name__ in str(exc_info.value)


@pytest.mark.parametrize("embeddings", [None, 42, "not-a-list", {"embeddings": []}])
def test_a_response_without_an_embeddings_collection_is_rejected(
    embeddings: object,
) -> None:
    client = _FakeGeminiClient(embeddings=embeddings)

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(TEXTS)

    assert exc_info.value.code is GeminiEmbeddingErrorCode.INVALID_PROVIDER_RESPONSE


@pytest.mark.parametrize("returned", [1, 3])
def test_a_result_count_mismatch_is_rejected(returned: int) -> None:
    client = _FakeGeminiClient(vectors=[(0.1, 0.2, 0.3, 0.4)] * returned)

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(TEXTS)

    assert exc_info.value.code is GeminiEmbeddingErrorCode.PROVIDER_RESULT_COUNT_MISMATCH


@pytest.mark.parametrize("vector", [(0.1, 0.2), (0.1, 0.2, 0.3, 0.4, 0.5), ()])
def test_a_vector_of_the_wrong_dimension_is_rejected(
    vector: tuple[float, ...],
) -> None:
    client = _FakeGeminiClient(vectors=[vector])

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(["one text"])

    assert exc_info.value.code is GeminiEmbeddingErrorCode.PROVIDER_DIMENSION_MISMATCH


@pytest.mark.parametrize("component", ["0.1", None, True, complex(1, 1)])
def test_a_non_numeric_vector_component_is_rejected(component: object) -> None:
    client = _FakeGeminiClient(vectors=[(0.1, 0.2, 0.3, component)])

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(["one text"])

    assert exc_info.value.code is GeminiEmbeddingErrorCode.MALFORMED_PROVIDER_VECTOR


@pytest.mark.parametrize("values", [None, 42, "not-a-vector"])
def test_a_non_sequence_embedding_is_rejected(values: object) -> None:
    client = _FakeGeminiClient()
    client.models = _FakeModels(
        response=_FakeEmbeddingResponse([_FakeEmbeddingItem(values)]),
        error=None,
    )

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(["one text"])

    assert exc_info.value.code is GeminiEmbeddingErrorCode.MALFORMED_PROVIDER_VECTOR


@pytest.mark.parametrize("component", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_vector_component_is_rejected(component: float) -> None:
    client = _FakeGeminiClient(vectors=[(0.1, 0.2, 0.3, component)])

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(["one text"])

    assert exc_info.value.code is GeminiEmbeddingErrorCode.NON_FINITE_PROVIDER_VECTOR
    assert exc_info.value.position == 0


def test_the_provider_can_be_built_from_settings() -> None:
    settings = Settings(
        gemini_api_key=API_KEY,  # type: ignore[arg-type]
        gemini_embedding_model="gemini-embedding-001",
        embedding_dimension=768,
    )

    provider = gemini_embedding_provider_from_settings(settings)

    assert provider.model_name == "gemini"
    assert provider.model_version == "gemini-embedding-001"
    assert provider.dimension == 768
    assert API_KEY not in repr(provider)


def test_building_from_settings_without_a_key_fails_before_any_request() -> None:
    settings = Settings(
        gemini_api_key=None,
        gemini_embedding_model=DEFAULT_GEMINI_EMBEDDING_MODEL,
    )

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        gemini_embedding_provider_from_settings(settings)

    assert exc_info.value.code is GeminiEmbeddingErrorCode.MISSING_API_KEY


def _chunk(index: int, content: str) -> HRDocumentChunk:
    return HRDocumentChunk(
        chunk_index=index,
        heading_path=f"Synthetic Policy > Section {index}",
        content_text=content,
        content_hash=sha256(content.encode("utf-8")).hexdigest(),
    )


def test_the_provider_drives_the_existing_hr_chunk_embedding_service() -> None:
    chunks = (_chunk(0, TEXTS[0]), _chunk(1, TEXTS[1]))
    client = _FakeGeminiClient()

    embeddings = embed_hr_chunks(chunks, _provider(client=client))

    assert client.models.calls[0]["contents"] == [chunk.content_text for chunk in chunks]
    assert [embedding.chunk_index for embedding in embeddings] == [0, 1]
    assert [embedding.values for embedding in embeddings] == list(VECTORS)
    assert [embedding.content_hash for embedding in embeddings] == [
        chunk.content_hash for chunk in chunks
    ]


def test_the_provider_drives_the_existing_hr_retrieval_service() -> None:
    question = "How much annual leave does an employee receive?"
    client = _FakeGeminiClient(vectors=[(0.11, 0.22, 0.33, 0.44)])
    record = SemanticSearchRecord(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        embedding_set_id=uuid4(),
        document_key="HR-SYNTHETIC-001",
        document_title="Synthetic Policy",
        chunk_index=0,
        heading_path="Synthetic Policy > Section 0",
        content_text="Synthetic policy content.",
        distance=0.1,
    )
    repository = Mock(spec=EmbeddingRepository)
    repository.search_similar_chunks.return_value = (record,)

    results = retrieve_hr_chunks(
        query=question,
        tenant_id="tenant-synthetic",
        provider=_provider(client=client),
        repository=repository,
        top_k=3,
    )

    assert client.models.calls[0]["contents"] == [question]
    repository.search_similar_chunks.assert_called_once_with(
        tenant_id="tenant-synthetic",
        query_vector=(0.11, 0.22, 0.33, 0.44),
        top_k=3,
        model_name="gemini",
        model_version=MODEL,
        document_type=None,
    )
    assert [result.chunk_id for result in results] == [record.chunk_id]


def test_a_provider_failure_never_becomes_an_empty_retrieval_result() -> None:
    client = _FakeGeminiClient(error=RuntimeError("transport failure"))
    repository = Mock(spec=EmbeddingRepository)

    with pytest.raises(GeminiEmbeddingError) as exc_info:
        retrieve_hr_chunks(
            query="How much annual leave does an employee receive?",
            tenant_id="tenant-synthetic",
            provider=_provider(client=client),
            repository=repository,
        )

    assert exc_info.value.code is GeminiEmbeddingErrorCode.PROVIDER_REQUEST_FAILED
    repository.search_similar_chunks.assert_not_called()
