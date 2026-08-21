"""Tests for deterministic section-aware HR Markdown chunking."""

from hashlib import sha256
from typing import Any

import pytest

from app.schemas.hr_documents import HRDocumentMetadata
from app.services.hr_chunking import (
    HEADING_PATH_DELIMITER,
    HRChunkingError,
    HRChunkingErrorCode,
    chunk_hr_markdown,
)
from app.services.hr_markdown import (
    SYNTHETIC_DOCUMENT_NOTICE,
    render_hr_document_markdown,
)


def _valid_payload() -> dict[str, Any]:
    return {
        "document_title": "Synthetic Leave Policy",
        "document_type": "Policy",
        "department": "Human Resources",
        "summary_purpose": "Explains synthetic leave rules for demonstration.",
        "language": "English",
        "version": "1.0",
        "effective_date": "2026-08-01",
        "content_owner": "Synthetic HR Team",
        "approval_status": "Approved",
        "approved_for_rag": "Approved",
        "document_status": "Approved",
        "access_level": "Internal General",
        "contains_personal_data": "No",
        "contains_confidential_data": "No",
        "synthetic": True,
        "official_company_document": False,
        "data_mode": "synthetic_demo",
        "document_content": "This is synthetic HR policy content.",
    }


def _markdown(**overrides: Any) -> str:
    payload = _valid_payload()
    payload.update(overrides)
    document = HRDocumentMetadata.model_validate(payload)
    return render_hr_document_markdown(document)


def _document_content_chunks(markdown: str, max_chunk_chars: int) -> list[str]:
    return [
        chunk.content_text
        for chunk in chunk_hr_markdown(markdown, max_chunk_chars=max_chunk_chars)
        if chunk.heading_path.endswith("Document Content")
    ]


def test_standardized_markdown_creates_expected_section_chunks() -> None:
    chunks = chunk_hr_markdown(_markdown())

    assert [(chunk.heading_path, chunk.content_text) for chunk in chunks] == [
        (
            "Synthetic Leave Policy > Purpose",
            "Explains synthetic leave rules for demonstration.",
        ),
        (
            "Synthetic Leave Policy > Document Content",
            "This is synthetic HR policy content.",
        ),
    ]


def test_front_matter_and_synthetic_notice_are_excluded() -> None:
    chunks = chunk_hr_markdown(_markdown())
    combined_content = "\n".join(chunk.content_text for chunk in chunks)

    assert "document_title:" not in combined_content
    assert "effective_date:" not in combined_content
    assert SYNTHETIC_DOCUMENT_NOTICE not in combined_content


def test_heading_path_preserves_nested_section_hierarchy() -> None:
    chunks = chunk_hr_markdown(
        _markdown(
            document_content=(
                "Overview paragraph.\n\n"
                "### Responsibilities\n\nSynthetic responsibility details."
            )
        )
    )

    assert HEADING_PATH_DELIMITER == " > "
    assert [chunk.heading_path for chunk in chunks] == [
        "Synthetic Leave Policy > Purpose",
        "Synthetic Leave Policy > Document Content",
        "Synthetic Leave Policy > Document Content > Responsibilities",
    ]


def test_chunk_indexes_start_at_zero_and_are_sequential() -> None:
    chunks = chunk_hr_markdown(_markdown(keywords=["leave", "synthetic"]))

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_same_input_and_limit_produce_identical_chunks() -> None:
    markdown = _markdown()

    assert chunk_hr_markdown(markdown, max_chunk_chars=80) == chunk_hr_markdown(
        markdown,
        max_chunk_chars=80,
    )


def test_content_hash_is_sha256_of_normalized_chunk_content() -> None:
    chunk = chunk_hr_markdown(_markdown())[0]

    assert chunk.content_hash == sha256(chunk.content_text.encode("utf-8")).hexdigest()
    assert len(chunk.content_hash) == 64


def test_equal_content_has_equal_hash_and_different_content_has_different_hash() -> None:
    first = chunk_hr_markdown(_markdown(summary_purpose="Shared purpose."))[0]
    same = chunk_hr_markdown(_markdown(summary_purpose="Shared purpose."))[0]
    different = chunk_hr_markdown(_markdown(summary_purpose="Different purpose."))[0]

    assert first.content_hash == same.content_hash
    assert first.content_hash != different.content_hash


