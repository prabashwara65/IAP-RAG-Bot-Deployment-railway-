"""OpenAI implementation of the vendor-neutral embedding provider contract.

This module is the only place in the platform that knows how OpenAI produces
vectors. The chunk embedding and retrieval services depend on
``EmbeddingProvider`` alone, so adding or swapping a vendor never reaches them.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from openai import OpenAI, OpenAIError

from app.core.config import Settings
from app.services.vector_validation import (
    VectorIssue,
    VectorValidationError,
    validate_vector,
)

OPENAI_PROVIDER_NAME = "openai"


class OpenAIEmbeddingErrorCode(StrEnum):
    """Stable OpenAI embedding provider failure codes."""

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


class OpenAIEmbeddingError(RuntimeError):
    """Raised when the OpenAI embedding provider cannot return usable vectors.

    A provider failure is never an empty result. It must stay distinct from
    "semantic search found nothing" and from the grounded answer service's
    insufficient-evidence result, so this error is raised rather than converted
    into vectors, an empty match list, or any answer text.
    """

    def __init__(
        self,
        code: OpenAIEmbeddingErrorCode,
        message: str,
        *,
        position: int | None = None,
    ) -> None:
        self.code = code
        self.position = position
        super().__init__(message)


_VECTOR_ISSUE_CODES: dict[VectorIssue, OpenAIEmbeddingErrorCode] = {
    VectorIssue.DIMENSION_MISMATCH: OpenAIEmbeddingErrorCode.PROVIDER_DIMENSION_MISMATCH,
    VectorIssue.MALFORMED_VALUE: OpenAIEmbeddingErrorCode.MALFORMED_PROVIDER_VECTOR,
    VectorIssue.NON_FINITE_VALUE: OpenAIEmbeddingErrorCode.NON_FINITE_PROVIDER_VECTOR,
}


class OpenAIEmbeddingProvider:
    """Produce real semantic vectors through the OpenAI Embeddings API.

    ``model_name`` is the stable vendor identity ``"openai"`` and
    ``model_version`` is the configured embedding model, for example
    ``"text-embedding-3-small"``. This matches the OpenAI language model
    provider and never invents a snapshot version from a floating alias.

    The requested dimension is explicit and authoritative: it is sent to the
    API and every returned vector is verified against it. Vectors are never
    padded, truncated, normalized, or otherwise transformed locally.

    The API key is passed to the SDK client and never stored on the instance,
    so it cannot surface through attributes, ``repr``, or error messages.

    Any object exposing ``embeddings.create`` may be injected as ``client``,
    which is how the unit tests run without network access.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimension: int,
        client: OpenAI | None = None,
    ) -> None:
        if not api_key.strip():
            raise OpenAIEmbeddingError(
                OpenAIEmbeddingErrorCode.MISSING_API_KEY,
                "An OpenAI API key is required before any request is sent.",
            )
        if not model.strip():
            raise OpenAIEmbeddingError(
                OpenAIEmbeddingErrorCode.MISSING_MODEL,
                "An OpenAI embedding model name is required before any request is sent.",
            )
        if dimension <= 0:
            raise OpenAIEmbeddingError(
                OpenAIEmbeddingErrorCode.INVALID_PROVIDER_DIMENSION,
                "The embedding dimension must be greater than zero.",
            )

        self._model = model.strip()
        self._dimension = dimension
        self._client = OpenAI(api_key=api_key) if client is None else client

    def __repr__(self) -> str:
        """Describe the provider without exposing any credential."""
        return (
            f"{type(self).__name__}"
            f"(model={self._model!r}, dimension={self._dimension})"
        )

    @property
    def model_name(self) -> str:
        return OPENAI_PROVIDER_NAME

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
                raise OpenAIEmbeddingError(
                    OpenAIEmbeddingErrorCode.BLANK_INPUT_TEXT,
                    "Embedding input text must contain non-whitespace characters.",
                    position=position,
                )

        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=list(requested),
                dimensions=self._dimension,
            )
        except OpenAIError as error:
            # Only the exception type is reported. The SDK message is never
            # interpolated, so no request, header, or credential material can
            # reach a log or an API response through this path.
            raise OpenAIEmbeddingError(
                OpenAIEmbeddingErrorCode.PROVIDER_REQUEST_FAILED,
                f"The OpenAI embedding request failed: {type(error).__name__}.",
            ) from error

        return self._validated_vectors(response, expected_count=len(requested))

    def _validated_vectors(
        self,
        response: object,
        *,
        expected_count: int,
    ) -> tuple[tuple[float, ...], ...]:
        data: object = getattr(response, "data", None)
        if not isinstance(data, Sequence) or isinstance(data, str | bytes):
            raise OpenAIEmbeddingError(
                OpenAIEmbeddingErrorCode.INVALID_PROVIDER_RESPONSE,
                "The OpenAI embedding response did not contain a data collection.",
            )
        if len(data) != expected_count:
            raise OpenAIEmbeddingError(
                OpenAIEmbeddingErrorCode.PROVIDER_RESULT_COUNT_MISMATCH,
                f"The provider returned {len(data)} vectors for {expected_count} texts.",
            )

        vectors: list[tuple[float, ...]] = []
        for position, item in enumerate(data):
            index: object = getattr(item, "index", None)
            if index != position:
                # Results are never reordered here. An unexpected index would
                # silently rebind a vector to the wrong chunk, so it is refused.
                raise OpenAIEmbeddingError(
                    OpenAIEmbeddingErrorCode.INVALID_PROVIDER_RESPONSE,
                    "The OpenAI embedding response was not in input order.",
                    position=position,
                )

            vector: object = getattr(item, "embedding", None)
            if not isinstance(vector, Sequence) or isinstance(vector, str | bytes):
                raise OpenAIEmbeddingError(
                    OpenAIEmbeddingErrorCode.MALFORMED_PROVIDER_VECTOR,
                    "The OpenAI embedding response contained a non-numeric vector.",
                    position=position,
                )

            try:
                vectors.append(validate_vector(vector, dimension=self._dimension))
            except VectorValidationError as error:
                raise OpenAIEmbeddingError(
                    _VECTOR_ISSUE_CODES[error.issue],
                    str(error),
                    position=position,
                ) from error

        return tuple(vectors)


def openai_embedding_provider_from_settings(
    settings: Settings,
) -> OpenAIEmbeddingProvider:
    """Build the provider from configuration without logging the credential."""
    api_key = settings.openai_api_key
    if api_key is None:
        raise OpenAIEmbeddingError(
            OpenAIEmbeddingErrorCode.MISSING_API_KEY,
            "OPENAI_API_KEY is not configured.",
        )
    return OpenAIEmbeddingProvider(
        api_key=api_key.get_secret_value(),
        model=settings.openai_embedding_model,
        dimension=settings.embedding_dimension,
    )
