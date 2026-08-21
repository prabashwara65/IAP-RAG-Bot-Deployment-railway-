# Office Intelligence Automation Platform: MVP Implementation Plan

## 1. Purpose

This document converts the approved Office Intelligence Automation Platform (OIAP) architecture into an implementation roadmap. Phase 1 is realigned to an HR-first Document Automation and Knowledge Agent that initially uses synthetic HR documents. It defines sequence, boundaries, expected modules, tests, evidence, acceptance gates, risks, and reviewable commit units. It is a plan only: it does not authorize application implementation, dependency changes, synthetic-document creation, deployment, or production use.

The controlling documents are:

- `docs/architecture/system-architecture.md`
- `docs/architecture/mvp-architecture.md`
- `docs/decisions/ADR-001-vector-database.md`
- `docs/decisions/ADR-002-hr-first-document-automation.md`
- `docs/architecture/hr-document-automation-phase1.md`
- `docs/framework/framework-application-plan.md`
- `docs/synthetic-data-policy.md`

If implementation exposes a conflict or missing decision, work stops at the affected boundary and the architecture owner records a decision; this plan must not silently override those documents.

## 2. Current project state

Phase 0 foundation work is completed in the repository: the FastAPI application skeleton, typed configuration, structured logging, correlation IDs, health/configuration-only readiness endpoints, common API errors, and Pytest/Ruff/MyPy configuration exist with tests. No PostgreSQL schema, pgvector integration, migrations, document pipeline, synthetic corpus, retrieval, RAG, LangGraph, MCP server, HITL publication workflow, frontend, or Docker Compose topology is implemented yet.

Current runtime dependencies are pinned to FastAPI, Uvicorn, Pydantic Settings, and python-dotenv. Current development dependencies are pinned to Pytest, pytest-asyncio, HTTPX, Ruff, and MyPy. These declarations establish only an initial tool foundation; they do not prove that the planned database, parsing, vector, workflow, LLM, or frontend capabilities are installed or validated.

The existing data boundary must remain synthetic-only. A later, explicitly approved synthetic-corpus phase must decide which reviewed source and evaluation files are committed and which processed artifacts remain ignored. No such change is made by this plan.

### Phase 1 realignment note

The existing baseline-first gates remain controlling, but the business slice and delivery sequence are now explicit:

1. Phase 0 foundation - completed.
2. PostgreSQL and pgvector document foundation.
3. Synthetic HR metadata schema and document corpus.
4. Document validation and standardized-Markdown pipeline.
5. Keyword and metadata retrieval baseline.
6. Semantic pgvector retrieval.
7. Grounded LLM RAG with citations.
8. LangGraph document workflow and HITL approval.
9. OIAP MCP server and tool integration.
10. Controlled HR demonstration.
11. Later replacement with approved real company documents.
12. Final PDF/form automation interface after the core workflow is proven.

This realignment does not authorize the later stages early. Synthetic HR documents must model the structure, metadata, access, approval, versioning, and ingestion expectations of future real documents. Raw PDFs never go directly to embeddings. Standardized Markdown is the direct RAG source, and explicit human approval is required before chunking, embedding publication, or active retrieval.

## 3. MVP implementation objective

Deliver a controlled HR demonstration in which governed synthetic HR documents pass validation, standardization, and HITL publication approval, and an authenticated synthetic user can ask a question. OIAP filters active sources by role, department, document rules, `access_level`, and `confidentiality`, retrieves evidence, evaluates evidence sufficiency, and returns one of the approved answer statuses. Supported answers include verified citations; partial answers state unsupported parts; conflicting documents are reported and escalated rather than resolved automatically; insufficient or restricted questions do not produce invented answers.

The MVP must produce reproducible evidence for a company Go/No-Go decision. It must not be described as production-ready or as proof that the design is safe or effective with real company documents.

## 4. Technical scope

The planned MVP scope is:

- a React demonstration frontend;
- a FastAPI modular monolith with explicit domain, service, repository, provider, and workflow boundaries;
- PostgreSQL with the pgvector extension as one database system;
- local filesystem storage for authoritative synthetic Markdown sources;
- mandatory YAML front-matter validation and visible synthetic-content labeling;
- Markdown parsing and heading-aware chunking;
- a keyword/metadata retrieval baseline before semantic retrieval;
- semantic retrieval through a provider-neutral embedding interface and `VectorStore` interface;
- evidence-grounded LLM generation only after retrieval baselines work and are measured;
- LangGraph for the target document workflow, introduced only after the underlying deterministic services and explicit states are proven;
- an OIAP MCP server that wraps selected application services for LangGraph without duplicating business logic;
- deterministic access filtering before evidence reaches an LLM;
- citation validation, conflict handling, refusal, escalation, feedback, audit events, evaluation, and basic telemetry; and
- Docker Compose packaging for local or controlled company demonstration.

## 5. Explicit exclusions

The MVP excludes real company documents, real employee enrollment, production identity integration, production deployment, high availability claims, legal or regulatory compliance claims, autonomous agents, model training, unrestricted web retrieval, object storage, Pinecone implementation, microservices, and live email, WhatsApp Business, voice, caller-information, payment, or other external integrations. It performs no autonomous risky or externally visible action. Any later external action requires a separate architecture decision, company approval, deterministic authorization, idempotency, and execution-time human approval.

## 6. Engineering principles

1. **Baseline first.** Validate sources, build and measure keyword/metadata retrieval, then build and fairly compare pgvector semantic retrieval. Add generation only after retrieval works.
2. **Controlled complexity.** Introduce the planned LangGraph and MCP boundaries only after deterministic services and workflow states are proven. Add reranking, query rewriting, hybrid retrieval, or additional infrastructure only for a measured need.
3. **Modular monolith first.** Module boundaries support review and testing without creating separately deployed services.
4. **Authorization before disclosure.** Deterministic access policy filters candidates before retrieval evidence reaches the LLM and is checked again before response construction.
5. **Sources are authoritative.** Markdown source versions are truth inputs; chunks, embeddings, indexes, answers, and evaluation outputs are reproducible generated artifacts.
6. **Fail closed.** Identity, access, lifecycle, evidence, and citation uncertainty produces denial, controlled non-answer, or human review.
7. **No model authority.** An LLM does not decide permissions, approve documents, resolve source authority, accept risk, or authorize external actions.
8. **No confidence fiction.** Vector distance, LLM self-ratings, and model-generated percentages are not represented as confidence.
9. **Traceability by version.** Source, chunker, embedding, retrieval, prompt, model, policy, workflow, and configuration versions are recorded in test and audit evidence.
10. **Small reviewable changes.** Each phase ends with isolated evidence and a recommended commit boundary; incomplete cross-phase work is not bundled.

## 7. Proposed repository structure

This is a target structure, not an instruction to create all paths at once. Each phase creates only the minimum files it owns.

