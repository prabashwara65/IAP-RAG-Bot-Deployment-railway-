"""Integration tests for service status and API errors."""

from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.core.config import Settings
from app.main import create_app


async def _request(
    method: str,
    path: str,
    *,
    application: FastAPI | None = None,
    raise_app_exceptions: bool = True,
    **kwargs: Any,
) -> Response:
    active_application = application or create_app(Settings(app_env="development"))
    transport = ASGITransport(
        app=active_application,
        raise_app_exceptions=raise_app_exceptions,
    )
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


async def test_health_endpoint_returns_expected_schema() -> None:
    response = await _request("GET", "/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "office-intelligence-automation-platform-oiap",
        "environment": "development",
    }
    assert response.headers["X-Correlation-ID"]


async def test_readiness_checks_only_loaded_configuration() -> None:
    response = await _request("GET", "/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["X-Correlation-ID"]


async def test_cors_allows_only_configured_origin() -> None:
    allowed = await _request(
        "OPTIONS",
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    unconfigured = await _request(
        "OPTIONS",
        "/api/v1/health",
        headers={
            "Origin": "https://unconfigured.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "Access-Control-Allow-Origin" not in unconfigured.headers


async def test_http_errors_use_common_contract() -> None:
    response = await _request("GET", "/api/v1/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "HTTP_404",
            "message": "Not Found",
            "correlation_id": response.headers["X-Correlation-ID"],
        }
    }


async def test_validation_errors_use_common_contract() -> None:
    application = create_app(Settings(app_env="test"))

    @application.get("/api/v1/test-validation")
    async def validation_route(required_count: int) -> dict[str, int]:
        return {"required_count": required_count}

    response = await _request(
        "GET",
        "/api/v1/test-validation",
        application=application,
        params={"required_count": "not-an-integer"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Request validation failed."
    assert body["error"]["correlation_id"] == response.headers["X-Correlation-ID"]
    assert body["error"]["details"][0]["location"] == ["query", "required_count"]


async def test_internal_errors_are_logged_but_not_exposed() -> None:
    application: FastAPI = create_app(Settings(app_env="test"))

    @application.get("/api/v1/test-error")
    async def error_route() -> None:
        raise RuntimeError("private internal failure detail")

    response = await _request(
        "GET",
        "/api/v1/test-error",
        application=application,
        raise_app_exceptions=False,
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred.",
            "correlation_id": response.headers["X-Correlation-ID"],
        }
    }
    assert "private internal failure detail" not in response.text
    assert "traceback" not in response.text.lower()
