"""Rate-limit behaviour of the HR grounded answer endpoint.

The limiter lives on the application instance, so each test composes its own
application and starts from a clean set of windows.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.api.dependencies import (
    get_current_user,
    get_embedding_provider,
    get_embedding_repository,
    get_llm_provider,
)
from app.core.config import Settings
from app.core.rate_limit import RATE_LIMITED_MESSAGE, RETRY_AFTER_HEADER
from app.domain.accounts import UserAccount
from app.domain.retrieval import SemanticSearchRecord
from app.main import create_app
from app.repositories.embeddings import EmbeddingRepository

ASK_PATH = "/api/v1/hr/ask"
HEALTH_PATH = "/api/v1/health"
TENANT_ID = "tenant-synthetic"
QUESTION = "How many annual leave days do employees receive?"
FAKE_API_KEY = "test-api-key-not-a-real-secret"
ANSWER = "Employees receive twenty-one working days of annual leave. [S1]"

VIEWER = "203.0.113.10"
OTHER_VIEWER = "203.0.113.99"
CLOUDFRONT_EDGE = "198.51.100.5"


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


class _StubLLMProvider:
    @property
    def model_name(self) -> str:
        return "stub-llm"

    @property
    def model_version(self) -> str:
        return "0.0.1"

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        return ANSWER


def _record() -> SemanticSearchRecord:
    return SemanticSearchRecord(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        embedding_set_id=uuid4(),
        document_key="HR-SYNTHETIC-LEAVE-001",
        document_title="Synthetic Annual Leave Policy",
        chunk_index=0,
        heading_path="Synthetic Annual Leave Policy > Entitlement",
        content_text="Every full-time employee receives twenty-one working days.",
        distance=0.12,
    )


def _application(*, max_requests: int = 5) -> FastAPI:
    """Compose the real application with deterministic collaborators."""
    repository = Mock(spec=EmbeddingRepository)
    repository.search_similar_chunks.return_value = (_record(),)
    application = create_app(
        Settings(
            app_env="test",
            gemini_api_key=FAKE_API_KEY,  # type: ignore[arg-type]
            rate_limit_requests=max_requests,
            rate_limit_window_seconds=60,
            rate_limit_trusted_proxy_hops=1,
        )
    )
    application.dependency_overrides[get_embedding_provider] = _StubEmbeddingProvider
    application.dependency_overrides[get_llm_provider] = _StubLLMProvider
    application.dependency_overrides[get_embedding_repository] = lambda: repository
    application.dependency_overrides[get_current_user] = lambda: UserAccount(
        id=uuid4(),
        email="tester@example.com",
        display_name="Tester",
        theme="system",
        avatar_path=None,
        created_at=datetime.now(UTC),
    )
    return application


async def _ask(application: FastAPI, *, viewer: str = VIEWER) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            ASK_PATH,
            json={"question": QUESTION, "tenant_id": TENANT_ID},
            headers={"X-Forwarded-For": f"{viewer}, {CLOUDFRONT_EDGE}"},
        )


async def _health(application: FastAPI, *, viewer: str = VIEWER) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(
            HEALTH_PATH,
            headers={"X-Forwarded-For": f"{viewer}, {CLOUDFRONT_EDGE}"},
        )


async def test_requests_below_the_limit_all_succeed() -> None:
    application = _application(max_requests=5)

    statuses = [(await _ask(application)).status_code for _ in range(5)]

    assert statuses == [200] * 5


async def test_exceeding_the_limit_returns_429() -> None:
    application = _application(max_requests=5)
    for _ in range(5):
        await _ask(application)

    response = await _ask(application)

    assert response.status_code == 429


async def test_the_429_uses_the_standard_error_contract() -> None:
    application = _application(max_requests=1)
    await _ask(application)

    response = await _ask(application)

    body = response.json()
    assert body["error"]["code"] == "HTTP_429"
    assert body["error"]["message"] == RATE_LIMITED_MESSAGE
    assert body["error"]["correlation_id"] == response.headers["X-Correlation-ID"]
    assert int(response.headers[RETRY_AFTER_HEADER]) >= 1


async def test_the_health_endpoint_is_never_rate_limited() -> None:
    application = _application(max_requests=1)
    await _ask(application)
    assert (await _ask(application)).status_code == 429

    statuses = [(await _health(application)).status_code for _ in range(10)]

    assert statuses == [200] * 10


async def test_one_client_being_limited_does_not_affect_another() -> None:
    application = _application(max_requests=1)
    await _ask(application, viewer=VIEWER)
    assert (await _ask(application, viewer=VIEWER)).status_code == 429

    response = await _ask(application, viewer=OTHER_VIEWER)

    assert response.status_code == 200


async def test_limiter_state_is_not_shared_between_applications() -> None:
    """Each composed application starts from clean windows."""
    exhausted = _application(max_requests=1)
    await _ask(exhausted)
    assert (await _ask(exhausted)).status_code == 429

    response = await _ask(_application(max_requests=1))

    assert response.status_code == 200


async def test_request_validation_still_runs_for_allowed_requests() -> None:
    application = _application(max_requests=5)
    transport = ASGITransport(app=application)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            ASK_PATH,
            json={"question": "   ", "tenant_id": TENANT_ID},
            headers={"X-Forwarded-For": f"{VIEWER}, {CLOUDFRONT_EDGE}"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
