"""Tests for uploaded-document extraction and deterministic chunking."""

from hashlib import sha256
from io import BytesIO

import pytest
from docx import Document

from app.services.document_ingestion import (
    DocumentIngestionError,
    DocumentIngestionErrorCode,
    ingest_document,
)


def test_text_file_is_split_at_paragraph_boundaries() -> None:
    result = ingest_document(
        "policy.txt",
        b"First paragraph.\n\nSecond paragraph.",
        max_chunk_chars=20,
    )

    assert [chunk.content_text for chunk in result.chunks] == [
        "First paragraph.",
        "Second paragraph.",
    ]
    assert [chunk.chunk_index for chunk in result.chunks] == [0, 1]


def test_long_markdown_text_is_split_and_preserved() -> None:
    content = "abcdefghijklmnopqrstuvwxyz"
    result = ingest_document("policy.MD", content.encode(), max_chunk_chars=10)

    assert "".join(chunk.content_text for chunk in result.chunks) == content
    assert all(len(chunk.content_text) <= 10 for chunk in result.chunks)


def test_docx_text_is_extracted() -> None:
    document = Document()
    document.add_paragraph("DOCX content")
    output = BytesIO()
    document.save(output)

    result = ingest_document("policy.docx", output.getvalue())

    assert result.extracted_text == "DOCX content"
    assert result.chunks[0].content_text == "DOCX content"


def test_chunk_hash_is_sha256_of_content() -> None:
    chunk = ingest_document("notes.txt", b"Useful notes.").chunks[0]

    assert chunk.content_hash == sha256(chunk.content_text.encode()).hexdigest()


@pytest.mark.parametrize(
    ("filename", "content", "code"),
    [
        ("policy.rtf", b"Policy text", DocumentIngestionErrorCode.UNSUPPORTED_FORMAT),
        ("policy.pdf", b"not a PDF", DocumentIngestionErrorCode.INVALID_DOCUMENT),
        ("empty.txt", b" \n ", DocumentIngestionErrorCode.EMPTY_DOCUMENT),
    ],
)
def test_unreadable_or_unsupported_file_is_rejected(
    filename: str,
    content: bytes,
    code: DocumentIngestionErrorCode,
) -> None:
    with pytest.raises(DocumentIngestionError) as exc_info:
        ingest_document(filename, content)

    assert exc_info.value.code is code


def test_non_positive_chunk_limit_is_rejected() -> None:
    with pytest.raises(DocumentIngestionError) as exc_info:
        ingest_document("notes.txt", b"Useful notes.", max_chunk_chars=0)

    assert exc_info.value.code is DocumentIngestionErrorCode.INVALID_MAX_CHUNK_CHARS