"""Unit tests for the OpenAI embedding provider.

Every test injects a fake client. No test in this module performs network I/O.
"""

from collections.abc import Sequence
from hashlib import sha256
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from openai import APIConnectionError, OpenAIError

from app.core.config import DEFAULT_OPENAI_EMBEDDING_MODEL, Settings
from app.domain.retrieval import SemanticSearchRecord
from app.providers.deterministic_embeddings import (
    DETERMINISTIC_EMBEDDING_MODEL_NAME,
    DeterministicEmbeddingProvider,
)
from app.providers.embeddings import EmbeddingProvider
from app.providers.openai_embeddings import (
    OPENAI_PROVIDER_NAME,
    OpenAIEmbeddingError,
    OpenAIEmbeddingErrorCode,
    OpenAIEmbeddingProvider,
    openai_embedding_provider_from_settings,
)
from app.repositories.embeddings import EmbeddingRepository
from app.services.hr_chunking import HRDocumentChunk
from app.services.hr_embedding import embed_hr_chunks
from app.services.hr_retrieval import retrieve_hr_chunks

API_KEY = "test-api-key-not-a-real-secret"
MODEL = "text-embedding-3-small"
DIMENSION = 4
VECTORS = ((0.1, 0.2, 0.3, 0.4), (0.5, 0.6, 0.7, 0.8))
TEXTS = ("First synthetic HR text.", "Second synthetic HR text.")


class _FakeEmbeddingItem:
    def __init__(self, embedding: object, index: int) -> None:
        self.embedding = embedding
        self.index = index
        self.object = "embedding"


class _FakeEmbeddingResponse:
    def __init__(self, data: object) -> None:
        self.data = data


class _FakeEmbeddings:
    def __init__(self, *, response: object, error: Exception | None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


_UNSET = object()


class _FakeOpenAIClient:
    """Minimal stand-in exposing only the `embeddings.create` surface we use."""

    def __init__(
        self,
        *,
        vectors: Sequence[Sequence[object]] = VECTORS,
        indexes: Sequence[int] | None = None,
        data: object = _UNSET,
        error: Exception | None = None,
    ) -> None:
        if data is _UNSET:
            positions = indexes if indexes is not None else range(len(vectors))
            data = [
                _FakeEmbeddingItem(embedding=list(vector), index=index)
                for vector, index in zip(vectors, positions, strict=True)
            ]
        self.embeddings = _FakeEmbeddings(
            response=_FakeEmbeddingResponse(data),
            error=error,
        )


def _provider(
    *,
    client: _FakeOpenAIClient | None = None,
    api_key: str = API_KEY,
    model: str = MODEL,
    dimension: int = DIMENSION,
) -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(
        api_key=api_key,
        model=model,
        dimension=dimension,
        client=client or _FakeOpenAIClient(),  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------
# Contract conformance and metadata
# --------------------------------------------------------------------------


def test_provider_satisfies_the_vendor_neutral_embedding_contract() -> None:
    provider: EmbeddingProvider = _provider()

    assert isinstance(provider, EmbeddingProvider)


def test_model_metadata_is_deterministic_and_matches_the_llm_provider_convention() -> None:
    provider = _provider(model="text-embedding-3-small", dimension=1536)

    assert provider.model_name == OPENAI_PROVIDER_NAME == "openai"
    assert provider.model_version == "text-embedding-3-small"
    assert provider.dimension == 1536
    twin = _provider(model="text-embedding-3-small", dimension=1536)
    assert (provider.model_name, provider.model_version, provider.dimension) == (
        twin.model_name,
        twin.model_version,
        twin.dimension,
    )


def test_surrounding_whitespace_in_the_model_name_is_ignored() -> None:
    client = _FakeOpenAIClient()

    provider = _provider(client=client, model="  text-embedding-3-small  ")
    provider.embed_texts(TEXTS)

    assert provider.model_version == "text-embedding-3-small"
    assert client.embeddings.calls[0]["model"] == "text-embedding-3-small"


def test_the_deterministic_provider_is_left_untouched() -> None:
    deterministic = DeterministicEmbeddingProvider(dimension=8)

    assert deterministic.model_name == DETERMINISTIC_EMBEDDING_MODEL_NAME
    assert deterministic.model_name != OPENAI_PROVIDER_NAME
    assert deterministic.embed_texts(["stable"]) == deterministic.embed_texts(["stable"])


# --------------------------------------------------------------------------
# Embeddings API mapping
# --------------------------------------------------------------------------


def test_the_configured_model_dimension_and_texts_are_forwarded() -> None:
    client = _FakeOpenAIClient()

    _provider(client=client).embed_texts(TEXTS)

    call = client.embeddings.calls[0]
    assert call["model"] == MODEL
    assert call["dimensions"] == DIMENSION
    assert call["input"] == list(TEXTS)
    assert set(call) == {"model", "input", "dimensions"}


def test_input_texts_are_forwarded_unchanged_and_in_order() -> None:
    texts = ["  leading and trailing spaces  ", "second", "third"]
    client = _FakeOpenAIClient(vectors=[(0.1, 0.2, 0.3, 0.4)] * 3)

    _provider(client=client).embed_texts(texts)

    assert client.embeddings.calls[0]["input"] == texts


def test_one_vector_is_returned_for_each_input_in_response_order() -> None:
    client = _FakeOpenAIClient()

    vectors = _provider(client=client).embed_texts(TEXTS)

    assert vectors == VECTORS
    assert len(vectors) == len(TEXTS)
    assert all(len(vector) == DIMENSION for vector in vectors)


def test_integer_components_are_normalized_to_floats_without_other_transformation() -> None:
    client = _FakeOpenAIClient(vectors=[(0, 1, 2, 3)])

    (vector,) = _provider(client=client).embed_texts(["one text"])

    assert vector == (0.0, 1.0, 2.0, 3.0)
    assert all(isinstance(component, float) for component in vector)


def test_the_client_is_called_exactly_once_per_embed_texts_call() -> None:
    client = _FakeOpenAIClient()
    provider = _provider(client=client)

    provider.embed_texts(TEXTS)
    assert len(client.embeddings.calls) == 1

    provider.embed_texts(TEXTS)
    assert len(client.embeddings.calls) == 2


def test_an_empty_collection_returns_no_vectors_without_calling_the_api() -> None:
    client = _FakeOpenAIClient()

    assert _provider(client=client).embed_texts([]) == ()
    assert client.embeddings.calls == []


# --------------------------------------------------------------------------
# Credential safety
# --------------------------------------------------------------------------


def test_the_api_key_is_never_stored_or_rendered_on_the_provider() -> None:
    provider = OpenAIEmbeddingProvider(api_key=API_KEY, model=MODEL, dimension=DIMENSION)

    assert API_KEY not in repr(provider)
    assert API_KEY not in str(provider)
    assert not any(value == API_KEY for value in vars(provider).values())
    assert repr(provider) == (
        f"OpenAIEmbeddingProvider(model={MODEL!r}, dimension={DIMENSION})"
    )


def test_the_sdk_failure_message_is_not_interpolated_into_the_provider_error() -> None:
    leak_marker = "credential-marker-that-must-never-be-echoed"
    client = _FakeOpenAIClient(error=OpenAIError(leak_marker))

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(TEXTS)

    assert leak_marker not in str(exc_info.value)
    assert leak_marker not in repr(exc_info.value)


# --------------------------------------------------------------------------
# Structural validation before any request
# --------------------------------------------------------------------------


@pytest.mark.parametrize("api_key", ["", "   ", "\n\t "])
def test_a_blank_api_key_is_rejected_before_any_request(api_key: str) -> None:
    client = _FakeOpenAIClient()

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client, api_key=api_key)

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.MISSING_API_KEY
    assert client.embeddings.calls == []


@pytest.mark.parametrize("model", ["", "   ", "\n\t "])
def test_a_blank_model_is_rejected_before_any_request(model: str) -> None:
    client = _FakeOpenAIClient()

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client, model=model)

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.MISSING_MODEL
    assert client.embeddings.calls == []


