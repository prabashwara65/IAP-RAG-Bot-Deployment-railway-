"""Contracts for uploaded-document extraction and chunk previews."""

from uuid import UUID

from pydantic import BaseModel


class DocumentChunkResponse(BaseModel):
    chunk_index: int
    content_text: str
    content_hash: str


class DocumentIngestionResponse(BaseModel):
    filename: str
    document_type: str
    document_key: str
    version_id: UUID
    version_status: str
    chunk_count: int
    chunks: list[DocumentChunkResponse]