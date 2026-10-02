"""Test 'What line spacing is required?' end-to-end."""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import create_database_engine
from app.providers.gemini_embeddings import gemini_embedding_provider_from_settings
from app.providers.gemini_llm import gemini_llm_provider_from_settings
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.services.hr_rag import (
    GROUNDING_SYSTEM_PROMPT,
    _expand_short_question,
    answer_hr_question,
    build_hr_rag_context,
    build_hr_rag_user_prompt,
)
from app.services.hr_retrieval import embed_hr_query, retrieve_hr_chunks

settings = get_settings()
engine = create_database_engine(settings)
embedder = gemini_embedding_provider_from_settings(settings)
llm = gemini_llm_provider_from_settings(settings)

QUESTION = "What line spacing is required?"
TENANT = "tenant-synthetic"

print("=" * 60)
print("SPACING QUERY DIAGNOSTIC")
print("=" * 60)

print("\n[1] Expansion")
expanded = _expand_short_question(QUESTION, llm)
print(f"    original: {QUESTION!r}")
print(f"    expanded: {expanded!r}")

print("\n[2] Retrieval (hybrid)")
with Session(engine) as session:
    repo = PostgresEmbeddingRepository(session)
    results = retrieve_hr_chunks(
        query=expanded,
        bm25_query=QUESTION,
        tenant_id=TENANT,
        provider=embedder,
        repository=repo,
        top_k=5,
        search_mode="hybrid",
    )
    print(f"    retrieved {len(results)} chunks:")
    for i, r in enumerate(results, 1):
        dist = "inf" if r.distance == float("inf") else f"{r.distance:.4f}"
        has_spacing = "spacing" in r.content_text.lower()
        print(f"      {i}. chunk#{r.chunk_index}  dist={dist}  "
              f"contains_spacing={has_spacing}")
        print(f"         {r.content_text[:100]!r}")

    print("\n[3] Context")
    if results:
        ctx = build_hr_rag_context(results, max_context_chars=6000)
        print(f"    {len(ctx.text)} chars, {len(ctx.sources)} sources")

    print("\n[4] LLM direct call")
    if results:
        user_prompt = build_hr_rag_user_prompt(QUESTION, ctx)
        raw = llm.generate(
            system_prompt=GROUNDING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        print(f"    {raw[:400]!r}")

print("\n[5] Full answer_hr_question")
with Session(engine) as session:
    repo = PostgresEmbeddingRepository(session)
    ans = answer_hr_question(
        question=QUESTION,
        tenant_id=TENANT,
        embedding_provider=embedder,
        llm_provider=llm,
        repository=repo,
        top_k=5,
    )
    print(f"    insufficient_evidence: {ans.insufficient_evidence}")
    print(f"    answer: {ans.answer}")
    print(f"    citations: {len(ans.citations)}")
    for c in ans.citations:
        print(f"      - [{c.citation_id}] chunk#{c.chunk_index}")