```text
office-intelligence-automation-platform-oiap/
├── app/
│   ├── api/                    # FastAPI routers, dependencies, error mapping
│   ├── core/                   # Typed configuration, logging, correlation, security primitives
│   ├── domain/                 # Framework-independent entities, value objects, status contracts
│   ├── services/               # Application use cases: ingestion, retrieval, answers, feedback
│   ├── repositories/           # Persistence interfaces and PostgreSQL implementations
│   ├── providers/              # Embedding and LLM interfaces plus configured adapters
│   ├── workflows/              # Explicit workflow state and later LangGraph adapter
│   ├── models/                 # Database ORM/table models only
│   ├── schemas/                # API, document metadata, provider, and evaluation schemas
│   └── main.py                 # FastAPI composition root
├── frontend/                   # React application and frontend tests
├── data/
│   ├── synthetic/              # Authoritative, reviewed synthetic Markdown sources
│   │   ├── company-wide/
│   │   ├── hr/
│   │   ├── finance/
│   │   ├── engineering/
│   │   ├── it/
│   │   └── operations/
│   ├── processed/              # Ignored/rebuildable chunks and embedding artifacts
│   └── evaluation/             # Versioned synthetic golden questions and expectations
├── migrations/                 # Versioned PostgreSQL and pgvector schema migrations
├── tests/
│   ├── unit/                   # Pure domain, parser, chunker, policy, and service tests
│   ├── integration/            # PostgreSQL, pgvector, API, ingestion, and provider-contract tests
│   ├── security/               # Access, leakage, path, injection, and secret/log tests
│   └── evaluation/             # Retrieval/RAG metrics and frozen-dataset regression tests
├── scripts/                    # Reproducible validation, ingestion, evaluation, and demo commands
├── docs/                       # Architecture, ADRs, framework evidence, operations, and guides
├── docker-compose.yml          # Local/controlled demo topology, added only in Phase 8
├── .env.example                # Non-secret typed configuration names and safe examples
├── requirements.txt
└── requirements-dev.txt
```

Dependency direction is inward: `api`, workflows, repositories, and providers may depend on domain/application contracts; domain types must not import FastAPI, LangGraph, PostgreSQL, pgvector, or vendor SDKs. The composition root selects concrete adapters. PostgreSQL and pgvector remain a single persistence service, while the `VectorStore` contract prevents storage-specific behavior from entering business logic.

## 8. Implementation milestones

The nine phases are sequential gates. A phase may begin exploratory spikes only when they are isolated and discarded or documented; it cannot claim completion until its required evidence and acceptance criteria pass. The required baseline sequence is fixed:

1. Validate documents and metadata.
2. Build the keyword/metadata retrieval baseline.
3. Measure the baseline.
4. Build semantic retrieval with PostgreSQL and pgvector.
5. Compare both methods fairly.
6. Add LLM generation only after retrieval is working.
7. Add the planned LangGraph workflow and HITL publication gate only after the deterministic document and retrieval services are proven; add MCP integration after its application-service contracts are stable.

### Phase 0 — Project and quality foundation

**Objective.** Establish the minimum executable FastAPI skeleton, typed configuration, quality gates, module dependency rules, and evidence conventions without implementing RAG behavior.

**Tasks.** Confirm supported Python and Node versions; define application composition and health/readiness boundaries; configure Ruff, MyPy, Pytest, and coverage expectations; add deterministic test configuration; establish structured error and correlation-ID conventions; document local commands; decide how evidence artifacts are named and retained; add only dependencies explicitly approved for this phase.

**Files or modules expected.** `app/main.py`, `app/api/`, `app/core/config.py`, `app/core/logging.py`, initial `app/domain/`, `tests/unit/`, `tests/integration/`, tool configuration, `README.md`, `.env.example`, and a phase evidence record under `docs/`. Paths are created only when implemented.

**Dependencies.** Existing FastAPI, Uvicorn, Pydantic Settings, python-dotenv, Pytest, pytest-asyncio, HTTPX, Ruff, and MyPy. Any packaging or coverage tool requires a separate justified dependency change.

**Tests.** Configuration success/failure, absence of secret values in logs, health endpoint, application startup/shutdown, deterministic error shape, correlation-ID propagation, import-boundary checks where practical, and clean-environment test/lint/type commands.

**Framework evidence required.** Exact environment and commands, dependency versions, passing/failing check output, configuration schema, module-boundary rationale, known limitations, reviewer, and a Phase 0 Go/No-Go record mapped mainly to Framework Delivery preparation.

**Acceptance criteria.** The application starts in a clean supported environment, fails clearly on invalid required configuration, exposes no business/RAG behavior, and the agreed Pytest/Ruff/MyPy commands are reproducible. No secret or local state is committed.

**Risks.** Premature abstractions, hidden platform assumptions, configuration sprawl, quality checks that do not run on Windows/WSL consistently, and treating a health endpoint as application readiness.

**Recommended commit boundary.** One foundation commit containing only the runnable skeleton, quality configuration, minimal documentation, and its tests. Dependency changes, if approved, are explicit in the same review and unrelated features are excluded.

### Phase 1 — PostgreSQL and pgvector foundation

**Objective.** Establish PostgreSQL with pgvector as one database foundation and prove migrations, transactions, relational/vector schema compatibility, and recovery-oriented lifecycle behavior.

**Tasks.** Select an approved PostgreSQL driver, migration tool, and persistence mapping approach; define database configuration; add a migration enabling the pgvector extension; create initial document, document-version, chunk, embedding-set, and embedding tables; model active/candidate/failed lifecycle state; add repository transaction boundaries; document local database start and migration commands; test migration forward and rollback behavior. ANN indexing is deferred until corpus size and evaluation justify parameters.

**Files or modules expected.** `app/models/`, `app/repositories/postgres/`, `app/core/database.py`, `migrations/`, database integration fixtures, and database setup documentation. A temporary database service may be introduced for tests; final Docker Compose packaging remains Phase 8.

**Dependencies.** Approved PostgreSQL driver, migration tool, and pgvector integration library. PostgreSQL must have a compatible pgvector extension. Versions are pinned and reviewed for license, maintenance, security, and platform support before use.

**Tests.** Clean migration, upgrade/downgrade, extension availability, transaction rollback, uniqueness and foreign keys, one-active-version constraints where enforceable, vector dimension compatibility, candidate isolation, idempotent persistence, and database-unavailable failure behavior.

**Framework evidence required.** ADR-001 traceability, schema/migration revision, exact commands, migration and rollback output, integration-test results, extension/version evidence, backup/recovery assumptions, query plan samples when relevant, and residual operational risks.

**Acceptance criteria.** A clean PostgreSQL instance can enable pgvector and apply migrations reproducibly; relational and embedding records remain linked transactionally; failed or candidate data cannot appear active; rollback is documented and tested. PostgreSQL and pgvector are never represented as separate database services.

