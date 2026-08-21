"""Deterministic, dependency-free embedding provider for tests and local development.

WARNING: this provider is NOT a semantic embedding model. Vectors are derived
from a cryptographic hash of the input text, so semantically similar texts do
not produce nearby vectors. It exists only to exercise the embedding pipeline
without network access, credentials, or model downloads. Never use it to build
an embedding set that a production retrieval path will consume.

Determinism is guaranteed across processes and machines because the derivation
uses ``hashlib`` rather than the process-randomized built-in ``hash``.
"""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256
from math import sqrt

DETERMINISTIC_EMBEDDING_MODEL_NAME = "deterministic-sha256-embedding"
DETERMINISTIC_EMBEDDING_MODEL_VERSION = "1.0.0"
DEFAULT_DETERMINISTIC_EMBEDDING_DIMENSION = 64

_BYTES_PER_COMPONENT = 4
_COUNTER_BYTES = 4
_UINT32_MAX = 2**32 - 1


class DeterministicEmbeddingProvider:
    """Derive stable pseudo-random unit vectors from text using SHA-256.

    The same text and dimension always produce exactly the same vector, and
    different texts normally produce different vectors. Every component is a
    finite float in ``[-1.0, 1.0]``.
    """

    def __init__(
        self,
        *,
        dimension: int = DEFAULT_DETERMINISTIC_EMBEDDING_DIMENSION,
    ) -> None:
        if dimension <= 0:
            raise ValueError("Embedding dimension must be greater than zero.")
        self._dimension = dimension

    @property
    def model_name(self) -> str:
        return DETERMINISTIC_EMBEDDING_MODEL_NAME

    @property
    def model_version(self) -> str:
        return DETERMINISTIC_EMBEDDING_MODEL_VERSION

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        """Return one deterministic vector per text, preserving input order."""
        return tuple(self._embed_text(text) for text in texts)

    def _embed_text(self, text: str) -> tuple[float, ...]:
        material = self._derive_bytes(text, self._dimension * _BYTES_PER_COMPONENT)
        components = [
            (
                int.from_bytes(
                    material[offset : offset + _BYTES_PER_COMPONENT],
                    byteorder="big",
                )
                / _UINT32_MAX
            )
            * 2.0
            - 1.0
            for offset in range(0, len(material), _BYTES_PER_COMPONENT)
        ]
        norm = sqrt(sum(component * component for component in components))
        if norm == 0.0:
            return tuple(components)
        return tuple(component / norm for component in components)

    def _derive_bytes(self, text: str, size: int) -> bytes:
        seed = (
            f"{DETERMINISTIC_EMBEDDING_MODEL_NAME}"
            f":{DETERMINISTIC_EMBEDDING_MODEL_VERSION}"
            f":{self._dimension}:{text}"
        ).encode()
        material = bytearray()
        counter = 0
        while len(material) < size:
            material.extend(
                sha256(seed + counter.to_bytes(_COUNTER_BYTES, byteorder="big")).digest()
            )
            counter += 1
        return bytes(material[:size])
