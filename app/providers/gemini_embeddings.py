"""Gemini implementation of the vendor-neutral embedding provider contract.

This module is the only place in the platform that knows how Gemini produces
vectors. The chunk embedding and retrieval services depend on
``EmbeddingProvider`` alone, so adding or swapping a vendor never reaches them.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from google import genai
from google.genai import types

from app.core.config import Settings
from app.services.vector_validation import (
    VectorIssue,
    VectorValidationError,
    validate_vector,
)

GEMINI_PROVIDER_NAME = "gemini"


class GeminiEmbeddingErrorCode(StrEnum):
    """Stable Gemini embedding provider failure codes."""

    MISSING_API_KEY = "missing_api_key"
    MISSING_MODEL = "missing_model"
    INVALID_PROVIDER_DIMENSION = "invalid_provider_dimension"
    BLANK_INPUT_TEXT = "blank_input_text"
    PROVIDER_REQUEST_FAILED = "provider_request_failed"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    PROVIDER_RESULT_COUNT_MISMATCH = "provider_result_count_mismatch"
    PROVIDER_DIMENSION_MISMATCH = "provider_dimension_mismatch"
    MALFORMED_PROVIDER_VECTOR = "malformed_provider_vector"
    NON_FINITE_PROVIDER_VECTOR = "non_finite_provider_vector"


class GeminiEmbeddingError(RuntimeError):
    """Raised when the Gemini embedding provider cannot return usable vectors.

    A provider failure is never an empty result. It must stay distinct from
    "semantic search found nothing" and from the grounded answer service's
    insufficient-evidence result, so this error is raised rather than converted
    into vectors, an empty match list, or any answer text.
    """

    def __init__(
        self,
        code: GeminiEmbeddingErrorCode,
        message: str,
        *,
        position: int | None = None,
    ) -> None:
        self.code = code
        self.position = position
        super().__init__(message)


_VECTOR_ISSUE_CODES: dict[VectorIssue, GeminiEmbeddingErrorCode] = {
    VectorIssue.DIMENSION_MISMATCH: GeminiEmbeddingErrorCode.PROVIDER_DIMENSION_MISMATCH,
    VectorIssue.MALFORMED_VALUE: GeminiEmbeddingErrorCode.MALFORMED_PROVIDER_VECTOR,
    VectorIssue.NON_FINITE_VALUE: GeminiEmbeddingErrorCode.NON_FINITE_PROVIDER_VECTOR,
}


class GeminiEmbeddingProvider:
    """Produce real semantic vectors through the Gemini Embeddings API.

    ``model_name`` is the stable vendor identity ``"gemini"`` and
    ``model_version`` is the configured embedding model, for example
    ``"gemini-embedding-001"``. This matches the Gemini language model
    provider and never invents a snapshot version from a floating alias.

    The requested dimension is explicit and authoritative: it is sent as
    ``output_dimensionality`` and every returned vector is verified against it.
    Vectors are never padded, truncated, normalized, or otherwise transformed
    locally.

    The API key is passed to the SDK client and never stored on the instance,
    so it cannot surface through attributes, ``repr``, or error messages.

    Any object exposing ``models.embed_content`` may be injected as ``client``,
    which is how the unit tests run without network access.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimension: int,
        client: Any | None = None,
    ) -> None:
        if not api_key.strip():
            raise GeminiEmbeddingError(
                GeminiEmbeddingErrorCode.MISSING_API_KEY,
                "A Gemini API key is required before any request is sent.",
            )
        if not model.strip():
            raise GeminiEmbeddingError(
                GeminiEmbeddingErrorCode.MISSING_MODEL,
                "A Gemini embedding model name is required before any request is sent.",
            )
        if dimension <= 0:
            raise GeminiEmbeddingError(
                GeminiEmbeddingErrorCode.INVALID_PROVIDER_DIMENSION,
                "The embedding dimension must be greater than zero.",
            )

        self._model = model.strip()
        self._dimension = dimension
        self._client = genai.Client(api_key=api_key) if client is None else client

    def __repr__(self) -> str:
        """Describe the provider without exposing any credential."""
        return (
            f"{type(self).__name__}"
            f"(model={self._model!r}, dimension={self._dimension})"
        )

    @property
    def model_name(self) -> str:
        return GEMINI_PROVIDER_NAME

    @property
    def model_version(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Return one validated vector per text, preserving input order.

        An empty collection returns no vectors without contacting the API,
        matching the deterministic provider. Blank texts are rejected before a
        request is sent, because a blank input cannot produce a meaningful
        vector and would still be billed.
        """
        requested = tuple(texts)
        if not requested:
            return ()
        for position, text in enumerate(requested):
            if not text.strip():
                raise GeminiEmbeddingError(
                    GeminiEmbeddingErrorCode.BLANK_INPUT_TEXT,
                    "Embedding input text must contain non-whitespace characters.",
                    position=position,
                )

        try:
            response = self._client.models.embed_content(
                model=self._model,
                contents=list(requested),
                config=types.EmbedContentConfig(
                    output_dimensionality=self._dimension,
                ),
            )
        except Exception as error:
            # Only the exception type is reported. The SDK message is never
            # interpolated, so no request, header, or credential material can
            # reach a log or an API response through this path.
            raise GeminiEmbeddingError(
                GeminiEmbeddingErrorCode.PROVIDER_REQUEST_FAILED,
                f"The Gemini embedding request failed: {type(error).__name__}.",
            ) from error

        return self._validated_vectors(response, expected_count=len(requested))

    def _validated_vectors(
        self,
        response: object,
        *,
        expected_count: int,
    ) -> tuple[tuple[float, ...], ...]:
        embeddings: object = getattr(response, "embeddings", None)
        if not isinstance(embeddings, Sequence) or isinstance(embeddings, str | bytes):
            raise GeminiEmbeddingError(
                GeminiEmbeddingErrorCode.INVALID_PROVIDER_RESPONSE,
                "The Gemini embedding response did not contain an embeddings collection.",
            )
        if len(embeddings) != expected_count:
            raise GeminiEmbeddingError(
                GeminiEmbeddingErrorCode.PROVIDER_RESULT_COUNT_MISMATCH,
                f"The provider returned {len(embeddings)} vectors for {expected_count} texts.",
            )

        vectors: list[tuple[float, ...]] = []
        for position, item in enumerate(embeddings):
            vector: object = getattr(item, "values", None)
            if not isinstance(vector, Sequence) or isinstance(vector, str | bytes):
                raise GeminiEmbeddingError(
                    GeminiEmbeddingErrorCode.MALFORMED_PROVIDER_VECTOR,
                    "The Gemini embedding response contained a non-numeric vector.",
                    position=position,
                )

            try:
                vectors.append(validate_vector(vector, dimension=self._dimension))
            except VectorValidationError as error:
                raise GeminiEmbeddingError(
                    _VECTOR_ISSUE_CODES[error.issue],
                    str(error),
                    position=position,
                ) from error

        return tuple(vectors)


def gemini_embedding_provider_from_settings(
    settings: Settings,
) -> GeminiEmbeddingProvider:
    """Build the provider from configuration without logging the credential."""
    api_key = settings.gemini_api_key
    if api_key is None:
        raise GeminiEmbeddingError(
            GeminiEmbeddingErrorCode.MISSING_API_KEY,
            "GEMINI_API_KEY is not configured.",
        )
    return GeminiEmbeddingProvider(
        api_key=api_key.get_secret_value(),
        model=settings.gemini_embedding_model,
        dimension=settings.embedding_dimension,
    )
