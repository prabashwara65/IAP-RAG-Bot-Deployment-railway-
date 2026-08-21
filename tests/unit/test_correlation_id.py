"""Tests for correlation IDs and structured logging."""

import json
from io import StringIO
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.middleware import MAX_CORRELATION_ID_LENGTH, normalize_correlation_id
from app.main import create_app


async def _get(**kwargs: Any) -> Response:
    application = create_app(Settings(app_env="test"))
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/api/v1/health", **kwargs)


async def test_valid_incoming_correlation_id_is_preserved() -> None:
    response = await _get(headers={"X-Correlation-ID": "request-123:child"})

    assert response.headers["X-Correlation-ID"] == "request-123:child"


async def test_missing_correlation_id_generates_uuid() -> None:
    response = await _get()

    assert str(UUID(response.headers["X-Correlation-ID"])) == response.headers[
        "X-Correlation-ID"
    ]


async def test_oversized_incoming_correlation_id_is_replaced_in_response() -> None:
    oversized = "x" * (MAX_CORRELATION_ID_LENGTH + 1)

    response = await _get(headers={"X-Correlation-ID": oversized})

    returned = response.headers["X-Correlation-ID"]
    assert returned != oversized
    assert str(UUID(returned)) == returned


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "contains spaces",
        "contains\nnewline",
        "x" * (MAX_CORRELATION_ID_LENGTH + 1),
        "",
    ],
)
def test_unsafe_correlation_id_is_replaced(unsafe_value: str) -> None:
    normalized = normalize_correlation_id(unsafe_value)

    assert normalized != unsafe_value
    assert str(UUID(normalized)) == normalized


def test_structured_logging_does_not_serialize_secret_like_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_value = "do-not-log-this-value"
    monkeypatch.setenv("UNRELATED_SECRET_TOKEN", secret_value)
    stream = StringIO()
    logger = configure_logging("INFO", stream=stream)

    logger.info("Configuration loaded")

    payload = json.loads(stream.getvalue())
    assert payload["level"] == "INFO"
    assert payload["logger"] == "oiap"
    assert payload["message"] == "Configuration loaded"
    assert "timestamp" in payload
    assert "correlation_id" in payload
    assert secret_value not in stream.getvalue()
