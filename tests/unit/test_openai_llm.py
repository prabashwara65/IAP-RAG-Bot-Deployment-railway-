"""Unit tests for the OpenAI language model provider.

Every test injects a fake client. No test in this module performs network I/O.
"""

from collections.abc import Sequence
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from openai import APIConnectionError, OpenAIError

from app.core.config import DEFAULT_OPENAI_MODEL, Settings
from app.domain.retrieval import SemanticSearchRecord
from app.providers.llm import LLMProvider
from app.providers.openai_llm import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    OPENAI_PROVIDER_NAME,
    OpenAILLMError,
    OpenAILLMErrorCode,
    OpenAILLMProvider,
    openai_llm_provider_from_settings,
)
from app.repositories.embeddings import EmbeddingRepository
from app.services.hr_rag import INSUFFICIENT_EVIDENCE_ANSWER, answer_hr_question

API_KEY = "test-api-key-not-a-real-secret"
MODEL = "gpt-5-mini"
SYSTEM_PROMPT = "System instructions for the test."
USER_PROMPT = "User question for the test."


class _FakeResponse:
    def __init__(self, output_text: object) -> None:
        self.output_text = output_text


class _FakeResponses:
    def __init__(self, *, output_text: object, error: Exception | None) -> None:
        self._output_text = output_text
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._output_text)


class _FakeOpenAIClient:
    """Minimal stand-in exposing only the `responses.create` surface we use."""

    def __init__(
        self,
        *,
        output_text: object = "Synthetic completion.",
        error: Exception | None = None,
    ) -> None:
        self.responses = _FakeResponses(output_text=output_text, error=error)


def _provider(
    *,
    client: _FakeOpenAIClient | None = None,
    api_key: str = API_KEY,
    model: str = MODEL,
    **overrides: Any,
) -> OpenAILLMProvider:
    return OpenAILLMProvider(
        api_key=api_key,
        model=model,
        client=client or _FakeOpenAIClient(),  # type: ignore[arg-type]
        **overrides,
    )


# --------------------------------------------------------------------------
# Contract conformance and metadata
# --------------------------------------------------------------------------


def test_provider_satisfies_the_vendor_neutral_llm_contract() -> None:
    provider: LLMProvider = _provider()

    assert isinstance(provider, LLMProvider)


def test_model_metadata_is_deterministic_and_free_of_invented_snapshots() -> None:
    provider = _provider(model="gpt-5-mini")

    assert provider.model_name == OPENAI_PROVIDER_NAME == "openai"
    assert provider.model_version == "gpt-5-mini"
    assert (provider.model_name, provider.model_version) == (
        _provider(model="gpt-5-mini").model_name,
        _provider(model="gpt-5-mini").model_version,
    )


def test_a_different_configured_model_changes_only_the_version() -> None:
    provider = _provider(model="gpt-5")

    assert provider.model_name == "openai"
    assert provider.model_version == "gpt-5"


def test_surrounding_whitespace_in_the_model_name_is_ignored() -> None:
    client = _FakeOpenAIClient()

    provider = _provider(client=client, model="  gpt-5-mini  ")
    provider.generate(system_prompt=SYSTEM_PROMPT, user_prompt=USER_PROMPT)

    assert provider.model_version == "gpt-5-mini"
    assert client.responses.calls[0]["model"] == "gpt-5-mini"


# --------------------------------------------------------------------------
# Responses API mapping
# --------------------------------------------------------------------------


def test_the_configured_model_is_forwarded_to_the_responses_api() -> None:
    client = _FakeOpenAIClient()

    _provider(client=client, model="gpt-5-mini").generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
    )

    assert client.responses.calls[0]["model"] == "gpt-5-mini"


def test_the_system_and_user_prompts_are_sent_as_separate_roles() -> None:
    client = _FakeOpenAIClient()

    _provider(client=client).generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
    )

    messages = client.responses.calls[0]["input"]
    assert messages == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ]


def test_the_prompts_are_never_concatenated_into_one_string() -> None:
    client = _FakeOpenAIClient()

    _provider(client=client).generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
    )

    call = client.responses.calls[0]
    assert not isinstance(call["input"], str)
    assert "instructions" not in call
    for message in call["input"]:
        assert SYSTEM_PROMPT in message["content"] or USER_PROMPT in message["content"]
        assert not (SYSTEM_PROMPT in message["content"] and USER_PROMPT in message["content"])


