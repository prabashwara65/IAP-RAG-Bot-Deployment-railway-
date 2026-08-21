"""Integration tests for the HR grounded answer endpoint.

Every test injects deterministic collaborators through FastAPI dependency
overrides. No test requires an OpenAI API key, network access, or a database.
"""

from collections.abc import Sequence
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.exc import OperationalError

from app.api.dependencies import (
    get_embedding_provider,
    get_embedding_repository,
    get_llm_provider,
)
from app.api.routes.hr_rag import (
    ANSWER_SERVICE_MESSAGE,
    CONFIGURATION_MESSAGE,
    EVIDENCE_STORE_MESSAGE,
)
from app.core.config import Settings
from app.domain.retrieval import SemanticSearchRecord
from app.main import create_app
from app.providers.openai_embeddings import (
    OpenAIEmbeddingError,
    OpenAIEmbeddingErrorCode,
)
from app.repositories.embeddings import EmbeddingRepository
from app.schemas.hr_rag import MAX_QUESTION_LENGTH

ASK_PATH = "/api/v1/hr/ask"
TENANT_ID = "tenant-synthetic"
QUESTION = "How many annual leave days do employees receive?"
FAKE_API_KEY = "test-api-key-not-a-real-secret"
GROUNDED_ANSWER = "Employees receive twenty-one working days of annual leave. [S1]"


