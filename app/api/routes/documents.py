"""Admin-only document extraction and candidate-vector persistence endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import get_embedding_provider, get_session
from app.api.permissions import get_current_admin
from app.core.config import Settings
from app.core.rate_limit import enforce_rate_limit
from app.providers.embeddings import EmbeddingProvider
from app.providers.gemini_embeddings import GeminiEmbeddingError
from app.schemas.document_ingestion import (
    DocumentChunkResponse,
    DocumentIngestionResponse,
)
from app.schemas.hr_documents import DocumentType
from app.services.document_activation import activate_document
from app.services.document_ingestion import (
    DocumentIngestionError,
    DocumentIngestionErrorCode,
    ingest_document,
    persist_ingested_document,
)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(get_current_admin), Depends(enforce_rate_limit)],
)

_ERROR_STATUS = {
    DocumentIngestionErrorCode.UNSUPPORTED_FORMAT: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    DocumentIngestionErrorCode.INVALID_DOCUMENT: status.HTTP_422_UNPROCESSABLE_CONTENT,
    DocumentIngestionErrorCode.EMPTY_DOCUMENT: status.HTTP_422_UNPROCESSABLE_CONTENT,
    DocumentIngestionErrorCode.INVALID_MAX_CHUNK_CHARS: status.HTTP_500_INTERNAL_SERVER_ERROR,
    DocumentIngestionErrorCode.PARSER_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
}


@router.post("/ingest", response_model=DocumentIngestionResponse)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File()],
    document_type: Annotated[DocumentType, Form()],
    session: Annotated[Session, Depends(get_session)],
    embedding_provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
) -> DocumentIngestionResponse:
    """Extract an upload and persist its chunks/vectors as a candidate version."""
    settings: Settings = request.app.state.settings
    content = await file.read(settings.document_max_bytes + 1)
    if len(content) > settings.document_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"The document exceeds the {settings.document_max_bytes}-byte upload limit.",
        )

    try:
        ingested = ingest_document(file.filename or "", content)
    except DocumentIngestionError as error:
        raise HTTPException(
            status_code=_ERROR_STATUS[error.code],
            detail=str(error),
        ) from error

    try:
        persisted = persist_ingested_document(
            session,
            tenant_id="tenant-real",
            content=content,
            document=ingested,
            embedding_provider=embedding_provider,
            document_type=document_type.value,
        )
    except GeminiEmbeddingError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The document could not be embedded for vector storage.",
        ) from error

    version_status = persisted.version_status
    activated_document_type = document_type.value
    if settings.auto_activate_uploads:
        version_status = activate_document(
            session,
            persisted.document_key,
            version_id=persisted.version_id,
        ).status
        activated_document_type = "CV"

    return DocumentIngestionResponse(
        filename=ingested.filename,
        document_type=activated_document_type,
        document_key=persisted.document_key,
        version_id=persisted.version_id,
        version_status=version_status.value,
        chunk_count=len(ingested.chunks),
        chunks=[
            DocumentChunkResponse(
                chunk_index=chunk.chunk_index,
                content_text=chunk.content_text,
                content_hash=chunk.content_hash,
            )
            for chunk in ingested.chunks
        ],
    )