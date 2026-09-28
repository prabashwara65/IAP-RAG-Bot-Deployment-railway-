"""Diagnose HR retrieval and grounded answering against the local database.

Runs three checks:
1. Provider config (model_name, model_version, dimension)
2. Semantic retrieval for two queries (one generic, one specific)
3. End-to-end grounded answer via Gemini for the specific query

Usage:
    python3 -m scripts.diagnose
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from app.providers.gemini_embeddings import gemini_embedding_provider_from_settings
from app.providers.gemini_llm import gemini_llm_provider_from_settings
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.services.hr_rag import answer_hr_question
from app.services.hr_retrieval import retrieve_hr_chunks


TENANT_ID = "default"

GENERIC_QUERY = "What is in section one?"
SPECIFIC_QUERY = "How many annual leave days do I get?"


def _print_results(label: str, results) -> None:
    print(f"=== {label} ===")
    print(f"Retrieved {len(results)} chunks:")
    if not results:
        print("  (no chunks)")
        print()
        return
    for r in results:
        print(f"  [{r.distance:.4f}] {r.document_key} > {r.heading_path}")
        preview = r.content_text[:80].replace("\n", " ")
        print(f"      {preview}")
    print()


def _print_answer(label: str, answer) -> None:
    print(f"=== {label} ===")
    print(f"insufficient_evidence : {answer.insufficient_evidence}")
    print(f"answer                : {answer.answer}")
    print(f"citations             : {len(answer.citations)}")
    for c in answer.citations:
        print(f"  - {c.citation_id} {c.document_key} > {c.heading_path}")
        print(f"      distance = {c.distance:.4f}")
    print()


def main() -> None:
    settings = get_settings()

    # --- 1. Config ---
    print("=== CONFIG ===")
    embedding_provider = gemini_embedding_provider_from_settings(settings)
    print(f"  embedding.model_name    = {embedding_provider.model_name!r}")
    print(f"  embedding.model_version = {embedding_provider.model_version!r}")
    print(f"  embedding.dimension     = {embedding_provider.dimension}")
    print()

    engine = create_database_engine(settings)
    factory = create_session_factory(engine)

    # --- 2. Retrieval ---
    with session_scope(factory) as session:
        repo = PostgresEmbeddingRepository(session)

        results_generic = retrieve_hr_chunks(
            query=GENERIC_QUERY,
            tenant_id=TENANT_ID,
            provider=embedding_provider,
            repository=repo,
            top_k=5,
        )
        _print_results(f"RETRIEVAL (generic): {GENERIC_QUERY!r}", results_generic)

        results_specific = retrieve_hr_chunks(
            query=SPECIFIC_QUERY,
            tenant_id=TENANT_ID,
            provider=embedding_provider,
            repository=repo,
            top_k=5,
        )
        _print_results(f"RETRIEVAL (specific): {SPECIFIC_QUERY!r}", results_specific)

    # --- 3. Grounded answer (optional; needs GEMINI_API_KEY) ---
    if settings.gemini_api_key is None:
        print("=== GROUNDED ANSWER ===")
        print("Skipped: GEMINI_API_KEY is not configured.")
        return

    try:
        llm_provider = gemini_llm_provider_from_settings(settings)
    except Exception as exc:
        print("=== GROUNDED ANSWER ===")
        print(f"Skipped: could not build LLM provider ({type(exc).__name__}: {exc}).")
        return

    with session_scope(factory) as session:
        repo = PostgresEmbeddingRepository(session)

        answer = answer_hr_question(
            question=SPECIFIC_QUERY,
            tenant_id=TENANT_ID,
            embedding_provider=embedding_provider,
            llm_provider=llm_provider,
            repository=repo,
            top_k=5,
        )
        _print_answer(f"GROUNDED ANSWER: {SPECIFIC_QUERY!r}", answer)


if __name__ == "__main__":
    main()