def test_no_tool_streaming_or_conversation_parameters_are_sent() -> None:
    client = _FakeOpenAIClient()

    _provider(client=client).generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
    )

    assert set(client.responses.calls[0]) == {"model", "input", "max_output_tokens"}


def test_a_bounded_output_limit_is_sent() -> None:
    client = _FakeOpenAIClient()

    _provider(client=client).generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
    )

    assert client.responses.calls[0]["max_output_tokens"] == DEFAULT_MAX_OUTPUT_TOKENS


def test_the_output_limit_is_configurable() -> None:
    client = _FakeOpenAIClient()

    _provider(client=client, max_output_tokens=256).generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
    )

    assert client.responses.calls[0]["max_output_tokens"] == 256


def test_the_client_is_called_exactly_once_per_generate_call() -> None:
    client = _FakeOpenAIClient()
    provider = _provider(client=client)

    provider.generate(system_prompt=SYSTEM_PROMPT, user_prompt=USER_PROMPT)
    assert len(client.responses.calls) == 1

    provider.generate(system_prompt=SYSTEM_PROMPT, user_prompt=USER_PROMPT)
    assert len(client.responses.calls) == 2


def test_the_output_text_is_returned_unchanged() -> None:
    client = _FakeOpenAIClient(output_text="  Synthetic grounded answer. [S1]  ")

    answer = _provider(client=client).generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
    )

    assert answer == "  Synthetic grounded answer. [S1]  "


# --------------------------------------------------------------------------
# Credential safety
# --------------------------------------------------------------------------


def test_the_api_key_is_never_stored_or_rendered_on_the_provider() -> None:
    provider = OpenAILLMProvider(api_key=API_KEY, model=MODEL)

    assert API_KEY not in repr(provider)
    assert API_KEY not in str(provider)
    assert not any(value == API_KEY for value in vars(provider).values())
    assert repr(provider) == f"OpenAILLMProvider(model={MODEL!r})"


def test_the_sdk_failure_message_is_not_interpolated_into_the_provider_error() -> None:
    leak_marker = "credential-marker-that-must-never-be-echoed"
    client = _FakeOpenAIClient(error=OpenAIError(leak_marker))

    with pytest.raises(OpenAILLMError) as exc_info:
        _provider(client=client).generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=USER_PROMPT,
        )

    assert leak_marker not in str(exc_info.value)
    assert leak_marker not in repr(exc_info.value)


# --------------------------------------------------------------------------
# Structural validation before any request
# --------------------------------------------------------------------------


@pytest.mark.parametrize("api_key", ["", "   ", "\n\t "])
def test_a_blank_api_key_is_rejected_before_any_request(api_key: str) -> None:
    client = _FakeOpenAIClient()

    with pytest.raises(OpenAILLMError) as exc_info:
        _provider(client=client, api_key=api_key)

    assert exc_info.value.code is OpenAILLMErrorCode.MISSING_API_KEY
    assert client.responses.calls == []


@pytest.mark.parametrize("model", ["", "   ", "\n\t "])
def test_a_blank_model_is_rejected_before_any_request(model: str) -> None:
    client = _FakeOpenAIClient()

    with pytest.raises(OpenAILLMError) as exc_info:
        _provider(client=client, model=model)

    assert exc_info.value.code is OpenAILLMErrorCode.MISSING_MODEL
    assert client.responses.calls == []


@pytest.mark.parametrize("max_output_tokens", [0, -1])
def test_a_non_positive_output_limit_is_rejected(max_output_tokens: int) -> None:
    with pytest.raises(OpenAILLMError) as exc_info:
        _provider(max_output_tokens=max_output_tokens)

    assert exc_info.value.code is OpenAILLMErrorCode.INVALID_MAX_OUTPUT_TOKENS


# --------------------------------------------------------------------------
# Response and transport failures
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        OpenAIError("transport failure"),
        APIConnectionError(
            request=httpx.Request("POST", "https://api.openai.com/v1/responses")
        ),
    ],
)
def test_an_sdk_failure_is_surfaced_as_a_provider_error(error: Exception) -> None:
    client = _FakeOpenAIClient(error=error)

    with pytest.raises(OpenAILLMError) as exc_info:
        _provider(client=client).generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=USER_PROMPT,
        )

    assert exc_info.value.code is OpenAILLMErrorCode.PROVIDER_REQUEST_FAILED
    assert exc_info.value.__cause__ is error
    assert type(error).__name__ in str(exc_info.value)


