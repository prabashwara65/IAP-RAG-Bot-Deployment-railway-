# ADR-002: HR-First Document Automation and Knowledge Agent

## Status

Accepted

## Date

2026-08-15

## Context

OIAP has completed its Phase 0 FastAPI and quality foundation. The approved long-term architecture remains a modular monolith with deterministic authorization, evidence-grounded generation, human authority, versioned sources, auditability, and provider abstractions. Phase 1 needs a focused business slice that can prove the document lifecycle and retrieval controls without using real company information.

HR policies, procedures, role directories, routing matrices, approval matrices, and FAQs provide a coherent first slice. They exercise document ownership, access scope, approval authority, versioning, conflicts, sensitive-data declarations, and employee-facing retrieval. Current development is still synthetic-only under `docs/synthetic-data-policy.md`; approved real company PDFs are expected only after separate governance and security gates.

The target workflow also needs explicit state, pause/resume behavior, reusable business capabilities, and a non-negotiable publication gate. Those needs establish boundaries for LangGraph, MCP, and HITL without transferring deterministic policy decisions to an LLM or orchestration framework.

## Decision

Phase 1 will implement an **HR-first Document Automation and Knowledge Agent** using synthetic HR documents initially. The architecture will deliberately match the future real-document lifecycle.

- FastAPI remains a modular monolith.
- PostgreSQL is the transactional system of record and pgvector is its vector extension.
- Structured Markdown is the direct source for RAG ingestion.
- Synthetic HR sources must pass metadata validation, content validation, standardization, and human approval before chunking or publication.
- Later real PDFs must pass extraction, form pre-fill, user review/correction, required-metadata validation, duplicate/version checks, sensitive-data/redaction checks, standardized-Markdown conversion, and human approval.
- Raw PDFs must never be sent directly to embeddings.
- LangGraph will orchestrate explicit workflow states and HITL interruptions.
- OIAP will expose selected business capabilities through its own MCP server. MCP tools will wrap application services rather than duplicate business logic.
- Deterministic application and governance services will decide authorization, access policy, approval authority, publication eligibility, and sensitive-data policy.
- HITL approval will prevent unapproved documents from entering active RAG retrieval.

These are Phase 1 target decisions. They do not claim that PostgreSQL, pgvector, RAG, LangGraph, MCP, HITL, or document processing is already implemented.

## Alternatives considered

### Continue with a generic company-knowledge demo

This preserves broad coverage but weakens business ownership and makes it harder to design meaningful metadata, approval, access, and evaluation cases. It was rejected as the immediate slice, while the broader company architecture remains future scope.

### Begin with real company PDFs

This would expose the project to unapproved personal, confidential, contractual, retention, and provider-handling risks before the lifecycle is proven. It was rejected until named owners, isolated infrastructure, access mappings, review, and Go/No-Go approval exist.

### Embed raw PDFs directly

This would bypass correction, standardization, metadata completeness, duplicate/version control, redaction review, stable citations, and publication approval. It was rejected.

### Put workflow and policy logic inside LangGraph or MCP tools

This would duplicate business logic and could make authorization or approval dependent on orchestration behavior. It was rejected. LangGraph coordinates; MCP exposes; application services decide and execute governed capabilities.

### Split Phase 1 into microservices

This would add deployment, security, tracing, consistency, and ownership complexity before operational evidence justifies it. It was rejected in favor of the approved modular monolith.

### Build the PDF/form interface first

This would optimize the presentation boundary before the metadata, validation, standardization, approval, and publication services are proven. It was deferred until the core workflow works end to end.

## Consequences

### Positive

- Phase 1 has a concrete business owner and document domain.
- Synthetic development can exercise realistic governance without real-data exposure.
- The same normalized document contract can support synthetic Markdown and later reviewed PDF extraction.
- Human approval is a structural publication gate rather than a UI convention.
- LangGraph, MCP, repositories, and providers retain explicit responsibilities.
- The HR slice can produce focused retrieval, access, conflict, citation, and workflow evaluation evidence.

### Tradeoffs and costs

- Synthetic documents will not reproduce all scan, layout, table, multilingual, ambiguity, or data-quality problems in real PDFs.
- The metadata and state model is broader than a basic RAG prototype.
- HITL requires reviewer roles, interruption persistence, idempotent resume behavior, and auditable decisions.
- MCP adds an interface boundary that must be versioned and contract-tested.
- Real-document replacement still requires a separate environment, new evaluation evidence, and explicit company approval.

## Security and governance implications

Authorization must be deny-by-default and must filter content before it reaches an LLM. LangGraph and the LLM cannot grant access, approve a source, resolve approval authority, or decide sensitive-data policy. MCP tools must call the same application services used by API boundaries so policy and audit behavior cannot diverge.

Every publication decision must record actor, role, document/version, decision, reason, time, correlation ID, and applicable policy/workflow versions. Inactive, rejected, failed, superseded, or archived versions must be excluded from normal retrieval. Restricted metadata, counts, titles, excerpts, and citations must not leak to unauthorized users.

Synthetic content must remain fictional, visibly labelled, isolated from real data, and compliant with `docs/synthetic-data-policy.md`. Discovery of real or prohibited data stops processing and triggers the policy's isolation and incident path.

## Synthetic-to-real transition

Synthetic sources are not relabelled as real. Approved company PDFs create new source records in a separate controlled environment. Named business/data, content, security, privacy/legal as required, access, architecture, and operations owners must approve purpose, source authority, classification, provider handling, retention, deletion, audit, backup, and recovery.

The real-document path must prove extraction, form pre-fill, user correction, metadata completeness, duplicate/version handling, sensitive-data and redaction review, standardized-Markdown fidelity, human approval, chunking, citation anchors, access controls, embeddings, index activation, rollback, and deletion. Retrieval, RAG, security, load, backup, and recovery evaluation must be rerun before a real-user pilot.

## Relationship to ADR-001

ADR-001 remains controlling for vector storage: PostgreSQL with pgvector is the initial vector store behind a `VectorStore` interface. ADR-002 narrows the first business slice and defines which approved standardized HR document versions may supply chunks and embeddings to that store. It does not change ADR-001's storage decision, provider abstraction, migration path, or requirement that pgvector remain part of PostgreSQL.

## Related documents

- `docs/architecture/system-architecture.md`
- `docs/architecture/mvp-architecture.md`
- `docs/architecture/hr-document-automation-phase1.md`
- `docs/implementation/mvp-implementation-plan.md`
- `docs/framework/framework-application-plan.md`
- `docs/synthetic-data-policy.md`
- `docs/decisions/ADR-001-vector-database.md`