**Risks.** Unsupported extension versions, Windows/WSL setup friction, migration lock or rollback failure, premature ANN tuning, vector workloads affecting relational operations, and schema coupling to a provider.

**Recommended commit boundary.** One database-foundation commit containing dependency declarations, migrations, persistence scaffolding, database tests, and setup evidence. Do not include parsing, retrieval, or synthetic content.

### Phase 2 — Synthetic document corpus and validation

**Objective.** After explicit content-generation approval, create a small governed synthetic corpus and deterministic validation pipeline before any retrieval implementation.

**Tasks.** Approve fictional taxonomy and owners; decide tracked source/evaluation paths and adjust `.gitignore` narrowly; define the metadata schema from `docs/synthetic-data-policy.md`; build filename, YAML, Markdown, visible-label, date, lifecycle, controlled-value, prohibited-data, and cross-version validators; create reviewed documents only after authorization; generate a source manifest with fingerprints; keep processed chunks/embeddings ignored and rebuildable.

**Files or modules expected.** `app/schemas/document.py`, `app/services/document_validation.py`, parser-independent domain validation types, `scripts/validate_documents.py`, `data/synthetic/<department>/`, validation fixtures, `tests/unit/`, `tests/security/`, and a reviewed corpus manifest/evidence record. This plan does not create those documents.

**Dependencies.** An approved safe YAML parser and, only if justified, a Markdown parser. Dependency behavior for unsafe constructors, duplicate keys, aliases, and resource limits must be reviewed. Corpus creation itself must not require an LLM or external provider.

**Tests.** Every mandatory field; valid controlled values; Boolean `synthetic: true`; ISO dates; quoted version semantics; title/filename/document-ID agreement; visible label; meaningful headings; duplicate IDs; multiple active versions; archived/superseded exclusion; prohibited contacts/secrets; path traversal; malformed or oversized YAML/Markdown; and deterministic manifest fingerprints.

**Framework evidence required.** Data-stage schema, synthetic-policy checklist per source, reviewer records, prohibited-data scans, manifest/fingerprints, validator test output, taxonomy decisions, known artificiality limitations, and signed Data-stage Go/No-Go.

**Acceptance criteria.** All active corpus sources pass automated validation and separate human review; invalid fixtures fail with stable error codes; no real or confidential information is present; source versions are traceable; generated artifacts are excluded from source authority and normal Git scope.

**Risks.** Accidental real data, copied confidential language, inconsistent fictional policies, evaluation leakage, weak negative cases, metadata drift, or committing generated vectors/database files.

**Recommended commit boundary.** Prefer two independently reviewed commits: first the schema/validator/tests; second the explicitly approved synthetic source corpus, manifest, and human-review evidence. Do not combine retrieval code with either commit.

### Phase 3 — Keyword and metadata retrieval baseline

**Objective.** Establish the simplest credible, access-aware retrieval reference and measure it before semantic methods.

**Tasks.** Parse validated sources; normalize text without changing meaning; index headings, text, tags, department, type, version, status, `access_level`, and `confidentiality`; implement deterministic keyword scoring and metadata filters; define stable tie-breaking; return evidence items with document/version/heading anchors; exclude inactive and unauthorized sources; run the frozen baseline questions and record metrics/errors/latency.

**Files or modules expected.** `app/domain/retrieval.py`, `app/services/keyword_retrieval.py`, metadata repository contracts/implementations, `app/schemas/retrieval.py`, `scripts/run_baseline_evaluation.py`, and unit, integration, security, and evaluation tests.

**Dependencies.** Prefer Python and PostgreSQL capabilities already available. Any text-search library or database extension requires evidence that it improves reproducibility or relevance enough to justify the dependency.

**Tests.** Exact keyword and metadata cases, punctuation/case normalization, stable ranking, top-k boundaries, status/version exclusion, every access level and confidentiality combination, no restricted metadata leakage, empty/unsupported queries, deterministic citation anchors, and frozen-dataset metric calculations.

**Framework evidence required.** Baseline code/configuration revision, corpus and golden-dataset versions, exact commands, retrieval recall, latency samples, access-correctness results, per-question output, error taxonomy, and human verification of expected sources.

**Acceptance criteria.** The baseline is reproducible, returns only authorized active evidence, reports measured results without overstating them, and creates a credible comparison point. No embedding or LLM path is needed to answer this gate.

**Risks.** Over-engineered “baseline,” unfair later comparison, hidden access bypass, brittle token matching, test-set tuning, and aggregate metrics hiding critical disclosure failures.

**Recommended commit boundary.** One baseline commit containing keyword/metadata retrieval, tests, evaluation runner, and evidence. Freeze its configuration before starting semantic retrieval.

### Phase 4 — Semantic retrieval baseline

**Objective.** Add provider-neutral embeddings and pgvector retrieval, then compare semantic and keyword/metadata baselines under identical authorized conditions.

**Tasks.** Define embedding request/result and `VectorStore` contracts; implement a deterministic fake embedding provider for tests; add the approved real embedding adapter; generate versioned embeddings for validated chunks; store them in PostgreSQL with pgvector; apply authorization/lifecycle predicates before candidate evidence leaves persistence; select exact search first at small scale and evaluate ANN only if needed; run the same frozen questions, users, corpus, top-k, and metrics as Phase 3.

**Files or modules expected.** `app/providers/embeddings/`, `app/repositories/vector_store.py`, `app/repositories/postgres/pgvector_store.py`, embedding/domain schemas, indexing scripts, integration fixtures, and retrieval/evaluation/security tests.

**Dependencies.** Approved embedding provider SDK or HTTP adapter and pgvector client integration. Pinecone is not added; only the storage-neutral contract is designed. Provider credentials remain runtime-only.

**Tests.** Provider contract and fake, dimension/version mismatch, batch/retry/idempotency behavior, exact-search correctness, authorized metadata predicates, active-version exclusion, stable chunk/source mapping, empty results, database/provider failures, re-embedding candidate activation, and fair baseline metric computation.

**Framework evidence required.** Embedding/provider and index versions, corpus/question/config hashes, side-by-side recall/latency/access results, query plans or index rationale, failure analysis, cost observations, reproducible commands, and Baseline-stage Go/No-Go for generation work.

**Acceptance criteria.** Semantic retrieval is reproducible and access-correct, retrieved chunks map to authoritative source headings, Phase 3 comparison is fair, and measured results justify or reject semantic complexity. Vector distance is retained only as a ranking signal and never exposed as confidence.

**Risks.** Embedding drift, mixed dimensions, misleading similarity interpretation, provider data retention, vector/relational resource contention, post-retrieval filtering leakage, or tuning against golden questions.

**Recommended commit boundary.** Separate the provider/contracts and pgvector persistence from the frozen comparison evidence when useful, but do not mix LLM generation or LangGraph. Each commit must keep tests passing and declare the active embedding version.

### Phase 5 — Grounded RAG workflow

