"""Unit tests for deterministic HR chunk embedding generation and persistence."""

from collections.abc import Sequence
from hashlib import sha256
from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from app.providers.deterministic_embeddings import DeterministicEmbeddingProvider
from app.repositories.embeddings import EmbeddingRepository
from app.schemas.hr_documents import HRDocumentMetadata
from app.services.hr_chunking import HRDocumentChunk, chunk_hr_markdown
from app.services.hr_embedding import (
    HRChunkEmbedding,
    HREmbeddingError,
    HREmbeddingErrorCode,
    embed_hr_chunks,
    persist_hr_chunk_embeddings,
)
from app.services.hr_markdown import render_hr_document_markdown


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


def _chunk(index: int, content: str) -> HRDocumentChunk:
    return HRDocumentChunk(
        chunk_index=index,
        heading_path=f"Synthetic Document > Section {index}",
        content_text=content,
        content_hash=sha256(content.encode("utf-8")).hexdigest(),
    )


def _chunks() -> tuple[HRDocumentChunk, ...]:
    return (
        _chunk(0, "First synthetic chunk."),
        _chunk(1, "Second synthetic chunk."),
        _chunk(2, "Third synthetic chunk."),
    )


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


def _repository(embedding_ids: Sequence[UUID]) -> Mock:
    repository = Mock(spec=EmbeddingRepository)
    repository.add_embedding.side_effect = list(embedding_ids)
    return repository


def test_provider_receives_chunk_content_text_in_chunk_order() -> None:
    chunks = _chunks()
    provider = _RecordingProvider(vectors=[(0.1, 0.2)] * len(chunks), dimension=2)

    embed_hr_chunks(chunks, provider)

    assert provider.call_count == 1
    assert provider.received_texts == tuple(chunk.content_text for chunk in chunks)


def test_chunk_order_and_identity_are_preserved_in_the_output() -> None:
    chunks = _chunks()
    provider = _RecordingProvider(
        vectors=[(0.1, 0.2), (0.3, 0.4), (0.5, 0.6)],
        dimension=2,
    )

    embeddings = embed_hr_chunks(chunks, provider)

    assert len(embeddings) == len(chunks)
    assert [embedding.chunk_index for embedding in embeddings] == [0, 1, 2]
    assert [embedding.content_hash for embedding in embeddings] == [
        chunk.content_hash for chunk in chunks
    ]
    assert [embedding.values for embedding in embeddings] == [
        (0.1, 0.2),
        (0.3, 0.4),
        (0.5, 0.6),
    ]


def test_integer_components_are_normalized_to_floats() -> None:
    provider = _RecordingProvider(vectors=[(0, 1)], dimension=2)

    (embedding,) = embed_hr_chunks((_chunk(0, "Synthetic chunk."),), provider)

    assert embedding.values == (0.0, 1.0)
    assert all(isinstance(value, float) for value in embedding.values)


def test_same_chunks_and_deterministic_provider_produce_identical_records() -> None:
    chunks = _chunks()
    provider = DeterministicEmbeddingProvider(dimension=16)

    assert embed_hr_chunks(chunks, provider) == embed_hr_chunks(chunks, provider)


def test_chunked_markdown_embeds_without_database_or_network_access() -> None:
    document = HRDocumentMetadata.model_validate(_valid_payload())
    chunks = chunk_hr_markdown(render_hr_document_markdown(document))
    provider = DeterministicEmbeddingProvider(dimension=8)

    embeddings = embed_hr_chunks(chunks, provider)

    assert len(embeddings) == len(chunks)
    assert all(len(embedding.values) == provider.dimension for embedding in embeddings)
    assert len({embedding.values for embedding in embeddings}) == len(embeddings)


def test_empty_chunk_input_is_rejected() -> None:
    provider = DeterministicEmbeddingProvider(dimension=4)

    with pytest.raises(HREmbeddingError) as exc_info:
        embed_hr_chunks((), provider)

    assert exc_info.value.code is HREmbeddingErrorCode.EMPTY_CHUNKS
    assert str(exc_info.value)


@pytest.mark.parametrize("dimension", [0, -1])
def test_invalid_provider_dimension_is_rejected(dimension: int) -> None:
    provider = _RecordingProvider(vectors=[()], dimension=dimension)

    with pytest.raises(HREmbeddingError) as exc_info:
        embed_hr_chunks((_chunk(0, "Synthetic chunk."),), provider)

    assert exc_info.value.code is HREmbeddingErrorCode.INVALID_PROVIDER_DIMENSION
    assert provider.call_count == 0


@pytest.mark.parametrize("vectors", [[], [(0.1, 0.2)], [(0.1, 0.2)] * 3])
def test_provider_result_count_mismatch_is_rejected(
    vectors: list[tuple[float, ...]],
) -> None:
    chunks = (_chunk(0, "First."), _chunk(1, "Second."))
    provider = _RecordingProvider(vectors=vectors, dimension=2)

    with pytest.raises(HREmbeddingError) as exc_info:
        embed_hr_chunks(chunks, provider)

    assert exc_info.value.code is HREmbeddingErrorCode.PROVIDER_RESULT_COUNT_MISMATCH


@pytest.mark.parametrize("vector", [(), (0.1,), (0.1, 0.2, 0.3)])
def test_vector_dimension_mismatch_is_rejected(vector: tuple[float, ...]) -> None:
    provider = _RecordingProvider(vectors=[vector], dimension=2)

    with pytest.raises(HREmbeddingError) as exc_info:
        embed_hr_chunks((_chunk(0, "Synthetic chunk."),), provider)

    assert exc_info.value.code is HREmbeddingErrorCode.VECTOR_DIMENSION_MISMATCH
    assert exc_info.value.chunk_index == 0