@pytest.mark.parametrize("dimension", [0, -1])
def test_a_non_positive_dimension_is_rejected_before_any_request(
    dimension: int,
) -> None:
    client = _FakeOpenAIClient()

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client, dimension=dimension)

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.INVALID_PROVIDER_DIMENSION
    assert client.embeddings.calls == []


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_a_blank_input_text_is_rejected_before_any_request(blank: str) -> None:
    client = _FakeOpenAIClient()

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(["valid text", blank])

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.BLANK_INPUT_TEXT
    assert exc_info.value.position == 1
    assert client.embeddings.calls == []


# --------------------------------------------------------------------------
# Transport and response validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        OpenAIError("transport failure"),
        APIConnectionError(
            request=httpx.Request("POST", "https://api.openai.com/v1/embeddings")
        ),
    ],
)
def test_an_sdk_failure_is_surfaced_as_a_provider_error(error: Exception) -> None:
    client = _FakeOpenAIClient(error=error)

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(TEXTS)

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.PROVIDER_REQUEST_FAILED
    assert exc_info.value.__cause__ is error
    assert type(error).__name__ in str(exc_info.value)


@pytest.mark.parametrize("data", [None, 42, "not-a-list", {"data": []}])
def test_a_response_without_a_data_collection_is_rejected(data: object) -> None:
    client = _FakeOpenAIClient(data=data)

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(TEXTS)

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.INVALID_PROVIDER_RESPONSE


@pytest.mark.parametrize("returned", [1, 3])
def test_a_result_count_mismatch_is_rejected(returned: int) -> None:
    client = _FakeOpenAIClient(vectors=[(0.1, 0.2, 0.3, 0.4)] * returned)

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(TEXTS)

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.PROVIDER_RESULT_COUNT_MISMATCH


