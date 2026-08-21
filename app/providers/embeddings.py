"""Vendor-neutral embedding provider contract.

The contract intentionally describes only what the platform needs to persist and
validate a vector. It carries no transport, credential, batching, or vendor
detail so that a local, hosted, or remote implementation can satisfy it without
leaking implementation concerns into services.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Minimal contract every embedding backend must satisfy."""

    @property
    def model_name(self) -> str:
        """Stable model identifier persisted alongside an embedding set."""
        ...

    @property
    def model_version(self) -> str:
        """Stable version identifier for the model that produced the vectors."""
        ...

    @property
    def dimension(self) -> int:
        """Positive component count every returned vector must have."""
        ...

    def embed_texts(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return exactly one vector per input text, preserving input order."""
        ...
