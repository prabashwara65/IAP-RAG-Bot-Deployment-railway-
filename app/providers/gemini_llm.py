"""Gemini implementation of the vendor-neutral language model contract.

This module is the only place in the platform that knows Gemini exists. The
grounded answer service depends on ``LLMProvider`` alone, so swapping or adding
a vendor never reaches the services layer.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from google import genai
from google.genai import types

from app.core.config import Settings

DEFAULT_MAX_OUTPUT_TOKENS = 800
GEMINI_PROVIDER_NAME = "gemini"


class GeminiLLMErrorCode(StrEnum):
    """Stable Gemini provider failure codes."""

    MISSING_API_KEY = "missing_api_key"
    MISSING_MODEL = "missing_model"
    INVALID_MAX_OUTPUT_TOKENS = "invalid_max_output_tokens"
    PROVIDER_REQUEST_FAILED = "provider_request_failed"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    EMPTY_PROVIDER_RESPONSE = "empty_provider_response"


class GeminiLLMError(RuntimeError):
    """Raised when the Gemini provider cannot return a usable completion.

    A provider failure is never an answer. It must stay distinct from the
    grounded answer service's insufficient-evidence result, so this error is
    raised rather than converted into any answer text.
    """

    def __init__(self, code: GeminiLLMErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class GeminiLLMProvider:
    """Generate completions through the Gemini Developer API.

    ``model_name`` is the stable vendor identity ``"gemini"`` and
    ``model_version`` is the configured model string, for example
    ``"gemini-2.5-flash"``. This mirrors how ``embedding_sets`` pairs one stable
    name with a moving version: upgrading the configured model is a version
    change under the same provider. No snapshot version is invented from an
    alias.

    The API key is passed to the SDK client and never stored on the instance,
    so it cannot surface through attributes, ``repr``, or error messages.

    Any object exposing ``models.generate_content`` may be injected as
    ``client``, which is how the unit tests run without network access.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: Any | None = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> None:
        if not api_key.strip():
            raise GeminiLLMError(
                GeminiLLMErrorCode.MISSING_API_KEY,
                "A Gemini API key is required before any request is sent.",
            )
        if not model.strip():
            raise GeminiLLMError(
                GeminiLLMErrorCode.MISSING_MODEL,
                "A Gemini model name is required before any request is sent.",
            )
        if max_output_tokens <= 0:
            raise GeminiLLMError(
                GeminiLLMErrorCode.INVALID_MAX_OUTPUT_TOKENS,
                "max_output_tokens must be greater than zero.",
            )

        self._model = model.strip()
        self._max_output_tokens = max_output_tokens
        self._client = genai.Client(api_key=api_key) if client is None else client

    def __repr__(self) -> str:
        """Describe the provider without exposing any credential."""
        return f"{type(self).__name__}(model={self._model!r})"

    @property
    def model_name(self) -> str:
        return GEMINI_PROVIDER_NAME

    @property
    def model_version(self) -> str:
        return self._model

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return one completion, keeping system and user content separate.

        System instructions travel as ``system_instruction``. The user prompt
        is the request body. They are never concatenated into one string.

        The returned text is the SDK ``text`` field verbatim; only the
        emptiness check ignores surrounding whitespace.
        """
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=self._max_output_tokens,
                ),
            )
        except Exception as error:
            # Only the exception type is reported. The SDK message is never
            # interpolated, so no request, header, or credential material can
            # reach a log or an API response through this path.
            raise GeminiLLMError(
                GeminiLLMErrorCode.PROVIDER_REQUEST_FAILED,
                f"The Gemini request failed: {type(error).__name__}.",
            ) from error

        text: object = getattr(response, "text", None)
        if not isinstance(text, str):
            raise GeminiLLMError(
                GeminiLLMErrorCode.INVALID_PROVIDER_RESPONSE,
                "The Gemini response did not contain textual output.",
            )
        if not text.strip():
            raise GeminiLLMError(
                GeminiLLMErrorCode.EMPTY_PROVIDER_RESPONSE,
                "The Gemini response contained no output text.",
            )
        return text


def gemini_llm_provider_from_settings(settings: Settings) -> GeminiLLMProvider:
    """Build the provider from configuration without logging the credential."""
    api_key = settings.gemini_api_key
    if api_key is None:
        raise GeminiLLMError(
            GeminiLLMErrorCode.MISSING_API_KEY,
            "GEMINI_API_KEY is not configured.",
        )
    return GeminiLLMProvider(
        api_key=api_key.get_secret_value(),
        model=settings.gemini_model,
    )
