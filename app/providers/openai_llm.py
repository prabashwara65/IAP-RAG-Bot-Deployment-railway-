"""OpenAI implementation of the vendor-neutral language model contract.

This module is the only place in the platform that knows OpenAI exists. The
grounded answer service depends on ``LLMProvider`` alone, so swapping or adding
a vendor never reaches the services layer.
"""

from __future__ import annotations

from enum import StrEnum

from openai import OpenAI, OpenAIError
from openai.types.responses import EasyInputMessageParam, ResponseInputParam

from app.core.config import Settings

DEFAULT_MAX_OUTPUT_TOKENS = 800
OPENAI_PROVIDER_NAME = "openai"


class OpenAILLMErrorCode(StrEnum):
    """Stable OpenAI provider failure codes."""

    MISSING_API_KEY = "missing_api_key"
    MISSING_MODEL = "missing_model"
    INVALID_MAX_OUTPUT_TOKENS = "invalid_max_output_tokens"
    PROVIDER_REQUEST_FAILED = "provider_request_failed"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    EMPTY_PROVIDER_RESPONSE = "empty_provider_response"


class OpenAILLMError(RuntimeError):
    """Raised when the OpenAI provider cannot return a usable completion.

    A provider failure is never an answer. It must stay distinct from the
    grounded answer service's insufficient-evidence result, so this error is
    raised rather than converted into any answer text.
    """

    def __init__(self, code: OpenAILLMErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class OpenAILLMProvider:
    """Generate completions through the OpenAI Responses API.

    ``model_name`` is the stable vendor identity ``"openai"`` and
    ``model_version`` is the configured model string, for example
    ``"gpt-5-mini"``. This mirrors how ``embedding_sets`` pairs one stable name
    with a moving version: upgrading the configured model is a version change
    under the same provider. No snapshot version is invented from an alias.

    The API key is passed to the SDK client and never stored on the instance,
    so it cannot surface through attributes, ``repr``, or error messages.

    Any object exposing ``responses.create`` may be injected as ``client``,
    which is how the unit tests run without network access.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: OpenAI | None = None,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> None:
        if not api_key.strip():
            raise OpenAILLMError(
                OpenAILLMErrorCode.MISSING_API_KEY,
                "An OpenAI API key is required before any request is sent.",
            )
        if not model.strip():
            raise OpenAILLMError(
                OpenAILLMErrorCode.MISSING_MODEL,
                "An OpenAI model name is required before any request is sent.",
            )
        if max_output_tokens <= 0:
            raise OpenAILLMError(
                OpenAILLMErrorCode.INVALID_MAX_OUTPUT_TOKENS,
                "max_output_tokens must be greater than zero.",
            )

        self._model = model.strip()
        self._max_output_tokens = max_output_tokens
        self._client = OpenAI(api_key=api_key) if client is None else client

    def __repr__(self) -> str:
        """Describe the provider without exposing any credential."""
        return f"{type(self).__name__}(model={self._model!r})"

    @property
    def model_name(self) -> str:
        return OPENAI_PROVIDER_NAME

    @property
    def model_version(self) -> str:
        return self._model

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return one completion, keeping system and user content in separate roles.

        The returned text is the Responses API ``output_text`` verbatim; only
        the emptiness check ignores surrounding whitespace.
        """
        messages: ResponseInputParam = [
            EasyInputMessageParam(role="system", content=system_prompt),
            EasyInputMessageParam(role="user", content=user_prompt),
        ]
        try:
            response = self._client.responses.create(
                model=self._model,
                input=messages,
                max_output_tokens=self._max_output_tokens,
            )
        except OpenAIError as error:
            # Only the exception type is reported. The SDK message is never
            # interpolated, so no request, header, or credential material can
            # reach a log or an API response through this path.
            raise OpenAILLMError(
                OpenAILLMErrorCode.PROVIDER_REQUEST_FAILED,
                f"The OpenAI request failed: {type(error).__name__}.",
            ) from error

        text: object = getattr(response, "output_text", None)
        if not isinstance(text, str):
            raise OpenAILLMError(
                OpenAILLMErrorCode.INVALID_PROVIDER_RESPONSE,
                "The OpenAI response did not contain textual output.",
            )
        if not text.strip():
            raise OpenAILLMError(
                OpenAILLMErrorCode.EMPTY_PROVIDER_RESPONSE,
                "The OpenAI response contained no output text.",
            )
        return text


def openai_llm_provider_from_settings(settings: Settings) -> OpenAILLMProvider:
    """Build the provider from configuration without logging the credential."""
    api_key = settings.openai_api_key
    if api_key is None:
        raise OpenAILLMError(
            OpenAILLMErrorCode.MISSING_API_KEY,
            "OPENAI_API_KEY is not configured.",
        )
    return OpenAILLMProvider(
        api_key=api_key.get_secret_value(),
        model=settings.openai_model,
    )