**Objective.** Add bounded grounded-answer behavior after retrieval has passed its gate; define the plain deterministic workflow contract that the later LangGraph/HITL stage will orchestrate.

**Tasks.** Define the six answer statuses and evidence bundle contract; implement deterministic evidence sufficiency inputs and decision rules; define an LLM provider interface and test fake; create bounded prompts that treat retrieved text as untrusted data; generate answers only from authorized evidence; validate citations; route partial, conflicting, insufficient, restricted, and high-risk cases correctly; record model/prompt/config versions; and specify the plain workflow and service contracts before LangGraph, HITL, and MCP integration.

**Files or modules expected.** `app/providers/llm/`, `app/services/evidence.py`, `app/services/answer_generation.py`, `app/services/citation_validation.py`, answer schemas/domain types, optionally `app/workflows/rag_graph.py`, prompt assets or builders, and unit/integration/security/evaluation tests.

**Dependencies.** Approved LLM adapter and, only after a written complexity decision, LangGraph. Do not add reranking, query rewriting, or hybrid-retrieval dependencies unless a separate measured gap and gate approves them.

**Tests.** All six statuses; supported claim/citation mapping; partial answers limited to supported parts with stated gaps; conflicts reported with citations and escalated, never resolved automatically; insufficient evidence refusal; restricted generic response; invalid/hallucinated citations; malicious document instructions; provider timeout/schema failure; deterministic routing; workflow resume/version behavior if LangGraph is introduced.

**Framework evidence required.** Retrieval prerequisite evidence, prompt/model/workflow versions, baseline-versus-grounded evaluation, citation traces, groundedness/completeness/refusal/conflict results, prompt-injection tests, latency/cost samples, failure examples, complexity justification, and rollback configuration.

**Acceptance criteria.** Generation never runs on unauthorized evidence; supported/partial outputs cite valid accessible sources; partial gaps are explicit; conflicts and high-risk cases escalate; unsupported questions do not invent answers; no percentage is presented as confidence; LangGraph exists only with accepted justification.

**Risks.** Hallucination, citation laundering, prompt injection, model-based authorization, hidden general-knowledge supplementation, schema drift, excessive cost/latency, and needless orchestration complexity.

**Recommended commit boundary.** First commit provider-neutral evidence/answer/citation contracts and deterministic tests; next commit the approved LLM adapter and evaluation evidence; add LangGraph in a separate commit/PR with its justification and state-transition tests.

### Phase 6 — Access control, escalation, feedback, and audit

**Objective.** Complete deterministic user-context enforcement and accountable post-answer workflows without enabling autonomous external actions.

**Tasks.** Define synthetic principal, role, department, manager, and explicit-document-rule fixtures; implement deny-by-default policy decisions; enforce filtering before retrieval/LLM and recheck response citations; create escalation records and reviewer state transitions; collect bounded feedback; write append-oriented audit events with correlation and version references; redact/minimize logged content; expose no inaccessible title, count, excerpt, or citation.

**Files or modules expected.** `app/domain/access.py`, `app/services/authorization.py`, `app/services/escalation.py`, `app/services/feedback.py`, `app/services/audit.py`, repository implementations, API schemas/routes as needed, and security/integration tests.

**Dependencies.** Prefer existing application/database capabilities. No production identity provider or communication-channel SDK is added. Any audit or telemetry library is separately reviewed for data handling.

**Tests.** Positive and negative matrices for all roles/departments/access/confidentiality values; unauthorized source existence leakage; citation recheck; administrator-versus-content entitlement; escalation creation/assignment/close; feedback validation; audit event completeness/redaction/order; retries/idempotency; database failure; and proof that no escalation action sends externally.

**Framework evidence required.** Access matrix and decision-table version, zero-known-disclosure critical test results, escalation/feedback traces, audit samples, redaction review, role-owner review, failure analysis, and residual-risk decision.

**Acceptance criteria.** Every protected path is deny-by-default; access filtering precedes generation; restricted responses are generic; conflicts and required reviews create traceable escalation; feedback cannot change policy/content automatically; audit records are useful without secrets or unnecessary source content; no risky action is autonomous.

**Risks.** Policy gaps, identity-fixture assumptions leaking into future design, metadata side channels, audit over-collection, reviewer queue ambiguity, duplicate events, and accidental coupling of escalation to external sending.

**Recommended commit boundary.** Separate commits for access-policy enforcement, escalation/feedback, and audit where each remains testable. Security evidence accompanies the access commit; no frontend or external adapter is bundled.

### Phase 7 — React demo interface

**Objective.** Provide a clear synthetic-only demonstration interface for questioning, status/citation display, feedback, escalation, and authorized document/reviewer views.

**Tasks.** Establish the React toolchain after approval; implement session/persona selection for synthetic roles, question submission, loading/error states, answer-status presentation, source/heading citations, partial-gap and conflict displays, generic access restriction, escalation/feedback actions, and synthetic-demo banners; add minimal authorized admin/reviewer views if backend milestones support them; meet keyboard, semantic markup, and basic accessibility expectations.

**Files or modules expected.** `frontend/` source, API client, typed response models, question/result/status/citation/feedback/escalation components, synthetic-session controls, tests, build configuration, and demo usage documentation.

**Dependencies.** Approved React/build/test packages pinned in the frontend manifest and lockfile. Avoid adding a large component framework unless a reviewed usability or accessibility need justifies it.

**Tests.** Component rendering for all statuses, citation links/anchors, partial gaps, conflict escalation, restricted generic text, validation/errors, loading/retry behavior, no confidence percentage, no inaccessible metadata, keyboard navigation, basic accessibility checks, and mocked API contract compatibility.

**Framework evidence required.** Build/test commands, lockfile, UI test output, screenshots or recordings labelled synthetic, accessibility review, API contract version, user-review notes, known limitations, and demo-claim review.

**Acceptance criteria.** A reviewer can complete the approved demo journeys; status and provenance are unmistakable; conflicts cannot appear resolved; restricted content does not leak; every screen is visibly synthetic; no control suggests a live external send/action; frontend build and tests are reproducible.

**Risks.** UI masking backend uncertainty, unsafe rendering of Markdown, misleading status styling, accessibility gaps, frontend/backend contract drift, dependency sprawl, or demo polish being mistaken for production maturity.

**Recommended commit boundary.** One frontend-foundation commit, followed by reviewable journey/status commits. Keep backend contract changes separate or explicitly paired; do not combine Docker/deployment work.

### Phase 8 — Evaluation, Docker Compose, and company demonstration

**Objective.** Produce a reproducible, evaluated, controlled demonstration package and a decision record without claiming production readiness.

**Tasks.** Freeze corpus, questions, configuration, prompts, models, and code revision; run retrieval and integrated RAG evaluations; complete error analysis and security regressions; package React, FastAPI, and one PostgreSQL service with pgvector in Docker Compose; mount synthetic sources and use non-secret configuration; test clean startup, migrations, ingestion, demo flows, shutdown, backup/restore assumptions, and rollback; create a demo guide, limitations statement, evidence index, release checklist, and company review pack.