@pytest.mark.parametrize(
    "component",
    [float("nan"), float("inf"), float("-inf")],
)
def test_non_finite_vector_values_are_rejected(component: float) -> None:
    chunks = (_chunk(0, "First."), _chunk(1, "Second."))
    provider = _RecordingProvider(vectors=[(0.1, 0.2), (0.3, component)], dimension=2)

    with pytest.raises(HREmbeddingError) as exc_info:
        embed_hr_chunks(chunks, provider)

    assert exc_info.value.code is HREmbeddingErrorCode.NON_FINITE_VECTOR_VALUE
    assert exc_info.value.chunk_index == 1


@pytest.mark.parametrize("component", ["0.1", None, True, complex(1, 1)])
def test_malformed_vector_values_are_rejected(component: object) -> None:
    provider = _RecordingProvider(vectors=[(0.1, component)], dimension=2)

    with pytest.raises(HREmbeddingError) as exc_info:
        embed_hr_chunks((_chunk(0, "Synthetic chunk."),), provider)

    assert exc_info.value.code is HREmbeddingErrorCode.MALFORMED_VECTOR_VALUE


def test_persistence_delegates_every_embedding_to_the_repository_in_order() -> None:
    embeddings = (
        HRChunkEmbedding(chunk_index=0, content_hash="hash-0", values=(0.1, 0.2)),
        HRChunkEmbedding(chunk_index=1, content_hash="hash-1", values=(0.3, 0.4)),
    )
    chunk_ids = {0: uuid4(), 1: uuid4()}
    embedding_set_id = uuid4()
    embedding_ids = (uuid4(), uuid4())
    repository = _repository(embedding_ids)

    persisted = persist_hr_chunk_embeddings(
        repository,
        embedding_set_id=embedding_set_id,
        embeddings=embeddings,
        chunk_ids=chunk_ids,
    )

    assert persisted == embedding_ids
    assert [call.kwargs for call in repository.add_embedding.call_args_list] == [
        {
            "chunk_id": chunk_ids[0],
            "embedding_set_id": embedding_set_id,
            "values": (0.1, 0.2),
        },
        {
            "chunk_id": chunk_ids[1],
            "embedding_set_id": embedding_set_id,
            "values": (0.3, 0.4),
        },
    ]


def test_persistence_uses_the_supplied_mapping_instead_of_positional_order() -> None:
    embeddings = (
        HRChunkEmbedding(chunk_index=5, content_hash="hash-5", values=(0.1,)),
        HRChunkEmbedding(chunk_index=2, content_hash="hash-2", values=(0.2,)),
    )
    chunk_ids = {2: uuid4(), 5: uuid4()}
    repository = _repository((uuid4(), uuid4()))

    persist_hr_chunk_embeddings(
        repository,
        embedding_set_id=uuid4(),
        embeddings=embeddings,
        chunk_ids=chunk_ids,
    )

    assert [call.kwargs["chunk_id"] for call in repository.add_embedding.call_args_list] == [
        chunk_ids[5],
        chunk_ids[2],
    ]


def test_persistence_rejects_empty_embeddings() -> None:
    repository = _repository(())

    with pytest.raises(HREmbeddingError) as exc_info:
        persist_hr_chunk_embeddings(
            repository,
            embedding_set_id=uuid4(),
            embeddings=(),
            chunk_ids={},
        )

    assert exc_info.value.code is HREmbeddingErrorCode.EMPTY_EMBEDDINGS
    repository.add_embedding.assert_not_called()


def test_persistence_rejects_a_missing_chunk_id_without_writing_anything() -> None:
    embeddings = (
        HRChunkEmbedding(chunk_index=0, content_hash="hash-0", values=(0.1,)),
        HRChunkEmbedding(chunk_index=1, content_hash="hash-1", values=(0.2,)),
    )
    repository = _repository((uuid4(),))

    with pytest.raises(HREmbeddingError) as exc_info:
        persist_hr_chunk_embeddings(
            repository,
            embedding_set_id=uuid4(),
            embeddings=embeddings,
            chunk_ids={0: uuid4()},
        )

    assert exc_info.value.code is HREmbeddingErrorCode.CHUNK_ID_MISSING
    assert exc_info.value.chunk_index == 1
    repository.add_embedding.assert_not_called()


def test_persistence_rejects_a_duplicated_chunk_index() -> None:
    embedding = HRChunkEmbedding(chunk_index=0, content_hash="hash-0", values=(0.1,))
    repository = _repository((uuid4(),))

    with pytest.raises(HREmbeddingError) as exc_info:
        persist_hr_chunk_embeddings(
            repository,
            embedding_set_id=uuid4(),
            embeddings=(embedding, embedding),
            chunk_ids={0: uuid4()},
        )

    assert exc_info.value.code is HREmbeddingErrorCode.DUPLICATE_CHUNK_INDEX
    repository.add_embedding.assert_not_called()


def test_persistence_rejects_one_chunk_id_mapped_to_several_chunk_indexes() -> None:
    chunk_id = uuid4()
    embeddings = (
        HRChunkEmbedding(chunk_index=0, content_hash="hash-0", values=(0.1,)),
        HRChunkEmbedding(chunk_index=1, content_hash="hash-1", values=(0.2,)),
    )
    repository = _repository((uuid4(),))

    with pytest.raises(HREmbeddingError) as exc_info:
        persist_hr_chunk_embeddings(
            repository,
            embedding_set_id=uuid4(),
            embeddings=embeddings,
            chunk_ids={0: chunk_id, 1: chunk_id},
        )

    assert exc_info.value.code is HREmbeddingErrorCode.DUPLICATE_CHUNK_ID
    repository.add_embedding.assert_not_called()
