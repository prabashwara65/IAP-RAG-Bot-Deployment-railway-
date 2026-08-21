"""OIAP FastAPI application composition root."""

from __future__ import annotations

from typing import cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException
from starlette.types import ExceptionHandler

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.database import create_database_engine, create_session_factory
from app.core.exceptions import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationIdMiddleware
from app.core.rate_limit import FixedWindowRateLimiter, RateLimitPolicy


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create a validated, independently testable Phase 0 application."""
    active_settings = settings or get_settings()
    configure_logging(active_settings.log_level)

    application = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
    )
    application.state.settings = active_settings
    engine = create_database_engine(active_settings)
    application.state.database_engine = engine
    application.state.session_factory = create_session_factory(engine)
    # One limiter per application instance, so its counters are never shared
    # between separately composed applications.
    application.state.rate_limiter = FixedWindowRateLimiter(
        RateLimitPolicy(
            max_requests=active_settings.rate_limit_requests,
            window_seconds=active_settings.rate_limit_window_seconds,
        )
    )

    application.add_exception_handler(
        HTTPException,
        cast(ExceptionHandler, http_exception_handler),
    )
    application.add_exception_handler(
        RequestValidationError,
        cast(ExceptionHandler, validation_exception_handler),
    )
    application.add_exception_handler(
        Exception,
        cast(ExceptionHandler, unhandled_exception_handler),
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type", "X-Correlation-ID"],
    )
    application.add_middleware(CorrelationIdMiddleware)
    application.include_router(api_router, prefix=active_settings.api_prefix)

    get_logger("startup").info(
        "Application configured",
        extra={"app_version": active_settings.app_version},
    )
    return application


app = create_app()