def test_no_empty_chunks_are_created() -> None:
    chunks = chunk_hr_markdown(_markdown(section_headings=["Scope", "Responsibilities"]))

    assert chunks
    assert all(chunk.content_text for chunk in chunks)
    assert all(chunk.content_text == chunk.content_text.strip() for chunk in chunks)


def test_section_content_order_is_preserved() -> None:
    chunks = chunk_hr_markdown(
        _markdown(
            section_headings=["Scope"],
            related_documents=["Synthetic Handbook"],
            keywords=["leave"],
            reviewer_notes="Synthetic review note.",
        )
    )

    assert [chunk.heading_path.rsplit(" > ", 1)[-1] for chunk in chunks] == [
        "Purpose",
        "Document Content",
        "Section Headings",
        "Related Documents",
        "Keywords",
        "Reviewer Notes",
    ]


def test_long_section_prefers_paragraph_boundaries() -> None:
    first_paragraph = "First paragraph stays whole."
    second_paragraph = "Second paragraph stays whole."
    markdown = _markdown(
        document_content=f"{first_paragraph}\n\n{second_paragraph}"
    )

    content_chunks = _document_content_chunks(markdown, max_chunk_chars=35)

    assert content_chunks == [first_paragraph, second_paragraph]


def test_oversized_single_paragraph_uses_deterministic_fallback() -> None:
    content = "abcdefghijklmnopqrstuvwxyz"
    markdown = _markdown(document_content=content)

    content_chunks = _document_content_chunks(markdown, max_chunk_chars=10)

    assert content_chunks == ["abcdefghij", "klmnopqrst", "uvwxyz"]
    assert "".join(content_chunks) == content
    assert all(len(chunk) <= 10 for chunk in content_chunks)


def test_all_retrieval_content_is_preserved_across_paragraph_chunks() -> None:
    content = "Alpha retrieval paragraph.\n\nBeta retrieval paragraph."
    content_chunks = _document_content_chunks(
        _markdown(document_content=content),
        max_chunk_chars=30,
    )

    assert "\n\n".join(content_chunks) == content


def test_optional_markdown_sections_are_chunked_with_their_heading_paths() -> None:
    chunks = chunk_hr_markdown(
        _markdown(
            keywords=["leave", "synthetic"],
            related_documents=["Synthetic Handbook"],
        )
    )

    by_path = {chunk.heading_path: chunk.content_text for chunk in chunks}
    assert by_path["Synthetic Leave Policy > Related Documents"] == "- Synthetic Handbook"
    assert by_path["Synthetic Leave Policy > Keywords"] == "- leave\n- synthetic"


@pytest.mark.parametrize(
    ("markdown", "code"),
    [
        ("# Missing front matter", HRChunkingErrorCode.MISSING_FRONT_MATTER),
        ("---\ndocument_title: \"Test\"", HRChunkingErrorCode.UNCLOSED_FRONT_MATTER),
        ("---\ndocument_title: \"Test\"\n---", HRChunkingErrorCode.MISSING_MARKDOWN_BODY),
        (
            "---\ndocument_title: \"Test\"\n---\n\nBody without H1",
            HRChunkingErrorCode.MISSING_DOCUMENT_HEADING,
        ),
        (
            f"---\ndocument_title: \"Test\"\n---\n\n# Test\n\n> {SYNTHETIC_DOCUMENT_NOTICE}",
            HRChunkingErrorCode.NO_MEANINGFUL_SECTIONS,
        ),
    ],
)
def test_malformed_standardized_markdown_is_rejected(
    markdown: str,
    code: HRChunkingErrorCode,
) -> None:
    with pytest.raises(HRChunkingError) as exc_info:
        chunk_hr_markdown(markdown)

    assert exc_info.value.code is code
    assert str(exc_info.value)


@pytest.mark.parametrize("max_chunk_chars", [0, -1])
def test_invalid_max_chunk_chars_is_rejected(max_chunk_chars: int) -> None:
    with pytest.raises(HRChunkingError) as exc_info:
        chunk_hr_markdown(_markdown(), max_chunk_chars=max_chunk_chars)

    assert exc_info.value.code is HRChunkingErrorCode.INVALID_MAX_CHUNK_CHARS