def test_results_returned_out_of_input_order_are_refused_not_reordered() -> None:
    client = _FakeOpenAIClient(vectors=VECTORS, indexes=[1, 0])

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(TEXTS)

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.INVALID_PROVIDER_RESPONSE
    assert exc_info.value.position == 0


@pytest.mark.parametrize("vector", [(0.1, 0.2), (0.1, 0.2, 0.3, 0.4, 0.5), ()])
def test_a_vector_of_the_wrong_dimension_is_rejected(
    vector: tuple[float, ...],
) -> None:
    client = _FakeOpenAIClient(vectors=[vector])

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(["one text"])

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.PROVIDER_DIMENSION_MISMATCH


@pytest.mark.parametrize("component", ["0.1", None, True, complex(1, 1)])
def test_a_non_numeric_vector_component_is_rejected(component: object) -> None:
    client = _FakeOpenAIClient(vectors=[(0.1, 0.2, 0.3, component)])

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(["one text"])

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.MALFORMED_PROVIDER_VECTOR


@pytest.mark.parametrize("embedding", [None, 42, "not-a-vector"])
def test_a_non_sequence_embedding_is_rejected(embedding: object) -> None:
    client = _FakeOpenAIClient()
    client.embeddings = _FakeEmbeddings(
        response=_FakeEmbeddingResponse([_FakeEmbeddingItem(embedding, 0)]),
        error=None,
    )

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(["one text"])

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.MALFORMED_PROVIDER_VECTOR


@pytest.mark.parametrize("component", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_vector_component_is_rejected(component: float) -> None:
    client = _FakeOpenAIClient(vectors=[(0.1, 0.2, 0.3, component)])

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        _provider(client=client).embed_texts(["one text"])

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.NON_FINITE_PROVIDER_VECTOR
    assert exc_info.value.position == 0


# --------------------------------------------------------------------------
# Configuration wiring
# --------------------------------------------------------------------------


def test_the_provider_can_be_built_from_settings() -> None:
    settings = Settings(
        openai_api_key=API_KEY,  # type: ignore[arg-type]
        openai_embedding_model="text-embedding-3-small",
        embedding_dimension=1536,
    )

    provider = openai_embedding_provider_from_settings(settings)

    assert provider.model_name == "openai"
    assert provider.model_version == "text-embedding-3-small"
    assert provider.dimension == 1536
    assert API_KEY not in repr(provider)


def test_building_from_settings_without_a_key_fails_before_any_request() -> None:
    settings = Settings(
        openai_api_key=None,
        openai_embedding_model=DEFAULT_OPENAI_EMBEDDING_MODEL,
    )

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        openai_embedding_provider_from_settings(settings)

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.MISSING_API_KEY


# --------------------------------------------------------------------------
# Compatibility with the existing HR services
# --------------------------------------------------------------------------


def _chunk(index: int, content: str) -> HRDocumentChunk:
    return HRDocumentChunk(
        chunk_index=index,
        heading_path=f"Synthetic Policy > Section {index}",
        content_text=content,
        content_hash=sha256(content.encode("utf-8")).hexdigest(),
    )


def test_the_provider_drives_the_existing_hr_chunk_embedding_service() -> None:
    chunks = (_chunk(0, TEXTS[0]), _chunk(1, TEXTS[1]))
    client = _FakeOpenAIClient()

    embeddings = embed_hr_chunks(chunks, _provider(client=client))

    assert client.embeddings.calls[0]["input"] == [chunk.content_text for chunk in chunks]
    assert [embedding.chunk_index for embedding in embeddings] == [0, 1]
    assert [embedding.values for embedding in embeddings] == list(VECTORS)
    assert [embedding.content_hash for embedding in embeddings] == [
        chunk.content_hash for chunk in chunks
    ]


def test_the_provider_drives_the_existing_hr_retrieval_service() -> None:
    question = "How much annual leave does an employee receive?"
    client = _FakeOpenAIClient(vectors=[(0.11, 0.22, 0.33, 0.44)])
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

    assert client.embeddings.calls[0]["input"] == [question]
    repository.search_similar_chunks.assert_called_once_with(
        tenant_id="tenant-synthetic",
        query_vector=(0.11, 0.22, 0.33, 0.44),
        top_k=3,
        model_name="openai",
        model_version=MODEL,
    )
    assert [result.chunk_id for result in results] == [record.chunk_id]


def test_a_provider_failure_never_becomes_an_empty_retrieval_result() -> None:
    client = _FakeOpenAIClient(error=OpenAIError("transport failure"))
    repository = Mock(spec=EmbeddingRepository)

    with pytest.raises(OpenAIEmbeddingError) as exc_info:
        retrieve_hr_chunks(
            query="How much annual leave does an employee receive?",
            tenant_id="tenant-synthetic",
            provider=_provider(client=client),
            repository=repository,
        )

    assert exc_info.value.code is OpenAIEmbeddingErrorCode.PROVIDER_REQUEST_FAILED
    repository.search_similar_chunks.assert_not_called()