**Files or modules expected.** `tests/evaluation/`, `data/evaluation/`, evaluation scripts/results policy, Dockerfiles, `docker-compose.yml`, safe configuration templates, health checks, `docs/demo/`, `docs/evidence/`, and release/rollback instructions. Generated databases, vectors, logs, and secret-bearing files remain untracked.

**Dependencies.** Approved container base images and pinned runtime/frontend dependencies. Docker Compose is an initial local/controlled demonstration topology. It is not a production orchestrator decision. No Pinecone or communication adapter is included.

**Tests.** Frozen golden-dataset metrics; fair baseline comparisons; all answer statuses; access/adversarial cases; citation correctness; groundedness/completeness/refusal/conflict handling; latency/resource samples; clean Docker build/start; service health; migration/ingestion idempotency; provider failure; restart; documented rollback; and demo smoke test.

**Framework evidence required.** Exact build/run commands, source/artifact identifiers, dependency/image inventories, all quality and evaluation results, raw and summarized errors, access-security evidence, Docker smoke evidence, demo review, known limitations, unresolved risks, and signed Evaluation/Delivery company Go/No-Go decisions.

**Acceptance criteria.** An approved reviewer can reproduce the exact synthetic demo from documented commands; critical access tests have zero known prohibited disclosure; required quality/evaluation gates pass or have explicitly accepted exceptions; artifacts map to the evaluated revision; limitations and non-production status are prominent; no live external action exists.

**Risks.** Environment-specific packaging, stale evidence, hidden credentials, non-reproducible provider behavior, cherry-picked demo cases, image vulnerabilities, resource exhaustion, or company stakeholders interpreting Delivery approval as Production approval.

**Recommended commit boundary.** Separate evaluation/dataset, containerization, and demo/evidence commits where practical. The final PR contains only the reviewed MVP release-candidate scope and links every material claim to evidence; production deployment remains a separate future decision.

## 9. Dependency plan

Dependencies are introduced only in the phase that uses them, pinned, reviewed, and accompanied by a test that exercises the capability. Selection criteria are maintenance status, license compatibility, security history, Python/Node/PostgreSQL compatibility, transitive footprint, data handling, platform support, and exit cost.

| Capability | Earliest phase | Planned decision |
|---|---:|---|
| PostgreSQL driver, migrations, ORM/query layer, pgvector integration | 1 | Select together so async/sync behavior, typing, migrations, and vector types are compatible |
| Safe YAML and Markdown parsing | 2 | Reject unsafe YAML features and preserve heading/source locations |
| Embedding adapter | 4 | Provider-neutral contract first; fake adapter required for tests |
| LLM adapter | 5 | Provider-neutral structured-result contract; credentials runtime-only |
| LangGraph | 5 | Add only after a written workflow-complexity justification |
| React toolchain and test utilities | 7 | Pin manifest and lockfile; keep UI dependency surface small |
| Container base images | 8 | Pin supported images and capture scan/rebuild evidence |

No dependency is added merely because it may be useful later. Each dependency change is isolated or clearly visible in its phase PR, updates relevant lock/declaration files, and includes removal/rollback considerations. Pinecone SDKs, communication-channel SDKs, agent frameworks beyond the justified LangGraph use, and production infrastructure tools are excluded from the MVP dependency plan.

## 10. Database and pgvector foundation

PostgreSQL is the primary relational database and pgvector is an extension within that PostgreSQL service, not a separate database. Migrations should enable the extension, create versioned relational entities, and add vector columns whose dimension is tied to an embedding-set version. Initial retrieval may use exact vector ordering; ANN indexes are added only after corpus/load evidence identifies a need and their recall tradeoff is evaluated.

Database design must support candidate ingestion, atomic activation, superseding, archive exclusion, failed-run cleanup, re-embedding, and rollback. Least-privilege application and migration roles, connection limits, transaction boundaries, backup/restore expectations, and vector-versus-relational load monitoring are defined before the demonstration package is accepted.

## 11. Configuration strategy

Use one typed settings boundary under `app/core/` with startup validation and environment-specific values injected at runtime. `.env.example` may contain safe names and non-secret development defaults, never credentials. Configuration domains should cover application, database, source paths, embedding/LLM adapters, dimensions, chunking, retrieval, evidence rules, workflow/prompt versions, audit/logging, evaluation, and feature gates.

Tests and evaluation pin configuration explicitly. Audit/evidence records capture non-secret configuration versions or fingerprints. Invalid access, model, dimension, path, or threshold combinations fail at startup or job initialization. Configuration must not silently enable an external provider, real-data path, Pinecone, or external action.

## 12. Synthetic document preparation

Synthetic document generation begins only after the Data-stage company checkpoint. Authors use the fictional taxonomy, filenames, visible warning, and YAML fields in `docs/synthetic-data-policy.md`; a separate human reviews every version. The first corpus should be small but deliberately cover company-wide, departmental, managerial, HR, administrator, version, conflict, unsupported, and malicious-content test cases.

Source Markdown under `data/synthetic/` is authoritative. A manifest records path, document ID/version, fingerprint, status, owner role, review record, and validation result. `data/processed/` holds rebuildable artifacts only and remains excluded from source authority.

## 13. Document schema validation

The schema requires `document_id`, `title`, `document_type`, `department`, `version`, `status`, `effective_date`, `review_date`, `owner`, `access_level`, `confidentiality`, `synthetic`, `language`, and `tags`. Controlled values, date/version rules, filename agreement, visible labels, one-active-version rules, review dates, and cross-version consistency are deterministic checks.

Validation returns structured error codes and source locations, collects safe multiple errors where possible, and never activates a partially valid source. Security limits cover file size, nesting, aliases, duplicate keys, encoding, path traversal, and unexpected file types.

## 14. Markdown and YAML parsing

Parse exactly one leading YAML front-matter block with safe loader behavior, then parse Markdown into a document tree that retains the title, heading hierarchy, text, lists, tables, and source offsets needed for citations. YAML values are data, not executable objects. Markdown HTML, links, code, and embedded instructions are treated as untrusted content and normalized or rejected under an explicit policy.

Parsing is separate from validation and chunking so each layer has deterministic unit tests. Parse errors create inactive ingestion failures with correlation and source identifiers, not partial searchable records.

## 15. Heading-aware chunking

Chunk by meaningful heading path before applying size limits. A chunk contains a stable identifier, document ID/version, heading path, sequence, normalized text, source offsets or anchors, text fingerprint, lifecycle/access metadata, and chunker version. Small adjacent sections may be combined and oversized sections split with a bounded, documented overlap.