@pytest.mark.parametrize("output_text", ["", "   ", "\n\t "])
def test_an_empty_response_is_rejected(output_text: str) -> None:
    client = _FakeOpenAIClient(output_text=output_text)

    with pytest.raises(OpenAILLMError) as exc_info:
        _provider(client=client).generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=USER_PROMPT,
        )

    assert exc_info.value.code is OpenAILLMErrorCode.EMPTY_PROVIDER_RESPONSE


@pytest.mark.parametrize("output_text", [None, 42, ["text"], {"text": "value"}])
def test_a_non_textual_response_is_rejected(output_text: object) -> None:
    client = _FakeOpenAIClient(output_text=output_text)

    with pytest.raises(OpenAILLMError) as exc_info:
        _provider(client=client).generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=USER_PROMPT,
        )

    assert exc_info.value.code is OpenAILLMErrorCode.INVALID_PROVIDER_RESPONSE


def test_a_response_without_output_text_is_rejected() -> None:
    class _ResponseWithoutText:
        pass

    client = _FakeOpenAIClient()
    client.responses = _FakeResponses(output_text="", error=None)
    client.responses.create = lambda **kwargs: _ResponseWithoutText()  # type: ignore[assignment,return-value]

    with pytest.raises(OpenAILLMError) as exc_info:
        _provider(client=client).generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=USER_PROMPT,
        )

    assert exc_info.value.code is OpenAILLMErrorCode.INVALID_PROVIDER_RESPONSE


# --------------------------------------------------------------------------
# Configuration wiring
# --------------------------------------------------------------------------


def test_the_provider_can_be_built_from_settings() -> None:
    settings = Settings(
        openai_api_key=API_KEY,  # type: ignore[arg-type]
        openai_model="gpt-5-mini",
    )

    provider = openai_llm_provider_from_settings(settings)

    assert provider.model_version == "gpt-5-mini"
    assert API_KEY not in repr(provider)


def test_building_from_settings_without_a_key_fails_before_any_request() -> None:
    settings = Settings(openai_api_key=None, openai_model=DEFAULT_OPENAI_MODEL)

    with pytest.raises(OpenAILLMError) as exc_info:
        openai_llm_provider_from_settings(settings)

    assert exc_info.value.code is OpenAILLMErrorCode.MISSING_API_KEY


# --------------------------------------------------------------------------
# Grounded RAG compatibility
# --------------------------------------------------------------------------


class _StubEmbeddingProvider:
    @property
    def model_name(self) -> str:
        return "stub-embedding-provider"

    @property
    def model_version(self) -> str:
        return "0.0.1"

    @property
    def dimension(self) -> int:
        return 2

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return [(0.1, 0.2) for _ in texts]


def _repository_with_one_chunk() -> Mock:
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
    return repository


def test_the_openai_provider_drives_the_existing_grounded_rag_service() -> None:
    client = _FakeOpenAIClient(output_text="Synthetic grounded answer. [S1]")

    answer = answer_hr_question(
        question="How much synthetic leave is granted?",
        tenant_id="tenant-synthetic",
        embedding_provider=_StubEmbeddingProvider(),
        llm_provider=_provider(client=client),
        repository=_repository_with_one_chunk(),
    )

    assert answer.insufficient_evidence is False
    assert [citation.citation_id for citation in answer.citations] == ["S1"]
    assert len(client.responses.calls) == 1


def test_a_provider_failure_never_becomes_an_insufficient_evidence_answer() -> None:
    client = _FakeOpenAIClient(error=OpenAIError("transport failure"))

    with pytest.raises(OpenAILLMError) as exc_info:
        answer_hr_question(
            question="How much synthetic leave is granted?",
            tenant_id="tenant-synthetic",
            embedding_provider=_StubEmbeddingProvider(),
            llm_provider=_provider(client=client),
            repository=_repository_with_one_chunk(),
        )

    assert exc_info.value.code is OpenAILLMErrorCode.PROVIDER_REQUEST_FAILED
    assert INSUFFICIENT_EVIDENCE_ANSWER not in str(exc_info.value)
