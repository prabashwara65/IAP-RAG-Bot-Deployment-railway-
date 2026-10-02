"""Call search_similar_chunks_hybrid directly to see what it returns."""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import create_database_engine
from app.providers.gemini_embeddings import gemini_embedding_provider_from_settings
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.services.hr_retrieval import embed_hr_query

settings = get_settings()
engine = create_database_engine(settings)
embedder = gemini_embedding_provider_from_settings(settings)

original = "What is paper size ?"
expanded = (
    "What are the standard dimensions and common uses of various "
    "paper sizes, such as A4, Letter, and Legal?"
)
qvec = embed_hr_query(expanded, embedder)

print("=== Test 1: query_text = ORIGINAL (BM25 gets original) ===")
with Session(engine) as session:
    repo = PostgresEmbeddingRepository(session)
    results = repo.search_similar_chunks_hybrid(
        tenant_id="tenant-synthetic",
        query_vector=qvec,
        query_text=original,
        top_k=5,
        model_name=embedder.model_name,
        model_version=embedder.model_version,
    )
    print(f"returned {len(results)} chunks:")
    for i, r in enumerate(results, 1):
        dist = "inf" if r.distance == float("inf") else f"{r.distance:.4f}"
        print(f"  {i}. chunk#{r.chunk_index}  dist={dist}")
        print(f"     {r.content_text[:60]!r}")

print()
print("=== Test 2: query_text = EXPANDED (BM25 gets expanded) ===")
with Session(engine) as session:
    repo = PostgresEmbeddingRepository(session)
    results = repo.search_similar_chunks_hybrid(
        tenant_id="tenant-synthetic",
        query_vector=qvec,
        query_text=expanded,
        top_k=5,
        model_name=embedder.model_name,
        model_version=embedder.model_version,
    )
    print(f"returned {len(results)} chunks:")
    for i, r in enumerate(results, 1):
        dist = "inf" if r.distance == float("inf") else f"{r.distance:.4f}"
        print(f"  {i}. chunk#{r.chunk_index}  dist={dist}")