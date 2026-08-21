"""Common Phase 0 response schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from app.core.config import AppEnvironment


class HealthResponse(BaseModel):
    """Application process health response."""

    status: Literal["healthy"]
    service: str
    environment: AppEnvironment


class ReadinessResponse(BaseModel):
    """Phase 0 configuration readiness response."""

    status: Literal["ready"]


class ErrorDetail(BaseModel):
    """Stable error details safe for API clients."""

    code: str
    message: str
    correlation_id: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    """Common error response envelope."""

    error: ErrorDetail
