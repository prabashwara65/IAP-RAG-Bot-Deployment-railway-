"""Request correlation middleware and logging context."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_ID_HEADER = "X-Correlation-ID"
MAX_CORRELATION_ID_LENGTH = 128
_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_correlation_id: ContextVar[str | None] = ContextVar(
    "correlation_id",
    default=None,
)


def get_correlation_id() -> str | None:
    """Return the correlation ID for the current request context, if present."""
    return _correlation_id.get()


def normalize_correlation_id(value: str | None) -> str:
    """Preserve a safe incoming identifier or replace it with a generated UUID."""
    if (
        value is not None
        and len(value) <= MAX_CORRELATION_ID_LENGTH
        and _SAFE_CORRELATION_ID.fullmatch(value) is not None
    ):
        return value
    return str(uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a safe correlation ID to request state, logs, and responses."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        correlation_id = normalize_correlation_id(
            request.headers.get(CORRELATION_ID_HEADER)
        )
        request.state.correlation_id = correlation_id
        token: Token[str | None] = _correlation_id.set(correlation_id)
        try:
            response = await call_next(request)
            response.headers[CORRELATION_ID_HEADER] = correlation_id
            return response
        finally:
            _correlation_id.reset(token)