Chunk-size and overlap choices are configuration evaluated against retrieval quality; they are not tuned only to the final golden set. Re-chunking creates candidate artifacts and requires reconciliation plus evaluation before activation. Citations point to the authoritative document and heading, not to the chunk as a new source.

## 16. Keyword/metadata retrieval baseline

The baseline uses deterministic token/term matching and metadata selection over validated active sources. It shares exactly the same user context, authorization predicates, corpus version, top-k policy, citation anchors, and golden questions later used for semantic retrieval. Ranking and tie-breaking are documented and repeatable.

Baseline evidence includes per-question ranked sources, expected/prohibited matches, retrieval recall, latency samples, empty-result behavior, access correctness, and error analysis. It remains available as a diagnostic comparator even if semantic retrieval performs better.

## 17. Semantic retrieval baseline

Semantic retrieval embeds the question through the active embedding adapter and queries authorized, active vectors stored by pgvector in PostgreSQL. Lifecycle and access predicates must constrain candidates before evidence leaves persistence; a later response check provides defense in depth. Returned evidence preserves source and embedding versions.

Compare with Phase 3 using the same corpus, questions, identities, top-k, metrics, hardware conditions where feasible, and run protocol. Vector distance is an internal ranking value, not a probability, calibrated confidence, or user-facing assurance.

## 18. Embedding provider abstraction

Define typed batch requests and results with model identifier, dimension, preprocessing version, and usage/error metadata. The interface supports a deterministic fake for tests and one approved MVP adapter. It must not expose provider SDK objects to domain or retrieval services.

Retries are bounded to transient idempotent calls. Provider changes generate a separate embedding set; incompatible dimensions or preprocessing versions cannot mix. Data retention, region, cost, rate limits, and permitted content require company review before a live provider is enabled.

## 19. VectorStore abstraction

`VectorStore` owns storage-neutral operations such as write candidate embeddings, activate an embedding set, search authorized active candidates, reconcile counts, and delete or retire artifacts. Request and result types use domain identifiers and filters rather than SQL or vendor-specific fields.

The initial adapter uses PostgreSQL with pgvector. Contract tests run against the adapter and a test fake. Pinecone remains a future adapter option triggered only by ADR-001 revisit conditions and a new architecture/security/operational decision; business logic must not change merely to adopt it.

## 20. PostgreSQL persistence layer

Repository interfaces cover documents/versions, chunks, embedding sets, retrieval records, answers/citations, principals/policies, escalation, feedback, audit, and evaluation references. Concrete PostgreSQL repositories own queries and transactions; services own business rules. ORM/table models do not become domain entities by default.

Queries use parameterization and explicit ordering. Integration tests exercise real PostgreSQL and pgvector behavior, including transactions, constraints, concurrency-sensitive activation, cleanup, and failure recovery. Unit tests must not pretend an in-memory database proves PostgreSQL semantics.

## 21. Document ingestion workflow

For synthetic HR sources, the ingestion sequence is: accept an approved repository-relative structured-Markdown path; fingerprint; parse; validate metadata/content/policy; standardize; create a candidate document version; record human review/approval; chunk; embed; persist candidate artifacts; reconcile; atomically activate; audit. Later PDFs first require extraction, form pre-fill, user correction, duplicate/version checks, sensitive-data/redaction checks, and conversion to the same standardized-Markdown contract. Raw PDFs never go directly to embeddings. Repeating the same source/version is idempotent.

Any validation, provider, or persistence failure leaves the previous active version intact and the candidate unavailable to normal retrieval. Superseded and archived documents are excluded by default. Rollback reactivates a previously validated version and its compatible artifacts with an audit record.

## 22. LangGraph workflow introduction

Implement document and question handling first as explicit application-service steps or a plain state machine. Introduce the planned LangGraph workflow after retrieval and the underlying deterministic services are proven. It owns orchestration for explicit states, bounded retries, citation/evidence branches, escalation, and HITL interruption; it does not own the decisions performed by policy and governance services.

Define a typed workflow state, deterministic nodes, transition guards, resume identifiers, retry ownership, terminal statuses, and versioning. LangGraph cannot authorize access, decide approval authority or publication eligibility, apply sensitive-data policy, or authorize risky action. Unit tests cover each node and transition; integration tests cover interruption/resume and duplicate-resume behavior. Add MCP integration only after the application-service contracts are stable.

## 23. LLM provider abstraction

The LLM interface accepts a bounded system instruction, authorized evidence bundle, question, structured-output schema, model/config identifiers, and time/resource limits. It returns typed content or a classified provider failure. Domain code does not depend on a vendor SDK.

A deterministic fake supports all answer and error paths. The approved adapter minimizes transmitted data, records non-secret model/version metadata, validates structured output, and disables unsupported fallback behavior. Switching model/provider requires regression evaluation and a rollback configuration.

## 24. Grounded answer generation

Generation receives only evidence already authorized for the principal. Prompts require material claims to be supported by supplied evidence, prohibit using general knowledge to fill gaps, and treat document instructions as untrusted text. The output maps to the approved answer-status contract: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `CONFLICTING_DOCUMENTS`, `INSUFFICIENT_INFORMATION`, `ACCESS_RESTRICTED`, or `HUMAN_REVIEW_REQUIRED`.

Partial answers contain only supported facts and identify missing parts. Conflicts identify relevant sources but do not choose an authority. Insufficient and restricted results avoid invented answers. Generation failure produces a controlled error or human review, never a fabricated fallback.

## 25. Citation validation

Every material generated claim must reference evidence supplied in the same request, with document ID, title, version, and heading anchor. A deterministic validator confirms citation existence, user accessibility, active-version applicability, and source-anchor validity. It must reject fabricated, inaccessible, superseded, or orphan citations.

Citation validation failure downgrades or rejects the response according to policy and may create `HUMAN_REVIEW_REQUIRED`. Citation quality is measured separately from stylistic answer quality.

## 26. Access-control simulation

Synthetic principals cover employee, manager, HR reviewer, content administrator, system administrator, evaluator/auditor, and department assignments. Policy combines role, department, explicit document rules, `access_level`, and `confidentiality`; denial is the default. Infrastructure administration does not imply content entitlement.

Positive and negative tests cover every controlled value and cross-department combination. Restricted cases reveal no inaccessible document title, excerpt, citation, count, or existence signal beyond approved generic language. Simulation is not production identity integration and must be replaced/revalidated before real-user use.

## 27. Conflict handling

Conflict candidates include contradictory active sources, ambiguous applicability, overlapping effective periods, and incompatible statements. Deterministic metadata checks identify known lifecycle/date conflicts; text-level detection may flag additional cases but cannot decide authority.

Material unresolved conflict returns `CONFLICTING_DOCUMENTS`, a conflict notice with citations, and human escalation. No LLM or ranking score resolves which source governs. Resolution requires a content owner and a new approved source/version or documented disposition.

## 28. Unsupported-question handling

