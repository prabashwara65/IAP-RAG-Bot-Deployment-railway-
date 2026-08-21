# ADR-001: Use PostgreSQL with pgvector as the Initial Vector Store

## Status

Accepted

## Date

2026-08-04

## Decision owners

The OIAP architecture owner is accountable for this decision. The future company data owner, security owner, database/operations owner, and AI engineering lead must review it before real company data or production deployment. Named individuals have not yet been assigned.

## Context

The Office Intelligence Automation Platform (OIAP) will begin with a secure Company Knowledge RAG MVP using synthetic Markdown documents with YAML metadata. The platform needs relational metadata, document versions, access rules, audit linkage, embeddings, and semantic retrieval. Expected MVP scale is limited, deployment begins with Docker Compose, and the architecture is a modular monolith.

## Problem statement

OIAP needs an initial vector store that supports evidence retrieval while keeping access filtering, document lifecycle, audit correlation, backup, and deployment manageable. The choice must not permanently couple business logic to one storage product or prevent later adoption of managed vector infrastructure.

## Decision drivers

- Correct access filtering before LLM generation.
- Transactional consistency between source metadata and vectors.
- Traceable document, chunk, and audit relationships.
- Simple backup, restore, local deployment, and operations for the MVP.
- Suitable retrieval at the expected corpus size and traffic.
- Low synchronization and infrastructure complexity.
- A credible evolution path for larger or multi-tenant workloads.

## Considered options

| Option | Strengths | Limitations for the initial scope |
|---|---|---|
| PostgreSQL with pgvector | Unified relational/vector queries, transactions, mature operations, metadata filtering | Shares database resources; ANN indexes and tuning require care |
| Pinecone | Managed vector infrastructure and independent scaling | Adds a second system, synchronization, vendor/service dependency, and MVP operational cost |
| Separate self-hosted vector database | Independent vector scaling and specialized features | Adds deployment, security, backup, monitoring, and consistency responsibilities |
| Local in-memory or file-based vector store | Fast to prototype and low setup | Weak durability, concurrency, filtering, audit linkage, backup, and realistic deployment path |

## Decision

Use PostgreSQL with the pgvector extension as OIAP's initial vector store. Store embeddings with stable chunk, document-version, and authorization metadata relationships. All business logic must use a `VectorStore` interface; PostgreSQL-specific queries remain in the pgvector adapter. Pinecone may later be introduced through another adapter without changing authorization, orchestration, citation, or document-lifecycle business logic.

## Rationale

pgvector unifies relational and vector data, allowing access-control filters and lifecycle conditions to be applied close to semantic retrieval. Transactional consistency reduces the chance that active metadata and embeddings diverge. Direct relationships simplify audit linkage, document version activation, deletion, and re-indexing. The same database can be backed up and deployed with the initial application, lowering MVP operational complexity. This is suitable for the expected synthetic corpus and demonstration traffic and avoids synchronizing a separate vector service before evidence shows a need.

## Advantages

- Unified relational and vector data.
- Transactional consistency during ingestion and version activation.
- Simpler role, department, `access_level`, and `confidentiality` filtering.
- Easier linkage among source versions, chunks, citations, and audit events.
- Easier document lifecycle management and cleanup.
- One initial backup, restore, deployment, and monitoring surface.
- Lower infrastructure and synchronization complexity for the MVP.
- SQL-based inspection supports debugging and audit review.

## Disadvantages

- Vector and transactional workloads share PostgreSQL CPU, memory, storage, connections, and I/O.
- Approximate nearest-neighbor indexes require explicit configuration, measurement, and maintenance.
- Query planning and metadata selectivity may need careful tuning.
- Independent vector scaling is less direct than with a managed vector service.
- Large multi-tenant SaaS scale may exceed the most economical or operationally safe shape of this design.

## Risks

Poor index parameters could reduce recall or increase latency. Vector traffic could affect core relational operations. Incorrect SQL filters could disclose restricted evidence. Embedding-model changes could mix incompatible vectors. Database restore could leave derived indexes out of sync with source manifests. These risks require access-control tests, versioned embeddings, capacity monitoring, reconciliation checks, and tested recovery.

## Consequences

The initial schema must represent documents, versions, chunks, embedding model/version, active state, departments, access levels, confidentiality, and citation anchors. Retrieval queries must combine authorization and lifecycle predicates with vector ranking. Migrations, backups, monitoring, and performance tests include pgvector. The source documents remain authoritative; vectors are reproducible derived artifacts.

## Security implications

Database roles follow least privilege. Retrieval must apply authenticated role, department, document, `access_level`, and `confidentiality` restrictions before evidence reaches the LLM. Denied rows and sensitive metadata must not leak through counts, citations, errors, or logs. Connections require transport encryption outside isolated local development, and storage encryption follows company policy. Access-control correctness is a release gate, not merely a relevance metric.

## Operational implications

Operators must monitor vector query latency, recall samples, database load, index size and health, connection saturation, vacuum/analyze behavior, ingestion queues, and relational workload impact. Backup and restore tests must include the extension, schema, vectors, and reconciliation against approved source manifests. Re-embedding runs need bounded batches, resumability, and an atomic activation strategy.

## Cost implications

The choice avoids an additional managed service during the MVP and consolidates operational effort. Costs still include PostgreSQL compute, storage, backups, engineering time, and embedding generation. A managed vector service may become cheaper in total operating cost if scale, staffing, isolation, or availability requirements change. No specific cost claim is accepted until deployment options are priced and measured.

## Migration strategy

1. Keep authorization, document lifecycle, retrieval requests, and retrieval results defined in domain types.
2. Access vectors only through the `VectorStore` interface.
3. Record stable document-version and chunk identifiers plus embedding model/version.
4. Add a Pinecone adapter only after a new ADR and security/operational review.
5. Backfill authorized active vectors to the target store and reconcile counts and hashes.
6. Run both adapters against the same versioned evaluation dataset and access-control suite.
7. Shadow or canary reads without exposing unapproved results.
8. Switch configuration only after acceptance gates pass; retain a timed rollback path.
9. Remove old vectors only after retention and rollback requirements expire.

## Revisit conditions

Reconsider this decision when one or more of the following is supported by measured demand or approved strategy:

- very large vector volume;
- many independent tenant organizations;
- high concurrent retrieval traffic;
- a need for independently managed vector scaling;
- company preference for managed vector infrastructure; or
- operational evidence that PostgreSQL vector workloads affect core business data.

A revisit does not automatically require migration; it triggers capacity, cost, security, and evaluation analysis.

## Validation plan

- Compare semantic retrieval with keyword or metadata baselines using golden questions.
- Measure retrieval recall, latency percentiles, and result stability at projected corpus sizes.
- Test role, department, document, `access_level`, and `confidentiality` filtering, including adversarial cases.
- Verify active versions are retrieved while superseded and archived versions are excluded by default.
- Test concurrent ingestion and query behavior, atomic activation, and failed-ingestion cleanup.
- Exercise backup, restore, reconciliation, re-indexing, and embedding-version rollback.
- Load-test vector and relational workloads together and define revisit thresholds.
- Confirm the same domain tests can run against a substitute `VectorStore` adapter.

## Related documents

- `docs/architecture/system-architecture.md`
- `docs/architecture/mvp-architecture.md`
- `docs/framework/framework-application-plan.md`
- `docs/synthetic-data-policy.md`
- Enterprise AI/ML Engineering Framework, v2.1.0: <https://github.com/chathuranga-sudusinghe/enterprise-ai-ml-engineering-framework>
