"""One-shot diagnostic: traces the full HR RAG pipeline for one question."""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import create_database_engine
from app.providers.gemini_embeddings import gemini_embedding_provider_from_settings
from app.providers.gemini_llm import gemini_llm_provider_from_settings
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.services.hr_rag import (
    GROUNDING_SYSTEM_PROMPT,
    _expand_short_question,
    build_hr_rag_context,
    build_hr_rag_user_prompt,
)
from app.services.hr_retrieval import embed_hr_query, retrieve_hr_chunks

QUESTION = "What is paper size ?"
TENANT = "tenant-synthetic"

print("=" * 60)
print("PIPELINE DIAGNOSTIC")
print("=" * 60)

settings = get_settings()
engine = create_database_engine(settings)
embedder = gemini_embedding_provider_from_settings(settings)
llm = gemini_llm_provider_from_settings(settings)

print("\n[1] Query expansion")
expanded = _expand_short_question(QUESTION, llm)
print("    original:", repr(QUESTION))
print("    expanded:", repr(expanded))

print("\n[2] Embedding expanded query")
qvec = embed_hr_query(expanded, embedder)
print("    vector dim:", len(qvec))

print("\n[3] Hybrid retrieval (search_mode='hybrid')")
with Session(engine) as session:
    repo = PostgresEmbeddingRepository(session)

    results = retrieve_hr_chunks(
        query=expanded,
        tenant_id=TENANT,
        provider=embedder,
        repository=repo,
        top_k=5,
        search_mode="hybrid",
    )
    print("    retrieved", len(results), "chunk(s)")
    for i, r in enumerate(results, 1):
        dist = "inf" if r.distance == float("inf") else f"{r.distance:.4f}"
        print("      ", i, ". dist=", dist, " chunk#", r.chunk_index, sep="")
        print("         doc=", repr(r.document_title))
        print("         heading=", repr(r.heading_path))
        print("         preview=", repr(r.content_text[:80]))

    print("\n[4] Building LLM context")
    if not results:
        print("    no chunks — stopping")
        raise SystemExit(0)

    ctx = build_hr_rag_context(results, max_context_chars=6000)
    print("    context length:", len(ctx.text), "chars")
    print("    sources:", len(ctx.sources))
    print("    first 400 chars of context:")
    print("    " + ctx.text[:400].replace("\n", "\n    "))

    print("\n[5] Calling LLM")
    user_prompt = build_hr_rag_user_prompt(QUESTION, ctx)
    raw = llm.generate(
        system_prompt=GROUNDING_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )
    print("    raw response (", len(raw), " chars):", sep="")
    print("    " + raw[:600].replace("\n", "\n    "))

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)