When authorized evidence does not address the question sufficiently, return `INSUFFICIENT_INFORMATION`; when policy blocks the answer, return `ACCESS_RESTRICTED`; when risk or system uncertainty needs a person, return `HUMAN_REVIEW_REQUIRED`. Responses may suggest a narrower question or review route but cannot infer missing company policy.

Tests include out-of-domain questions, compound partially supported questions, empty retrieval, ambiguous wording, inaccessible-only evidence, provider/database failure, and attempted prompt override.

## 29. Human escalation

An escalation record contains a permitted question summary, reason code, evidence references, answer/workflow/config versions, correlation ID, created time, assigned reviewer role, state, and disposition. Sensitive excerpts are minimized. State transitions are explicit and auditable.

The MVP may create and display review items only; it sends no email, WhatsApp message, voice action, or other external notification. Reviewer identity, service expectations, and escalation ownership require company confirmation.

## 30. Feedback collection

Feedback records answer ID/version, synthetic principal, helpful/unhelpful selection, bounded reason codes, optional minimized text, and timestamp. It supports evaluation and error triage but cannot automatically alter prompts, sources, retrieval thresholds, access rules, or deployments.

APIs validate size and allowed values; UI explains synthetic-demo use. Reports separate feedback from objective correctness metrics and preserve the configuration needed to reproduce the answer.

## 31. Audit logging

Append-oriented audit events cover document lifecycle, ingestion, policy decisions, retrieval, generation/status, citations, escalation, feedback, configuration changes, and reviewer decisions. Required fields include actor/system reference, action, time, correlation ID, target/version references, authorization result, outcome, and relevant provider/workflow versions.

Do not log secrets, full sources, embeddings, unrestricted prompts, or unnecessary question/excerpt content. Retention, tamper evidence, privileged access, and export are unresolved company decisions; the MVP must state those limitations.

## 32. React frontend milestones

1. Toolchain, API client, synthetic-session context, application shell, and tests.
2. Question form, validation, loading, safe error, and correlation-ID presentation.
3. Distinct rendering for all six statuses, including partial gaps and conflict escalation.
4. Citation/source-heading view with safe Markdown/text rendering.
5. Feedback and escalation interactions.
6. Minimal authorized document/reviewer views if supported by completed APIs.
7. Accessibility, synthetic labeling, responsive demonstration layout, and build evidence.

The frontend must never calculate confidence from vector distance or imply that a model answer is authoritative without its source evidence.

## 33. API milestones

1. Health/readiness and typed error contract.
2. Candidate document validation and authorized lifecycle endpoints.
3. Baseline retrieval/evaluation boundary.
4. Question endpoint returning status, answer, citations, gaps/conflict detail, and correlation ID.
5. Feedback and escalation create/read/review boundaries.
6. Authorized audit/evaluation access where needed for the demo.

Routers remain thin; services own use cases and policy; repositories/providers own external concerns. Every protected endpoint establishes an authenticated synthetic principal and validates size/type. API versioning and idempotency are explicit where lifecycle state changes.

## 34. Testing strategy

Use a test pyramid with pure unit tests for domain rules, validation, parsing, chunking, ranking, policy, evidence, statuses, and citations; PostgreSQL/pgvector and API integration tests for real boundaries; security tests for leakage, injection, paths, secrets, and access matrices; and evaluation tests for dataset-level behavior. Provider fakes make normal CI deterministic; live-provider tests are opt-in, credential-safe, separately reported, and never required to prove model-free logic.

Each defect receives the narrowest useful regression test. Test data follows the synthetic-data policy. Pytest, Ruff, and MyPy results are recorded per phase; frontend checks join in Phase 7. Passing tests do not imply production readiness.

## 35. Evaluation strategy

Freeze and version corpus, golden questions, identities, expected/prohibited sources, configurations, and metric code. Measure retrieval recall, citation correctness, groundedness, completeness, refusal correctness, access-control correctness, conflict handling, latency, and user feedback. Report per-case failures and useful segments, not only aggregates.

Phase 3 and Phase 4 comparisons use identical conditions. Phase 5 adds generation measures without discarding retrieval metrics. Company owners approve numeric thresholds before claiming a gate; critical access cases require zero known prohibited disclosures. Error analysis and limitations accompany every result.

## 36. Golden-question dataset

`data/evaluation/` should contain versioned synthetic cases with question ID/text, principal role/department attributes, expected answer status, expected and prohibited source IDs/versions/headings, required supported facts, acceptable gaps/refusal behavior, conflict expectations, and scenario tags. Include routine, partial, conflicting, unsupported, restricted, stale/superseded, archived-test-only, prompt-injection, cross-department, and failure scenarios.

Keep tuning/development cases separate from the frozen gate set. Human content and security reviewers approve expectations. Dataset changes require a reason, version, reviewer, and rerun of affected baselines.

## 37. Docker Compose milestone

Phase 8 packages the React frontend, FastAPI modular monolith, and one PostgreSQL service with pgvector. It mounts authoritative synthetic sources read-only where practical, uses persistent development volumes for database state, applies health checks and startup ordering, and injects secrets outside version control.

Document clean build, migration, ingestion, evaluation/demo start, shutdown, reset, and recovery commands. Pin images and review them. Docker Compose supports reproducibility for local/controlled demonstration only; it is not evidence of production topology, high availability, security approval, or disaster recovery.

## 38. Security checks

- Deny-by-default endpoint and retrieval authorization.
- Cross-role, cross-department, document-rule, access-level, and confidentiality matrices.
- No metadata, count, title, citation, timing detail, or error leakage for restricted sources.
- Safe YAML loading, bounded files/requests, path confinement, and parameterized queries.
- Prompt-injection documents treated as data and unable to change policy/workflow.
- Secrets absent from Git, images, logs, errors, prompts, evidence, and frontend bundles.
- Least-privilege database/runtime roles and safe CORS/host/output settings for the demo.
- Dependency and container review, with findings and exceptions recorded.
- No autonomous publication, sending, calling, routing, payment, or irreversible action.

Security testing is a gate, not a claim of compliance or exhaustive assurance.

## 39. Observability foundation

Use structured events and correlation IDs across API, ingestion, retrieval, provider, workflow, and persistence boundaries. Initial metrics include request/stage latency, ingestion validation/failure counts, retrieval result/status distribution, authorization denials, provider errors, citation failures, escalation queue state, evaluation revision, and PostgreSQL resource indicators.

Do not log unrestricted content. Redaction and sampling are tested. Dashboard/alert products, retention, access, thresholds, and incident routing are company decisions; Phase 8 needs only enough telemetry to reproduce failures and support the controlled demonstration.

## 40. Demo preparation

Prepare a scripted guide covering valid supported, partial, conflicting, insufficient, restricted, escalation, superseded-version, and prompt-injection scenarios. Every screen and artifact states that data and personas are synthetic. The guide lists prerequisites, exact revision/configuration, startup and reset commands, expected statuses/citations, known limitations, and troubleshooting.

