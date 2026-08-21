"""Deterministic section-aware chunking for standardized HR Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from app.services.hr_markdown import SYNTHETIC_DOCUMENT_NOTICE

DEFAULT_MAX_CHUNK_CHARS = 1200
HEADING_PATH_DELIMITER = " > "

_HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")
_PARAGRAPH_BOUNDARY_PATTERN = re.compile(r"\n[ \t]*\n+")


class HRChunkingErrorCode(StrEnum):
    INVALID_MAX_CHUNK_CHARS = "invalid_max_chunk_chars"
    MISSING_FRONT_MATTER = "missing_front_matter"
    UNCLOSED_FRONT_MATTER = "unclosed_front_matter"
    MISSING_MARKDOWN_BODY = "missing_markdown_body"
    MISSING_DOCUMENT_HEADING = "missing_document_heading"
    NO_MEANINGFUL_SECTIONS = "no_meaningful_sections"


class HRChunkingError(ValueError):
    """Raised when standardized HR Markdown cannot be chunked safely."""

    def __init__(self, code: HRChunkingErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class HRDocumentChunk:
    """In-memory chunk record aligned with the persisted ChunkModel fields."""

    chunk_index: int
    heading_path: str
    content_text: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class _Section:
    heading_path: str
    content: str


def _extract_markdown_body(markdown: str) -> str:
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines or lines[0] != "---":
        raise HRChunkingError(
            HRChunkingErrorCode.MISSING_FRONT_MATTER,
            "Standardized HR Markdown must begin with YAML front matter.",
        )
    try:
        closing_index = lines.index("---", 1)
    except ValueError as error:
        raise HRChunkingError(
            HRChunkingErrorCode.UNCLOSED_FRONT_MATTER,
            "Standardized HR Markdown front matter is not closed.",
        ) from error

    body = "\n".join(lines[closing_index + 1 :]).strip()
    if not body:
        raise HRChunkingError(
            HRChunkingErrorCode.MISSING_MARKDOWN_BODY,
            "Standardized HR Markdown has no body content.",
        )
    return body


def _parse_sections(body: str) -> tuple[_Section, ...]:
    lines = body.split("\n")
    first_content_line = next((line for line in lines if line.strip()), "")
    first_heading = _HEADING_PATTERN.fullmatch(first_content_line)
    if first_heading is None or len(first_heading.group(1)) != 1:
        raise HRChunkingError(
            HRChunkingErrorCode.MISSING_DOCUMENT_HEADING,
            "Standardized HR Markdown body must begin with a level-one document heading.",
        )

    heading_stack: list[tuple[int, str]] = []
    content_lines: list[str] = []
    sections: list[_Section] = []

    def flush_section() -> None:
        if not heading_stack:
            content_lines.clear()
            return
        retained_lines = content_lines
        if len(heading_stack) == 1:
            notice = f"> {SYNTHETIC_DOCUMENT_NOTICE}"
            retained_lines = [line for line in content_lines if line.strip() != notice]
        content = "\n".join(retained_lines).strip()
        if content:
            sections.append(
                _Section(
                    heading_path=HEADING_PATH_DELIMITER.join(
                        heading for _, heading in heading_stack
                    ),
                    content=content,
                )
            )
        content_lines.clear()

    for line in lines:
        heading_match = _HEADING_PATTERN.fullmatch(line)
        if heading_match is None:
            content_lines.append(line)
            continue

        flush_section()
        level = len(heading_match.group(1))
        heading = heading_match.group(2).strip()
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading))

    flush_section()
    return tuple(sections)


def _split_oversized_paragraph(paragraph: str, max_chunk_chars: int) -> list[str]:
    parts: list[str] = []
    remaining = paragraph.strip()
    while len(remaining) > max_chunk_chars:
        split_at = max(
            remaining.rfind(" ", 0, max_chunk_chars + 1),
            remaining.rfind("\n", 0, max_chunk_chars + 1),
            remaining.rfind("\t", 0, max_chunk_chars + 1),
        )
        if split_at <= 0:
            split_at = max_chunk_chars
        part = remaining[:split_at].rstrip()
        if part:
            parts.append(part)
        remaining = remaining[split_at:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


def _split_section_content(content: str, max_chunk_chars: int) -> tuple[str, ...]:
    paragraphs = [
        paragraph.strip()
        for paragraph in _PARAGRAPH_BOUNDARY_PATTERN.split(content.strip())
        if paragraph.strip()
    ]
    chunks: list[str] = []
    current = ""

    def flush_current() -> None:
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    for paragraph in paragraphs:
        if len(paragraph) > max_chunk_chars:
            flush_current()
            chunks.extend(_split_oversized_paragraph(paragraph, max_chunk_chars))
            continue
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chunk_chars:
            current = candidate
        else:
            flush_current()
            current = paragraph

    flush_current()
    return tuple(chunks)


def chunk_hr_markdown(
    markdown: str,
    *,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> tuple[HRDocumentChunk, ...]:
    """Split standardized HR Markdown into stable, section-aware retrieval chunks."""
    if max_chunk_chars <= 0:
        raise HRChunkingError(
            HRChunkingErrorCode.INVALID_MAX_CHUNK_CHARS,
            "max_chunk_chars must be greater than zero.",
        )

    body = _extract_markdown_body(markdown)
    sections = _parse_sections(body)
    chunks: list[HRDocumentChunk] = []
    for section in sections:
        for content in _split_section_content(section.content, max_chunk_chars):
            chunks.append(
                HRDocumentChunk(
                    chunk_index=len(chunks),
                    heading_path=section.heading_path,
                    content_text=content,
                    content_hash=sha256(content.encode("utf-8")).hexdigest(),
                )
            )

    if not chunks:
        raise HRChunkingError(
            HRChunkingErrorCode.NO_MEANINGFUL_SECTIONS,
            "Standardized HR Markdown contains no meaningful retrieval content.",
        )
    return tuple(chunks)
