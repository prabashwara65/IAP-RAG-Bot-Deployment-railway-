"""FastAPI dependency wiring for the HR RAG endpoint.

Dependencies only build collaborators. Retrieval, prompting, ranking,
embedding, and answer generation stay in the services layer.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.domain.accounts import UserAccount
from app.providers.embeddings import EmbeddingProvider
from app.providers.gemini_embeddings import (
    GeminiEmbeddingError,
    gemini_embedding_provider_from_settings,
)
from app.providers.gemini_llm import GeminiLLMError, gemini_llm_provider_from_settings
from app.providers.llm import LLMProvider
from app.repositories.embeddings import EmbeddingRepository
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.repositories.sqlalchemy_users import SQLAlchemyUserAccountRepository
from app.repositories.users import UserAccountRepository
from app.services.auth import AuthError, AuthService

logger = get_logger("api.dependencies")

PROVIDER_UNAVAILABLE_MESSAGE = "The answering service is not configured."
SIGN_IN_REQUIRED_MESSAGE = "Sign in is required."
_bearer_scheme = HTTPBearer(auto_error=False)


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


def get_account_repository(
    session: Annotated[Session, Depends(get_session)],
) -> UserAccountRepository:
    """Bind the account repository to this request's session."""
    return SQLAlchemyUserAccountRepository(session)


def get_auth_service(
    request: Request,
    repository: Annotated[UserAccountRepository, Depends(get_account_repository)],
) -> AuthService:
    """Compose the auth service for this request."""
    return AuthService(repository, get_request_settings(request))


def get_bearer_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = None,
) -> str | None:
    """Read a bearer token from the Authorization header when present."""
    if credentials is not None and credentials.credentials.strip():
        return credentials.credentials.strip()
    header = request.headers.get("Authorization")
    if header is None:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def get_current_user(
    request: Request,
    auth: Annotated[AuthService, Depends(get_auth_service)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> UserAccount:
    """Require a valid session for the current request."""
    token = get_bearer_token(request, credentials)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=SIGN_IN_REQUIRED_MESSAGE,
        )
    try:
        return auth.user_for_token(token)
    except AuthError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=SIGN_IN_REQUIRED_MESSAGE,
        ) from error


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
        provider = gemini_embedding_provider_from_settings(
            get_request_settings(request)
        )
    except GeminiEmbeddingError as error:
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
        provider = gemini_llm_provider_from_settings(get_request_settings(request))
    except GeminiLLMError as error:
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