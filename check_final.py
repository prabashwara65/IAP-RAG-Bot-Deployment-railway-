"""Final end-to-end test of the HR RAG pipeline."""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import create_database_engine
from app.providers.gemini_embeddings import gemini_embedding_provider_from_settings
from app.providers.gemini_llm import gemini_llm_provider_from_settings
from app.repositories.postgres.embeddings import PostgresEmbeddingRepository
from app.services.hr_rag import answer_hr_question

settings = get_settings()
engine = create_database_engine(settings)
embedder = gemini_embedding_provider_from_settings(settings)
llm = gemini_llm_provider_from_settings(settings)

QUESTION = "What is paper size ?"
TENANT = "tenant-synthetic"

print("=" * 60)
print("FINAL END-TO-END TEST")
print("=" * 60)
print(f"Question: {QUESTION!r}")
print(f"Tenant:   {TENANT!r}")
print()

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

print()
print("=" * 60)
print("RESULT")
print("=" * 60)
print(f"insufficient_evidence: {ans.insufficient_evidence}")
print()
print("Answer:")
print(ans.answer)
print()
print(f"Citations: {len(ans.citations)}")
for c in ans.citations:
    print(f"  - [{c.citation_id}] {c.document_title}  chunk#{c.chunk_index}")
    print(f"      {c.heading_path}")