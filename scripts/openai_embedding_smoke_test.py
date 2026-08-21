"""Manual OpenAI embedding connectivity check.

This script performs one real, tiny API call and is never run by pytest. It
prints only safe metadata: never the API key, and never a full vector.

Usage:
    OPENAI_API_KEY=... python -m scripts.openai_embedding_smoke_test

Add --similarity to also run a local cosine sanity check on three short texts.
That variant sends one request with three inputs instead of two.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from math import sqrt

from app.core.config import get_settings
from app.providers.openai_embeddings import (
    OpenAIEmbeddingError,
    openai_embedding_provider_from_settings,
)

SMOKE_TEXTS = (
    "Employees receive annual leave according to HR policy.",
    "Annual leave entitlement for employees.",
)
SIMILARITY_TEXTS = (
    "Employees receive annual leave according to HR policy.",
    "How much annual leave does an employee receive?",
    "The office printer needs more paper.",
)


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Compute cosine similarity locally, after the vectors have been returned."""
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _run_smoke() -> int:
    provider = openai_embedding_provider_from_settings(get_settings())
    print(f"provider={provider.model_name} model={provider.model_version}")
    print(f"configured_dimension={provider.dimension}")

    vectors = provider.embed_texts(SMOKE_TEXTS)

    print(f"vector_count={len(vectors)}")
    print(f"vector_dimensions={[len(vector) for vector in vectors]}")
    if len(vectors) != len(SMOKE_TEXTS):
        print(f"SMOKE TEST FAILED: expected {len(SMOKE_TEXTS)} vectors")
        return 1
    if any(len(vector) != provider.dimension for vector in vectors):
        print("SMOKE TEST FAILED: a vector did not match the configured dimension")
        return 1
    if vectors[0] == vectors[1]:
        print("SMOKE TEST FAILED: two different texts produced identical vectors")
        return 1

    print("SMOKE TEST OK")
    return 0


def _run_similarity() -> int:
    provider = openai_embedding_provider_from_settings(get_settings())
    print(f"provider={provider.model_name} model={provider.model_version}")

    vectors = provider.embed_texts(SIMILARITY_TEXTS)
    if len(vectors) != len(SIMILARITY_TEXTS):
        print("SANITY CHECK FAILED: unexpected vector count")
        return 1

    related = _cosine_similarity(vectors[0], vectors[1])
    unrelated = _cosine_similarity(vectors[0], vectors[2])
    print(f"similarity(A_policy, B_question)={related:.4f}")
    print(f"similarity(A_policy, C_printer)={unrelated:.4f}")

    if related > unrelated:
        print("SANITY CHECK OK: the related pair is closer than the unrelated pair")
        return 0
    print("SANITY CHECK UNEXPECTED: the related pair was not closer")
    return 1


def main(argv: Sequence[str]) -> int:
    """Run the connectivity smoke test, or the optional similarity check."""
    try:
        if "--similarity" in argv:
            return _run_similarity()
        return _run_smoke()
    except OpenAIEmbeddingError as error:
        print(f"FAILED [{error.code.value}]: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
