"""FastAPI dependency wiring for the HR RAG endpoint.

Dependencies only build collaborators. Retrieval, prompting, ranking,
embedding, and answer generation stay in the services layer.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.providers.embeddings import EmbeddingProvider
from app.providers.llm import LLMProvider
from app.providers.openai_embeddings import (
    OpenAIEmbeddingError,
    openai_embedding_provider_from_settings,
)
from app.providers.openai_llm import OpenAILLMError, openai_llm_provider_from_settings
from app.repositories.embeddings import EmbeddingRepository
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository

logger = get_logger("api.dependencies")

PROVIDER_UNAVAILABLE_MESSAGE = "The answering service is not configured."


def get_request_settings(request: Request) -> Settings:
    """Return the settings the application was composed with."""
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> Iterator[Session]:
    """Yield one transactional session per request."""
    with session_scope(request.app.state.session_factory) as session:
        yield session


def get_embedding_repository(
    session: Annotated[Session, Depends(get_session)],
) -> EmbeddingRepository:
    """Bind the pgvector repository to this request's session."""
    return PostgresEmbeddingRepository(session)


def get_embedding_provider(request: Request) -> EmbeddingProvider:
    """Return the process-wide embedding provider, building it on first use.

    Construction is deferred so the application still starts without a
    credential; only requests that need a provider fail. The built provider is
    cached on application state because each one owns an HTTP client.
    """
    cached: EmbeddingProvider | None = getattr(
        request.app.state, "embedding_provider", None
    )
    if cached is not None:
        return cached

    try:
        provider = openai_embedding_provider_from_settings(
            get_request_settings(request)
        )
    except OpenAIEmbeddingError as error:
        logger.error(
            "Embedding provider unavailable",
            extra={"failure_code": error.code.value},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=PROVIDER_UNAVAILABLE_MESSAGE,
        ) from error

    request.app.state.embedding_provider = provider
    return provider


def get_llm_provider(request: Request) -> LLMProvider:
    """Return the process-wide language model provider, building it on first use."""
    cached: LLMProvider | None = getattr(request.app.state, "llm_provider", None)
    if cached is not None:
        return cached

    try:
        provider = openai_llm_provider_from_settings(get_request_settings(request))
    except OpenAILLMError as error:
        logger.error(
            "Language model provider unavailable",
            extra={"failure_code": error.code.value},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=PROVIDER_UNAVAILABLE_MESSAGE,
        ) from error

    request.app.state.llm_provider = provider
    return provider
