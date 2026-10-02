"""Compare retrieval filters against what's actually in the DB."""

from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import create_database_engine
from app.providers.gemini_embeddings import gemini_embedding_provider_from_settings

settings = get_settings()
engine = create_database_engine(settings)
provider = gemini_embedding_provider_from_settings(settings)

print("=== Provider identity (what the SQL filter demands) ===")
print("  model_name:   ", repr(provider.model_name))
print("  model_version:", repr(provider.model_version))
print("  dimension:    ", provider.dimension)

print()
print("=== Documents in DB ===")
with engine.connect() as c:
    for r in c.execute(text("""
        SELECT id, document_key, title, tenant_id, document_type
          FROM documents
    """)).all():
        print("  ", dict(r._mapping))

print()
print("=== Document versions in DB ===")
with engine.connect() as c:
    for r in c.execute(text("""
        SELECT id, document_id, status
          FROM document_versions
    """)).all():
        print("  ", dict(r._mapping))

print()
print("=== Embedding sets in DB ===")
with engine.connect() as c:
    for r in c.execute(text("""
        SELECT id, document_version_id, status,
               model_name, model_version, dimension
          FROM embedding_sets
    """)).all():
        print("  ", dict(r._mapping))

print()
print("=== Embeddings in DB (join chain) ===")
with engine.connect() as c:
    rows = c.execute(text("""
        SELECT e.chunk_id, e.embedding_set_id,
               es.model_name, es.model_version, es.dimension,
               dv.status AS version_status,
               d.tenant_id, d.document_key
          FROM embeddings e
          JOIN embedding_sets es ON es.id = e.embedding_set_id
          JOIN chunks ch ON ch.id = e.chunk_id
          JOIN document_versions dv ON dv.id = ch.document_version_id
          JOIN documents d ON d.id = dv.document_id
    """)).all()
    for r in rows:
        print("  ", dict(r._mapping))
    print(f"  total: {len(rows)}")