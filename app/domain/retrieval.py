"""Persistence-neutral records returned by semantic retrieval repositories."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SemanticSearchRecord:
    """One matched chunk with its document context and vector distance.

    ``distance`` is a smaller-is-closer distance produced by the repository
    implementation. No ranking, scoring, or normalization is applied here.
    """

    chunk_id: UUID
    document_id: UUID
    document_version_id: UUID
    embedding_set_id: UUID
    document_key: str
    document_title: str
    chunk_index: int
    heading_path: str
    content_text: str
    distance: float
