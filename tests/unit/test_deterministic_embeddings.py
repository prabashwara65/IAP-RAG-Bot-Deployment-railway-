"""Tests for the deterministic, dependency-free embedding provider."""

from math import isfinite, sqrt

import pytest

from app.providers.deterministic_embeddings import (
    DEFAULT_DETERMINISTIC_EMBEDDING_DIMENSION,
    DETERMINISTIC_EMBEDDING_MODEL_NAME,
    DETERMINISTIC_EMBEDDING_MODEL_VERSION,
    DeterministicEmbeddingProvider,
)
from app.providers.embeddings import EmbeddingProvider


def test_provider_satisfies_the_embedding_provider_contract() -> None:
    provider: EmbeddingProvider = DeterministicEmbeddingProvider()

    assert isinstance(provider, EmbeddingProvider)


def test_provider_reports_model_name_version_and_dimension() -> None:
    provider = DeterministicEmbeddingProvider()

    assert provider.model_name == DETERMINISTIC_EMBEDDING_MODEL_NAME
    assert provider.model_version == DETERMINISTIC_EMBEDDING_MODEL_VERSION
    assert provider.dimension == DEFAULT_DETERMINISTIC_EMBEDDING_DIMENSION
    assert provider.dimension > 0


def test_same_input_produces_the_same_vector() -> None:
    provider = DeterministicEmbeddingProvider(dimension=16)

    assert provider.embed_texts(["synthetic policy text"]) == provider.embed_texts(
        ["synthetic policy text"]
    )


def test_separate_provider_instances_produce_the_same_vector() -> None:
    first = DeterministicEmbeddingProvider(dimension=16)
    second = DeterministicEmbeddingProvider(dimension=16)

    assert first.embed_texts(["synthetic policy text"]) == second.embed_texts(
        ["synthetic policy text"]
    )


def test_different_input_produces_different_vectors() -> None:
    provider = DeterministicEmbeddingProvider(dimension=16)

    first, second = provider.embed_texts(["first synthetic text", "second synthetic text"])

    assert first != second


def test_vectors_are_returned_in_input_order() -> None:
    provider = DeterministicEmbeddingProvider(dimension=8)
    texts = ["alpha", "beta", "gamma"]

    vectors = provider.embed_texts(texts)

    assert len(vectors) == len(texts)
    assert vectors == tuple(provider.embed_texts([text])[0] for text in texts)


def test_every_component_is_a_finite_float_within_the_unit_range() -> None:
    provider = DeterministicEmbeddingProvider(dimension=32)

    (vector,) = provider.embed_texts(["synthetic policy text"])

    assert len(vector) == provider.dimension
    assert all(isinstance(component, float) for component in vector)
    assert all(isfinite(component) for component in vector)
    assert all(-1.0 <= component <= 1.0 for component in vector)


def test_vectors_are_normalized_to_unit_length() -> None:
    provider = DeterministicEmbeddingProvider(dimension=32)

    (vector,) = provider.embed_texts(["synthetic policy text"])

    assert sqrt(sum(component * component for component in vector)) == pytest.approx(1.0)


def test_dimension_is_configurable() -> None:
    provider = DeterministicEmbeddingProvider(dimension=3)

    (vector,) = provider.embed_texts(["synthetic policy text"])

    assert provider.dimension == 3
    assert len(vector) == 3


def test_dimension_changes_the_derived_vector() -> None:
    short = DeterministicEmbeddingProvider(dimension=4).embed_texts(["shared text"])[0]
    long_vector = DeterministicEmbeddingProvider(dimension=8).embed_texts(["shared text"])[0]

    assert short != long_vector[:4]


def test_empty_input_returns_no_vectors() -> None:
    assert DeterministicEmbeddingProvider(dimension=4).embed_texts([]) == ()


def test_empty_text_is_embedded_deterministically() -> None:
    provider = DeterministicEmbeddingProvider(dimension=4)

    assert provider.embed_texts([""]) == provider.embed_texts([""])
    assert provider.embed_texts([""]) != provider.embed_texts([" "])


def test_derivation_is_stable_across_processes_and_releases() -> None:
    """Guards the hashlib-based derivation against accidental, silent changes."""
    (vector,) = DeterministicEmbeddingProvider(dimension=4).embed_texts(["alpha"])

    assert vector == pytest.approx(
        (0.49358912828590046, -0.6162962791802924, 0.49351326116208283, 0.36468250542582614)
    )


@pytest.mark.parametrize("dimension", [0, -1])
def test_non_positive_dimension_is_rejected(dimension: int) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        DeterministicEmbeddingProvider(dimension=dimension)