class _StubEmbeddingProvider:
    """Embedding provider stub with a fixed vector and no semantics."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

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
        if self._error is not None:
            raise self._error
        return [(0.1, 0.2) for _ in texts]


class _StubLLMProvider:
    """Language model stub returning one fixed completion."""

    def __init__(self, response: str = GROUNDED_ANSWER) -> None:
        self._response = response
        self.prompts: list[str] = []

    @property
    def model_name(self) -> str:
        return "stub-llm"

    @property
    def model_version(self) -> str:
        return "0.0.1"

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        return self._response


def _record(document_key: str = "HR-SYNTHETIC-LEAVE-001") -> SemanticSearchRecord:
    return SemanticSearchRecord(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        embedding_set_id=uuid4(),
        document_key=document_key,
        document_title="Synthetic Annual Leave Policy",
        chunk_index=0,
        heading_path="Synthetic Annual Leave Policy > Entitlement",
        content_text="Every full-time employee receives twenty-one working days.",
        distance=0.12,
    )


def _repository(
    records: Sequence[SemanticSearchRecord] = (),
    *,
    error: Exception | None = None,
) -> Mock:
    repository = Mock(spec=EmbeddingRepository)
    if error is not None:
        repository.search_similar_chunks.side_effect = error
    else:
        repository.search_similar_chunks.return_value = tuple(records)
    return repository


def _application(
    *,
    embedding_provider: object | None = None,
    llm_provider: object | None = None,
    repository: Mock | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    """Compose the real application with deterministic collaborators."""
    application = create_app(
        settings
        or Settings(
            app_env="test",
            openai_api_key=FAKE_API_KEY,  # type: ignore[arg-type]
        )
    )
    if embedding_provider is not None:
        application.dependency_overrides[get_embedding_provider] = (
            lambda: embedding_provider
        )
    if llm_provider is not None:
        application.dependency_overrides[get_llm_provider] = lambda: llm_provider
    if repository is not None:
        application.dependency_overrides[get_embedding_repository] = lambda: repository
    return application


async def _ask(
    application: FastAPI,
    *,
    payload: dict[str, Any] | None = None,
    raise_app_exceptions: bool = True,
) -> Response:
    transport = ASGITransport(
        app=application,
        raise_app_exceptions=raise_app_exceptions,
    )
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            ASK_PATH,
            json=payload if payload is not None else {
                "question": QUESTION,
                "tenant_id": TENANT_ID,
            },
        )


def _grounded_application(
    *,
    records: Sequence[SemanticSearchRecord] | None = None,
    llm_response: str = GROUNDED_ANSWER,
) -> FastAPI:
    return _application(
        embedding_provider=_StubEmbeddingProvider(),
        llm_provider=_StubLLMProvider(llm_response),
        repository=_repository((_record(),) if records is None else records),
    )


# --------------------------------------------------------------------------
# Successful answers
# --------------------------------------------------------------------------


async def test_a_grounded_answer_is_returned_with_its_citations() -> None:
    response = await _ask(_grounded_application())

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == GROUNDED_ANSWER
    assert body["insufficient_evidence"] is False
    assert len(body["citations"]) == 1
    assert response.headers["X-Correlation-ID"]


async def test_citations_expose_the_contracted_fields_only() -> None:
    response = await _ask(_grounded_application())

    (citation,) = response.json()["citations"]
    assert set(citation) == {
        "citation_id",
        "document_key",
        "document_title",
        "heading_path",
        "chunk_index",
        "distance",
    }
    assert citation["citation_id"] == "S1"
    assert citation["document_key"] == "HR-SYNTHETIC-LEAVE-001"
    assert citation["document_title"] == "Synthetic Annual Leave Policy"
    assert citation["heading_path"] == "Synthetic Annual Leave Policy > Entitlement"
    assert citation["chunk_index"] == 0
    assert citation["distance"] == pytest.approx(0.12)


async def test_internal_identifiers_are_not_exposed() -> None:
    record = _record()
    application = _grounded_application(records=(record,))

    response = await _ask(application)

    for identifier in (
        record.chunk_id,
        record.document_id,
        record.document_version_id,
        record.embedding_set_id,
    ):
        assert str(identifier) not in response.text
    assert record.content_text not in response.text


async def test_the_tenant_from_the_request_reaches_retrieval() -> None:
    repository = _repository((_record(),))
    application = _application(
        embedding_provider=_StubEmbeddingProvider(),
        llm_provider=_StubLLMProvider(),
        repository=repository,
    )

    await _ask(application, payload={"question": QUESTION, "tenant_id": "tenant-other"})

    assert repository.search_similar_chunks.call_args.kwargs["tenant_id"] == "tenant-other"
    assert repository.search_similar_chunks.call_args.kwargs["top_k"] == 5


async def test_no_supporting_evidence_is_a_successful_response() -> None:
    application = _grounded_application(records=())

    response = await _ask(application)

    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is True
    assert body["citations"] == []
    assert body["answer"]


# --------------------------------------------------------------------------
# Request validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("question", ["", "   ", "\n\t "])
async def test_a_blank_question_is_rejected(question: str) -> None:
    response = await _ask(
        _grounded_application(),
        payload={"question": question, "tenant_id": TENANT_ID},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["correlation_id"] == response.headers["X-Correlation-ID"]
    assert body["error"]["details"][0]["location"] == ["body", "question"]


@pytest.mark.parametrize("tenant_id", ["", "   "])
async def test_a_blank_tenant_is_rejected(tenant_id: str) -> None:
    response = await _ask(
        _grounded_application(),
        payload={"question": QUESTION, "tenant_id": tenant_id},
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["location"] == ["body", "tenant_id"]


async def test_a_missing_tenant_is_rejected() -> None:
    response = await _ask(_grounded_application(), payload={"question": QUESTION})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_an_unknown_field_is_rejected() -> None:
    response = await _ask(
        _grounded_application(),
        payload={"question": QUESTION, "tenant_id": TENANT_ID, "top_k": 50},
    )

    assert response.status_code == 422


async def test_an_oversized_question_is_rejected() -> None:
    response = await _ask(
        _grounded_application(),
        payload={"question": "a" * (MAX_QUESTION_LENGTH + 1), "tenant_id": TENANT_ID},
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------
# Failure mapping
# --------------------------------------------------------------------------


async def test_a_missing_credential_is_reported_as_unavailable() -> None:
    settings = Settings(_env_file=None, app_env="test", openai_api_key=None)  # type: ignore[call-arg]
    assert settings.openai_api_key is None
    application = _application(settings=settings, repository=_repository((_record(),)))

    response = await _ask(application)

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "HTTP_503"
    assert body["error"]["message"] == CONFIGURATION_MESSAGE


async def test_a_provider_request_failure_is_reported_as_a_bad_gateway() -> None:
    leak_marker = "internal-provider-detail-that-must-not-leak"
    application = _application(
        embedding_provider=_StubEmbeddingProvider(
            error=OpenAIEmbeddingError(
                OpenAIEmbeddingErrorCode.PROVIDER_REQUEST_FAILED,
                leak_marker,
            )
        ),
        llm_provider=_StubLLMProvider(),
        repository=_repository((_record(),)),
    )

    response = await _ask(application)

    assert response.status_code == 502
    assert response.json()["error"]["message"] == ANSWER_SERVICE_MESSAGE
    assert leak_marker not in response.text


async def test_a_hallucinated_citation_is_reported_as_a_bad_gateway() -> None:
    application = _grounded_application(
        llm_response="Employees receive unlimited leave. [S99]"
    )

    response = await _ask(application)

    assert response.status_code == 502
    assert response.json()["error"]["message"] == ANSWER_SERVICE_MESSAGE
    assert "S99" not in response.text


async def test_an_evidence_store_failure_is_reported_as_unavailable() -> None:
    application = _application(
        embedding_provider=_StubEmbeddingProvider(),
        llm_provider=_StubLLMProvider(),
        repository=_repository(
            error=OperationalError("SELECT secret_table", {}, Exception("db down"))
        ),
    )

    response = await _ask(application)

    assert response.status_code == 503
    assert response.json()["error"]["message"] == EVIDENCE_STORE_MESSAGE
    assert "secret_table" not in response.text


async def test_no_credential_or_internal_detail_appears_in_any_error_body() -> None:
    application = _application(
        embedding_provider=_StubEmbeddingProvider(
            error=OpenAIEmbeddingError(
                OpenAIEmbeddingErrorCode.PROVIDER_REQUEST_FAILED,
                FAKE_API_KEY,
            )
        ),
        llm_provider=_StubLLMProvider(),
        repository=_repository((_record(),)),
    )

    response = await _ask(application)

    assert FAKE_API_KEY not in response.text
    assert "Traceback" not in response.text
    assert "openai" not in response.text.casefold()
    assert set(response.json()["error"]) == {"code", "message", "correlation_id"}


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


async def test_the_configured_origin_may_post_to_the_endpoint() -> None:
    application = _grounded_application()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.options(
            ASK_PATH,
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "POST" in response.headers["Access-Control-Allow-Methods"]
