"""HR grounded answer endpoint.

The route owns HTTP concerns only: contract validation, collaborator
injection, and mapping known failures onto stable status codes. Every
retrieval, prompting, and grounding decision stays in ``app.services.hr_rag``.
"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import (
    get_current_user,
    get_embedding_provider,
    get_embedding_repository,
    get_llm_provider,
)
from app.core.logging import get_logger
from app.core.rate_limit import enforce_rate_limit
from app.providers.embeddings import EmbeddingProvider
from app.providers.gemini_embeddings import (
    GeminiEmbeddingError,
    GeminiEmbeddingErrorCode,
)
from app.providers.gemini_llm import GeminiLLMError, GeminiLLMErrorCode
from app.providers.llm import LLMProvider
from app.repositories.embeddings import EmbeddingRepository
from app.schemas.hr_rag import HRAskRequest, HRAskResponse
from app.services.hr_rag import HRRAGError, HRRAGErrorCode, answer_hr_question
from app.services.hr_retrieval import HRRetrievalError, HRRetrievalErrorCode

router = APIRouter(prefix="/hr", tags=["hr-rag"])

logger = get_logger("api.hr_rag")

INVALID_QUESTION_MESSAGE = "The question could not be answered as submitted."
ANSWER_SERVICE_MESSAGE = "The answering service could not produce a grounded answer."
EVIDENCE_STORE_MESSAGE = "The approved HR evidence store is unavailable."
CONFIGURATION_MESSAGE = "The answering service is not configured."

_REQUEST_RETRIEVAL_CODES = frozenset(
    {
        HRRetrievalErrorCode.BLANK_QUERY,
        HRRetrievalErrorCode.BLANK_TENANT_ID,
        HRRetrievalErrorCode.INVALID_TOP_K,
    }
)
_SERVER_RAG_CODES = frozenset(
    {
        HRRAGErrorCode.INVALID_MAX_CONTEXT_CHARS,
        HRRAGErrorCode.CONTEXT_BUDGET_TOO_SMALL,
    }
)
_PROVIDER_CONFIGURATION_CODES = frozenset(
    {
        GeminiEmbeddingErrorCode.MISSING_API_KEY.value,
        GeminiEmbeddingErrorCode.MISSING_MODEL.value,
        GeminiLLMErrorCode.MISSING_API_KEY.value,
        GeminiLLMErrorCode.MISSING_MODEL.value,
    }
)


def _fail(
    status_code: int,
    message: str,
    *,
    failure_code: str,
    error: Exception,
) -> NoReturn:
    """Log the real failure and return a stable, non-revealing response.

    Only the curated message reaches the client. Provider and service messages
    are never interpolated, so no request, credential, or schema detail can
    leak through an error body.
    """
    logger.warning(
        "HR grounded answer request failed",
        extra={"failure_code": failure_code, "status_code": status_code},
    )
    raise HTTPException(status_code=status_code, detail=message) from error


@router.post(
    "/ask",
    response_model=HRAskResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(enforce_rate_limit), Depends(get_current_user)],
)
def ask_hr_question(
    payload: HRAskRequest,
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    llm_provider: Annotated[LLMProvider, Depends(get_llm_provider)],
    repository: Annotated[EmbeddingRepository, Depends(get_embedding_repository)],
) -> HRAskResponse:
    """Answer one HR question strictly from that tenant's approved HR sources.

    Declared with ``def`` rather than ``async def`` on purpose: the grounded
    answer service performs blocking database and provider I/O, so FastAPI runs
    it in a worker thread instead of stalling the event loop.

    An answer with no supporting evidence is a normal 200 response carrying
    ``insufficient_evidence``; it is not an error.
    """
    try:
        answer = answer_hr_question(
            question=payload.question,
            tenant_id=payload.tenant_id,
            embedding_provider=embedding_provider,
            llm_provider=llm_provider,
            repository=repository,
        )
    except HRRetrievalError as error:
        if error.code in _REQUEST_RETRIEVAL_CODES:
            _fail(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                INVALID_QUESTION_MESSAGE,
                failure_code=error.code.value,
                error=error,
            )
        _fail(
            status.HTTP_502_BAD_GATEWAY,
            ANSWER_SERVICE_MESSAGE,
            failure_code=error.code.value,
            error=error,
        )
    except HRRAGError as error:
        if error.code is HRRAGErrorCode.BLANK_QUESTION:
            _fail(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                INVALID_QUESTION_MESSAGE,
                failure_code=error.code.value,
                error=error,
            )
        if error.code in _SERVER_RAG_CODES:
            _fail(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                ANSWER_SERVICE_MESSAGE,
                failure_code=error.code.value,
                error=error,
            )
        _fail(
            status.HTTP_502_BAD_GATEWAY,
            ANSWER_SERVICE_MESSAGE,
            failure_code=error.code.value,
            error=error,
        )
    except (GeminiEmbeddingError, GeminiLLMError) as error:
        if error.code.value in _PROVIDER_CONFIGURATION_CODES:
            _fail(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                CONFIGURATION_MESSAGE,
                failure_code=error.code.value,
                error=error,
            )
        _fail(
            status.HTTP_502_BAD_GATEWAY,
            ANSWER_SERVICE_MESSAGE,
            failure_code=error.code.value,
            error=error,
        )
    except SQLAlchemyError as error:
        _fail(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            EVIDENCE_STORE_MESSAGE,
            failure_code="evidence_store_unavailable",
            error=error,
        )

    return HRAskResponse.from_domain(answer)
