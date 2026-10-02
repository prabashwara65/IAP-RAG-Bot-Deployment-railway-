"""Embedding persistence and semantic search contracts without vendor detail."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.domain.retrieval import SemanticSearchRecord


class EmbeddingRepository(Protocol):
    def add_embedding(
        self,
        *,
        chunk_id: UUID,
        embedding_set_id: UUID,
        values: Sequence[float],
    ) -> UUID: ...

    def search_similar_chunks(
        self,
        *,
        tenant_id: str,
        query_vector: Sequence[float],
        top_k: int,
        model_name: str,
        model_version: str,
        document_type: str | None = None,
    ) -> Sequence[SemanticSearchRecord]:
        """Return the closest chunks for one tenant, closest first.

        Implementations must restrict the search to the supplied tenant, to
        active document versions, and to active embedding sets whose model
        name, model version, and dimension match the query. Ordering must be stable
        for equal distances. ``document_type`` optionally restricts matching
        documents. No database expression may cross this boundary.
        """
        ...

    def search_similar_chunks_hybrid(
        self,
        *,
        tenant_id: str,
        query_vector: Sequence[float],
        query_text: str,
        top_k: int,
        model_name: str,
        model_version: str,
        document_type: str | None = None,
        rrf_k: int = 60,
        candidate_pool: int = 50,
    ) -> tuple[SemanticSearchRecord, ...]:
        """Return active chunks ranked by vector and full-text RRF."""
        ...
