"""Consistent safe API exception responses."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.logging import get_logger
from app.core.middleware import CORRELATION_ID_HEADER
from app.schemas.common import ErrorDetail, ErrorResponse

logger = get_logger("exceptions")


def _correlation_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    return value if isinstance(value, str) else "unavailable"


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    correlation_id = _correlation_id(request)
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            correlation_id=correlation_id,
            details=details,
        )
    )
    response_headers = {CORRELATION_ID_HEADER: correlation_id}
    if headers is not None:
        # The correlation header is authoritative and cannot be overridden.
        response_headers = {**headers, **response_headers}
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
        headers=response_headers,
    )


async def http_exception_handler(
    request: Request,
    exception: HTTPException,
) -> JSONResponse:
    """Translate FastAPI HTTP errors to the common error contract."""
    message = exception.detail if isinstance(exception.detail, str) else "Request failed."
    return _error_response(
        request,
        status_code=exception.status_code,
        code=f"HTTP_{exception.status_code}",
        message=message,
        headers=exception.headers,
    )


async def validation_exception_handler(
    request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    """Preserve safe validation locations and messages in the common contract."""
    details = [
        {
            "type": error.get("type"),
            "location": list(error.get("loc", ())),
            "message": error.get("msg"),
        }
        for error in exception.errors()
    ]
    return _error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        details=details,
    )


async def unhandled_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Log internal details and return a stable non-sensitive response."""
    logger.exception("Unhandled application exception", exc_info=exception)
    return _error_response(
        request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred.",
    )