Run the demo from a clean environment against the frozen evidence set. Do not improvise live data, enable real communication, hide failures, or imply production readiness. Company reviewers receive the architecture, risk, evidence, and unresolved-decision summary before the session.

## 41. Synthetic-to-real document transition

Real-data transition is outside the MVP and requires its own gate. Named business/data, content, security, privacy/legal as required, access, architecture, and operations owners must approve purpose, sources, classification, identity mapping, provider handling, retention, deletion, audit, backup, and recovery.

Approved real documents enter a separate environment and source records; synthetic files or artifacts are never relabeled or mixed. Re-run parsing, sampled content review, chunking, embeddings, access/adversarial evaluation, citation checks, load, backup, restore, rollback, and deletion tests. No real-user pilot starts without an explicit company Go decision.

## 42. Risks and mitigations

| Risk | Planned mitigation and gate |
|---|---|
| Accidental real/confidential data | Synthetic policy, separate review, scans, manifests; stop/isolate on discovery |
| Invalid or inconsistent sources | Deterministic schema/cross-version checks and content-owner review before activation |
| Unauthorized evidence leakage | Pre-retrieval filtering, response citation recheck, adversarial matrix, fail closed |
| Weak retrieval hidden by generation | Freeze and measure keyword then semantic baselines before LLM work |
| Hallucinated or invalid citations | Bounded evidence prompt, deterministic citation validation, explicit non-answer |
| Conflicts resolved automatically | `CONFLICTING_DOCUMENTS`, cited notice, mandatory human escalation |
| Vector distance shown as confidence | Treat only as ranking; schema/UI/test prohibition on confidence presentation |
| Embedding/model/provider drift | Versioned adapters/artifacts, regression evaluation, candidate activation, rollback |
| pgvector resource contention | Exact search initially, monitoring/load tests, tuning; revisit ADR-001 on evidence |
| LangGraph/abstraction over-complexity | Plain workflow first and a separate written justification/commit |
| Audit/log data exposure | Minimization, redaction tests, access controls, unresolved retention called out |
| Demo mistaken for production | Persistent synthetic labeling, limitations, separate Production gate |
| Scope expands to communications | No adapters/actions in MVP; separate ADR, channel approval, human execution gate |

## 43. Decisions requiring company confirmation

- Named business sponsor, architecture owner, data/content owners, security owner, evaluation owner, escalation reviewers, and release authority.
- Supported Python/Node/PostgreSQL environments and Windows/WSL expectations.
- PostgreSQL driver, migration/query tooling, deployment version, pgvector version, and database roles.
- Fictional company taxonomy and authorization semantics for role, department, `access_level`, `confidentiality`, and explicit rules.
- Permission to create and commit the synthetic corpus and evaluation dataset, including `.gitignore` treatment.
- LLM and embedding providers/models, data regions, retention/training terms, credentials, budgets, and rate limits.
- Chunking, top-k, evidence, metric, latency, cost, and critical acceptance thresholds.
- Whether measured workflow complexity justifies LangGraph in the MVP.
- Audit/log content, retention, access, tamper-evidence, and export requirements.
- Human escalation routing and review service expectations.
- Docker/container platform, image policy, demonstration audience, and release approval.
- Real-document approval, privacy/legal review, identity provider, hosting, recovery, and pilot gates.
- Separate future consent and approval rules for email, WhatsApp Business, and voice workflows.

Unconfirmed decisions remain explicit configuration blocks or phase blockers; engineers must not infer company policy.

## 44. Definition of Done

The MVP implementation is done only when:

- [ ] All nine phases meet their acceptance criteria with linked, versioned evidence.
- [ ] The exact implementation and configuration revision is identified and reproducible.
- [ ] All active sources are approved, synthetic, schema-valid, visibly labelled, and traceable.
- [ ] Keyword/metadata and semantic baselines are measured and fairly compared.
- [ ] PostgreSQL with pgvector operates as one tested database foundation behind `VectorStore`.
- [ ] Retrieval filters authorization and lifecycle before evidence reaches the LLM.
- [ ] All six statuses, partial gaps, conflict escalation, refusal, citations, feedback, and audit behavior pass tests.
- [ ] Conflicting documents are not automatically resolved and no risky/external action is autonomous.
- [ ] Vector distance or model self-rating is not presented as confidence.
- [ ] Pytest, Ruff, MyPy, frontend checks, integration/security/evaluation suites, and Docker smoke tests pass or have named, approved exceptions.
- [ ] Golden-dataset results, errors, access-critical cases, latency, and limitations are reviewed.
- [ ] Clean Docker Compose demonstration commands, reset/rollback instructions, and synthetic-only labeling are verified.
- [ ] Secrets, real data, generated databases/vectors, and unnecessary logs are absent from tracked artifacts.
- [ ] Documentation, evidence register, risk/decision updates, demo guide, and company review are complete.
- [ ] A named authority records the Evaluation/Delivery Go/No-Go for the exact artifact.

Completion means a reviewed synthetic MVP demonstration package, not production readiness, compliance, real-data approval, or authorization for external integrations.

## 45. Commit and pull-request boundaries

Commits should be single-purpose, independently testable, and ordered so reviewers can evaluate foundations before dependent behavior. Recommended boundaries are:

1. `foundation: add minimal FastAPI configuration and quality gates`
2. `database: add PostgreSQL pgvector migrations and repositories`
3. `documents: add schema validation and parser tests`
4. `data: add approved synthetic corpus and review manifest`
5. `retrieval: add keyword and metadata baseline with evidence`
6. `embeddings: add provider contract and versioned indexing`
7. `retrieval: add pgvector semantic baseline and comparison`
8. `rag: add evidence, status, and citation contracts`
9. `rag: add approved LLM adapter and grounded generation`
10. `workflow: add staged LangGraph and HITL document orchestration`
11. `mcp: expose stable OIAP application-service capabilities`
12. `security: enforce simulated access policy and leakage tests`
13. `review: add escalation, feedback, and audit workflows`
14. `frontend: add synthetic RAG demo journeys`
15. `evaluation: freeze golden dataset and integrated results`
16. `delivery: add Docker Compose and demonstration evidence`

Each PR states scope/non-goals, source architecture links, dependency changes, database migrations, exact validation commands/results, evidence artifacts, security/data impact, risks, unresolved decisions, rollback, and the next gate. Corpus/data PRs require content and data/security review; access/security PRs require control-owner review; provider PRs require provider/data-handling approval; release PRs require business, engineering, security, and evaluation review.

Do not mix broad formatting, unrelated refactors, generated artifacts, dependency upgrades, source-corpus changes, database migrations, provider changes, and feature behavior unless the combination is inseparable and explained. Never place secrets or real company data in a commit or PR. Staging, committing, pushing, release publication, deployment, and production approval are separate explicit actions; this plan performs none of them.
