# OIAP Enterprise AI/ML Engineering Framework Application Plan

## Purpose and framework alignment

This document applies the [Enterprise AI/ML Engineering Framework](https://github.com/chathuranga-sudusinghe/enterprise-ai-ml-engineering-framework) to the Office Intelligence Automation Platform (OIAP). The project follows the lifecycle:

**Problem → Data → Baseline → Advanced AI → Evaluation → Delivery → Production → Maintenance**

The framework supports structured engineering judgment; following it does not guarantee project success, legal compliance, security accreditation, or production readiness. Each gate requires OIAP-specific evidence and accountable human review. Phase 0 foundation work is completed. Phase 1 is now an HR-first Document Automation and Knowledge Agent, beginning with the PostgreSQL and pgvector document foundation. Synthetic document generation and later Phase 1 capabilities remain subject to their explicit implementation gates.

## Operating rules

- Use the simplest credible baseline before advanced AI behavior.
- Keep evidence, decisions, risks, exceptions, and gate outcomes versioned and reviewable.
- Use synthetic HR documents only for current development and clearly separate them from future approved real data.
- Apply role-, department-, document-, `access_level`-, and `confidentiality`-based filtering before LLM generation.
- Use deterministic controls for authorization, lifecycle, approvals, and external actions.
- Require citations, unsupported-question handling, human escalation, audit logging, monitoring, and evaluation.
- Preserve a FastAPI modular monolith with PostgreSQL and pgvector. Introduce RAG, LangGraph, MCP, HITL, React, and Docker Compose only at their controlled stages.
- Preserve LLM, embedding, and `VectorStore` abstractions; Pinecone is a future option, not an MVP dependency.
- Perform no autonomous risky action in the first implementation; future email, WhatsApp, and voice operations require separate approval.

## Phase 1 HR-first application

The current business slice applies the framework to HR document automation and knowledge retrieval. Synthetic HR documents deliberately use the future metadata, access, approval, versioning, and ingestion model. The framework sequence remains Data validation, keyword/metadata baseline, semantic baseline, grounded generation, evaluation, and delivery; the Phase 1 implementation additionally gates document standardization, HITL publication, LangGraph orchestration, and MCP integration.

Structured Markdown is the direct RAG source. A synthetic source must pass metadata validation, content validation, standardization, and human approval before chunking and embeddings can become active. Later real PDFs must first pass extraction, form pre-fill, user review/correction, duplicate/version checks, sensitive-data/redaction checks, and conversion to the same standardized-Markdown contract. Raw PDFs are never embedded directly.

LangGraph coordinates explicit workflow states and interruptions but does not decide authorization, access policy, approval authority, publication eligibility, or sensitive-data policy. The planned OIAP MCP server exposes selected business capabilities to LangGraph by wrapping application services; MCP tools do not duplicate core business logic. Neither component is currently implemented.

## Stage 1: Problem

### Stage objective

Define who OIAP serves, which company knowledge problem is worth solving, what risks are unacceptable, and what evidence would justify continuing.

### Project activities

- Identify employee, manager, content-administrator, reviewer, security, audit, and management users.
- Interview or otherwise validate business pain points: findability, inconsistent answers, source ambiguity, escalation delay, and audit gaps.
- Identify high-risk workflows, including restricted-document access and future email, WhatsApp, voice, caller-information, and external actions.
- Define measurable success, guardrails, scope, exclusions, assumptions, and constraints.
- Confirm that Phase 1 is synthetic-only HR document automation and knowledge retrieval, not communication automation.

### Required inputs

Business sponsor, user groups, current knowledge processes, candidate use cases, risk appetite, company policies, architecture constraints, and the proposed MVP boundary.

### Expected outputs

Approved problem statement, stakeholder/role map, user journeys, scope and non-goals, success and guardrail metrics, initial risk register, decision log, and MVP charter.

### Required evidence

Interview or workshop notes, pain-point examples without prohibited data, signed-off scope, prioritized use cases, metric definitions, assumptions, risk owners, and recorded disagreements.

### Key risks

Solving an unvalidated problem; expanding into high-risk communication automation; vague success criteria; missing content or security owners; treating a demo as proof of value.

### Human review responsibility

The business sponsor owns purpose and value; employee/management representatives validate workflows; security/data owners review risk and data boundaries; the architecture owner confirms technical scope.

### Go/No-Go gate

**Go** only if named owners approve the synthetic-only HR document automation and knowledge problem, users, success measures, exclusions, and risk boundaries. **No-Go** if the team cannot name a business decision, authoritative owner, or safe initial scope.

### Unresolved company decisions

Sponsor and owners; priority departments; pain-point ranking; acceptable user populations; success thresholds; risk appetite; escalation ownership; budget and schedule.

### Completion checklist

- [ ] Users and management stakeholders are identified.
- [ ] Business pain points and high-risk workflows are evidenced.
- [ ] MVP scope, excluded communication functions, and no-autonomous-action rule are approved.
- [ ] Success metrics, guardrails, assumptions, constraints, risks, and owners are recorded.
- [ ] Problem-stage Go/No-Go is signed and dated.

## Stage 2: Data

### Stage objective

Create a governed, reviewable synthetic corpus and metadata/evaluation design while planning—but not authorizing—the later real-document transition.

### Project activities

- Apply `docs/synthetic-data-policy.md`; generate no documents until separately authorized.
- Define and validate the governed HR metadata contract and Markdown semantic-section rules.
- Design fictional departments, roles, access cases, conflicts, versions, and unsupported topics.
- Validate content consistency, source labels, provenance, and absence of confidential or real data.
- Define source, processed-artifact, and evaluation directories and lifecycle behavior.
- Plan real-document inventory, owner approval, classification, ingestion, deletion, and re-indexing.

### Required inputs

Approved MVP scope, synthetic-data policy, metadata schema, access taxonomy, document taxonomy, proposed evaluation scenarios, and company data-handling requirements where known.

### Expected outputs

Approved schema and validators, synthetic corpus plan, source manifest design, data-quality checklist, access test matrix, lifecycle rules, evaluation-data specification, and synthetic-to-real transition plan.

### Required evidence

Schema test results, human review records, consistency and duplicate checks, prohibited-data scans, manifests/fingerprints, document/version status reports, and access-label coverage.

### Key risks

Accidental real or confidential data; implausibly clean documents; inconsistent dates or policies; metadata drift; access labels that do not represent company rules; derived artifacts mistaken for sources.

### Human review responsibility

Content owners review correctness and conflicts; security/data owners review prohibition and classification; AI engineers review chunking/evaluation suitability; an authorized company owner approves any future real source.

### Go/No-Go gate

**Go** to baseline implementation only when the synthetic schema, corpus plan, review process, access matrix, and source lifecycle are approved and no prohibited data is present. **No-Go** on unowned sources, invalid metadata, real data, or unresolved critical access ambiguity.

### Unresolved company decisions

Department taxonomy, role mapping, classification meanings, document owners, retention, audit retention, future real-source systems, lawful/authorized use, and real-data provider restrictions.

### Completion checklist

- [ ] Synthetic-only policy and mandatory YAML/Markdown schema are approved.
- [ ] No confidential or real company, employee, client, contact, credential, or contract data is present.
- [ ] Consistency, version, conflict, access, and lifecycle cases are planned.
- [ ] Sources and generated chunks/embeddings are clearly distinguished.
- [ ] Synthetic-to-real transition requirements are recorded.
- [ ] Data-stage Go/No-Go is signed and dated.

## Stage 3: Baseline

### Stage objective

Build and measure the simplest credible retrieval references before adding grounded generation or agent-like workflow complexity.

### Project activities

- Define baseline questions, role/department contexts, expected source documents, prohibited sources, and acceptable refusal behavior.
- Implement a simple keyword and/or metadata retrieval baseline with the same access filters.
- Implement a basic semantic retrieval baseline using PostgreSQL with pgvector through `VectorStore`.
- Hold corpus, questions, access identities, top-k, and evaluation conditions constant for fair comparison.
- Record latency, retrieval recall, errors, and reproducibility details.
- Avoid proceeding directly to advanced agent behavior.

### Required inputs

Approved synthetic corpus, versioned golden questions, expected sources, access matrix, baseline metric definitions, PostgreSQL/pgvector design, and reproducible environment specification.

### Expected outputs

Runnable keyword/metadata and semantic baselines, locked configurations, results report, error taxonomy, retrieval examples, and a measured gap statement.

### Required evidence

Code/test revision, corpus and dataset versions, commands, environment/configuration, result artifacts, metric calculations, per-case failures, latency samples, and reviewer sign-off.

### Key risks

Unfair baseline comparison; evaluation leakage; weak expected-source labels; access filters omitted from one baseline; optimizing on the test set; interpreting vector distance as confidence.

### Human review responsibility

AI engineers implement and analyze; content owners verify expected sources; security reviewers verify prohibited-source behavior; the architecture owner approves whether measured gaps justify more complexity.

### Go/No-Go gate

**Go** to Advanced AI only if baselines are reproducible, fairly compared, access-correct, and show a material documented gap that a proposed method can address. **No-Go** if the baseline is absent, not credible, or already sufficient for the approved objective.

### Unresolved company decisions

Metric thresholds, relative value of keyword versus semantic results, latency and cost targets, golden-dataset ownership, acceptable failure categories, and projected corpus/load size.

### Completion checklist

- [ ] Baseline questions and expected/prohibited documents are independently reviewed.
- [ ] Keyword/metadata and semantic retrieval use identical authorized conditions.
- [ ] Retrieval recall, latency, errors, and access correctness are reported.
- [ ] Results are reproducible and do not use percentage-like model confidence.
- [ ] Measured gaps and proposed next methods are explicit.
- [ ] Baseline-stage Go/No-Go is signed and dated.

## Stage 4: Advanced AI

### Stage objective

Add only the advanced components needed to close measured baseline gaps while preserving deterministic authorization and human control.

### Project activities

- Add evidence-grounded answer generation with verified citations and explicit answer statuses.
- Introduce LangGraph after deterministic services are proven, for bounded workflow control, HITL document publication, evidence checks, feedback, and human escalation.
- Expose selected stable application-service capabilities through OIAP's MCP server without moving business rules into MCP tools.
- Evaluate reranking or query rewriting only if a specific baseline error category justifies it.
- Keep LLM, embedding, and vector-store interfaces provider-independent.
- Add conflict detection, unsupported-question handling, prompt-injection defenses, and policy-controlled refusal.
- Measure quality, latency, cost, operational complexity, and regression against the baseline.

### Required inputs

Accepted baseline evidence, error analysis, approved target gaps, answer-status contract, security boundaries, provider constraints, human-review workflow, and acceptance metrics.

### Expected outputs

Versioned workflow, prompts, provider adapters, grounded-generation behavior, citation verifier, evidence rules, escalation flow, architecture decision updates, and comparative results.

### Required evidence

Baseline-versus-advanced evaluation, ablations where useful, prompt/model/config versions, access and injection tests, citation traces, failure cases, cost/latency data, human-review outcomes, and rollback proof.

### Key risks

Unsupported answers; citation mismatch; prompt injection; model used as an authorization authority; hidden provider data retention; unjustified complexity; reviewer overload; behavior drift.

### Human review responsibility

AI engineers own implementation evidence; content experts review groundedness/conflicts; security owners review provider and attack boundaries; human reviewers decide escalations; architecture/business owners approve complexity.

### Go/No-Go gate

**Go** only if advanced methods improve approved gaps without failing access, safety, citation, latency, cost, or rollback guardrails. **No-Go** if improvement is not material, controls depend on model discretion, or baseline behavior is safer and sufficient.

### Unresolved company decisions

LLM and embedding providers, data regions/retention, acceptable models, evidence thresholds, reranking/query-rewriting need, prompt ownership, review service levels, and escalation authority.

### Completion checklist

- [ ] Each advanced method maps to a measured baseline gap.
- [ ] Access filtering precedes LLM generation and is deterministically tested.
- [ ] Citations and all six answer statuses are validated.
- [ ] Human escalation works and no risky action is autonomous.
- [ ] Provider, prompt, model, and workflow versions are traceable and reversible.
- [ ] Advanced-AI Go/No-Go is signed and dated.

## Stage 5: Evaluation

### Stage objective

Evaluate the integrated RAG workflow under realistic synthetic scenarios and make limitations, errors, and tradeoffs decision-ready.

### Project activities

- Measure retrieval recall, citation correctness, groundedness, completeness, refusal correctness, access-control correctness, latency, user feedback, and conflict handling.
- Segment tests by role, department, document type/status, access level, confidentiality, and answer status.
- Exercise unsupported, partially supported, conflicting, restricted, stale-version, malicious-content, provider-failure, and escalation cases.
- Compare against the frozen baseline under consistent conditions.
- Perform human review, error analysis, regression testing, and threshold sensitivity analysis.

### Required inputs

Frozen corpus and golden dataset, evaluation protocol, baseline results, integrated build/configuration, expected citations/statuses, user/access fixtures, metric definitions, and company-approved thresholds.

### Expected outputs

Evaluation report, metric tables, error taxonomy, qualitative examples, access-control report, latency/cost report, known limitations, remediation plan, and gate recommendation.

### Required evidence

Dataset hashes/versions, exact commands/configuration, raw and summarized results, calculation tests, reviewer annotations, failed cases, regression comparisons, and documented threshold decisions.

### Key risks

Test leakage; aggregate metrics hiding access failures; subjective groundedness labels; small clean corpus; evaluator disagreement; cherry-picked demos; model/provider drift after evaluation.

### Human review responsibility

AI/evaluation engineers own reproducibility; content experts label sources and correctness; security reviewers own access/adversarial cases; representative users review usability; business owners accept residual risk.

### Go/No-Go gate

**Go** to Delivery only if approved thresholds pass, critical access tests show zero known prohibited disclosure, error analysis is complete, and residual risks are accepted. **No-Go** on unverified citations, unsafe refusals, material regressions, or non-reproducible results.

### Unresolved company decisions

Numeric thresholds, critical-case policy, human rating rubric, acceptable latency/cost, sample sizes, user-feedback population, evaluator independence, and residual-risk authority.

### Completion checklist

- [ ] All required retrieval, answer, refusal, access, conflict, latency, and feedback measures are reported.
- [ ] Baseline and advanced methods use fair, versioned conditions.
- [ ] Critical and segmented failures are visible, not averaged away.
- [ ] Limitations and residual risks are accepted by named owners.
- [ ] Evaluation artifacts and commands are reproducible.
- [ ] Evaluation-stage Go/No-Go is signed and dated.

## Stage 6: Delivery

### Stage objective

Package the evaluated MVP so an approved reviewer can reproduce, inspect, demonstrate, and decide on it without implying production status.

### Project activities

- Create reproducible packaging with Docker Compose, pinned/controlled dependencies, and secret-free configuration templates.
- Complete architecture, decisions, data, API, operations, evaluation, security, and limitation documentation.
- Prepare release checklist, demo guide, rollback notes, known-issues register, and company review materials.
- Run Pytest, Ruff, MyPy, image/dependency checks, and clean-environment startup validation when implementation exists.
- Produce a traceable release candidate without unapproved data or credentials.

### Required inputs

Accepted evaluation evidence, versioned source, dependency manifests, configuration schema, documentation set, security findings, known risks, and release scope.

### Expected outputs

Versioned release candidate, Docker Compose package, configuration examples, test/quality reports, release checklist, demo guide, evidence index, rollback guide, and reviewer decision pack.

### Required evidence

Build/run commands and outputs, artifact hashes, dependency and license inventory, test/lint/type results, image scan results, configuration validation, clean-start demo evidence, documentation review, and approval record.

### Key risks

Environment-specific builds; secrets or generated data in artifacts; incomplete docs; stale evaluation; demo paths bypassing controls; artifact/source mismatch; release mistaken for production approval.

### Human review responsibility

Engineering owns reproducibility; security reviews artifacts/configuration; content and business owners review demo claims; release authority decides whether the package may be shared or piloted.

### Go/No-Go gate

**Go** only if a clean reviewer environment can reproduce the documented behavior, required checks pass or have accepted exceptions, artifacts match evidence, and company review approves the exact delivery. Delivery approval is not production approval.

### Unresolved company decisions

Artifact registry, supported host platforms, release/version scheme, dependency policy, license review, distribution audience, demo environment, exception authority, and release signer.

### Completion checklist

- [ ] Docker Compose and configuration templates reproduce the approved demo without secrets.
- [ ] Documentation, release checklist, demo guide, known issues, and rollback instructions are complete.
- [ ] Pytest, Ruff, MyPy, security, and packaging evidence is recorded.
- [ ] Artifact hashes map to source and evaluation versions.
- [ ] Company reviewers approve claims and distribution scope.
- [ ] Delivery-stage Go/No-Go is signed and dated.

## Stage 7: Production

### Stage objective

Decide whether and how OIAP may operate with real users or data, then deploy only under approved security, reliability, support, and governance controls.

### Project activities

- Obtain separate deployment and synthetic-to-real approval.
- Configure company identity, least privilege, runtime secrets, network controls, encryption, and provider settings.
- Establish structured logging, monitoring, alerts, backup, restore, incident response, rollback, recovery, and access review.
- Validate capacity, availability, cost, retention, deletion, audit, and disaster-recovery objectives.
- Run a bounded pilot with staged rollout, rollback triggers, named support, and no autonomous risky actions.

### Required inputs

Approved delivery artifact, real-data transition evidence, threat model, provider and privacy/legal reviews, deployment design, operational objectives, runbooks, on-call/support model, and business authorization.

### Expected outputs

Approved deployment, environment/configuration record, access assignments, monitoring dashboards/alerts, backups, tested runbooks, incident and change procedures, pilot report, and production decision.

### Required evidence

Deployment approvals, secret/access review, penetration/security results as required, load and failure tests, backup/restore evidence, rollback/recovery drills, monitoring alert tests, audit samples, incident exercises, cost measurements, and pilot feedback.

### Key risks

Unauthorized disclosure; provider data handling; weak identity mapping; inadequate recovery; alert fatigue; unbounded cost; real documents with conflicts or personal data; pilot expansion without approval; communication actions causing harm.

### Human review responsibility

Company deployment authority owns Go/No-Go; security, privacy/legal, data, infrastructure, business, and support owners approve their controls; content owners approve sources; humans approve every future externally visible risky action.

### Go/No-Go gate

**Go** only with explicit deployment approval, accepted residual risk, tested controls and recovery, named operational ownership, approved real data, and bounded rollout criteria. **No-Go** if any critical access, secret, backup, incident, rollback, or data-ownership control lacks evidence.

### Unresolved company decisions

Hosting and network topology, identity provider, availability/recovery objectives, retention and legal hold, data region, provider contracts, incident severity model, on-call coverage, budget, pilot cohort, and communication consent/approval rules.

### Completion checklist

- [ ] Deployment approval is separate from delivery approval.
- [ ] Secrets, identity, access, logging, monitoring, backup, incident response, rollback, recovery, and access review are tested.
- [ ] Real documents and provider use have named approval.
- [ ] Capacity, latency, availability, cost, and support ownership are accepted.
- [ ] Pilot scope and automatic rollback/stop conditions are documented.
- [ ] Production-stage Go/No-Go is signed and dated.

## Stage 8: Maintenance

### Stage objective

Keep approved behavior, documents, access, providers, and operations trustworthy; learn from failures; and retire components or the platform when value no longer justifies risk and cost.

### Project activities

- Review document freshness, owner assignments, conflicts, superseding, deletion, re-ingestion, and re-indexing.
- Analyze feedback, unsupported queries, failures, access denials, citations, drift, latency, cost, and escalation workload.
- Version and evaluate prompt, model, embedding, chunking, retrieval, and workflow changes before release.
- Update dependencies and access policies through controlled changes.
- Exercise backup, recovery, rollback, and incident procedures on schedule.
- Define model/provider replacement and system retirement criteria.

### Required inputs

Production telemetry, audit records, feedback, incidents, document review dates, dependency advisories, provider notices, access reviews, cost reports, evaluation datasets, and business value measures.

### Expected outputs

Maintenance reviews, refreshed documents/indexes, failure analyses, regression reports, patched releases, access recertification, updated runbooks, risk/decision changes, and retirement or continuation recommendations.

### Required evidence

Freshness and owner reports, re-index reconciliation, trend metrics, incident postmortems, feedback disposition, prompt/model/version history, dependency scan and update tests, access review records, recovery drills, cost/value analysis, and deletion evidence.

### Key risks

Stale or conflicting sources; silent provider/model drift; access creep; dependency vulnerabilities; evaluation dataset obsolescence; unreviewed prompt changes; ineffective alerts; retained data beyond need; indefinite operation without value.

### Human review responsibility

Content owners recertify documents; access/security owners recertify policy; AI engineers evaluate behavior changes; operations owns reliability; business owners decide continuation; company authority approves retirement and data disposition.

### Go/No-Go gate

At each review, **Go** to continue only if value, evaluation, security, access, freshness, recovery, cost, and ownership remain acceptable. Pause, rollback, restrict, or retire when thresholds fail or critical ownership/evidence is absent.

### Unresolved company decisions

Review cadence, service objectives, freshness windows, drift thresholds, feedback service levels, dependency update policy, access recertification schedule, retention/deletion schedule, model retirement triggers, and platform retirement authority.

### Completion checklist

- [ ] Document refresh, superseding, re-ingestion, and deletion are current.
- [ ] Feedback, failures, drift, access, latency, cost, and escalation trends are reviewed.
- [ ] Prompt/model/dependency/access changes pass regression and approval gates.
- [ ] Backup, recovery, rollback, and incident runbooks are exercised.
- [ ] Value, residual risk, and retirement criteria have named owners.
- [ ] Maintenance continuation/pause/retirement decision is signed and dated.

## Project evidence register

The evidence register is a repository-traceable index, not a claim that evidence exists. Each row must identify an immutable or versioned artifact, owner, reviewer, date, scope, result, limitations, and related gate.

| Evidence ID | Category | Planned evidence | Stage/gate |
|---|---|---|---|
| `EVD-PROBLEM-*` | Problem | User/pain-point evidence, scope, metrics, stakeholder approval | Problem |
| `EVD-DATA-*` | Data | Schema validation, manifests, reviews, prohibited-data checks | Data |
| `EVD-BASE-*` | Baseline | Dataset/config versions, commands, metrics, errors | Baseline |
| `EVD-AI-*` | Advanced AI | Comparative tests, prompts/models, citation/access traces | Advanced AI |
| `EVD-EVAL-*` | Evaluation | Frozen datasets, results, calculations, annotations | Evaluation |
| `EVD-DEL-*` | Delivery | Builds, checks, hashes, demo and release review | Delivery |
| `EVD-PROD-*` | Production | Deployment, controls, recovery, monitoring, pilot approvals | Production |
| `EVD-MAINT-*` | Maintenance | Trends, refresh, incidents, updates, access/value reviews | Maintenance |

Evidence containing sensitive information must be access-controlled and referenced without copying it into open documentation. Failed and inconclusive evidence remains visible with disposition.

## Engineering decision register

Significant decisions use ADRs with status, context, options, rationale, consequences, security/operational/cost impacts, validation, owners, revisit conditions, and links to evidence. The initial entry is `docs/decisions/ADR-001-vector-database.md`, which selects PostgreSQL with pgvector behind a `VectorStore` interface. Future entries should cover identity, LLM/embedding providers, access policy, document/object storage, evaluation thresholds, deployment, audit retention, and any Pinecone or service-decomposition proposal. Superseded ADRs remain linked rather than rewritten silently.

## Risk register expectations

Each risk record includes ID, description, cause, affected users/data/workflows, likelihood and impact rationale, current controls, evidence, owner, target treatment, residual risk, trigger/indicator, review date, status, and gate impact. At minimum track unauthorized retrieval, unsupported answers, citation error, prompt injection, content conflict/staleness, real-data leakage, provider handling, pgvector capacity, operational recovery, audit exposure, reviewer overload, integration side effects, cost, and scope expansion. Company owners, not the LLM, accept residual risk.

## AI-assisted development review responsibility

AI tools may assist planning, drafting, coding, tests, or review, but their output is untrusted until a qualified human reviews it. The human author remains responsible for correctness, licensing, security, privacy, architecture fit, reproducibility, and disclosure. Record material AI assistance, affected artifacts, validation performed, reviewer, unresolved limitations, and approval where the framework or company requires it. AI output cannot approve a gate, accept risk, authorize access, publish a document, or execute an irreversible action.

## Synthetic-to-real-data transition gate

Transition is a separate company gate, not a routine configuration change. **Go** requires named business/data/security/privacy or legal/technical owners; authorized purpose and sources; classification, retention, deletion, provider, regional, and audit decisions; production identity and access mapping; isolated ingestion; content-owner sampling; new embeddings/indexes; real-data retrieval, citation, refusal, conflict, adversarial access, load, backup, recovery, and rollback evidence; and explicit signed approval. **No-Go** applies if ownership, authorization, critical access correctness, deletion, recovery, or residual-risk acceptance is missing. Synthetic sources and artifacts are not relabelled or mixed with real ones.

## Company approval checkpoints

| Checkpoint | Minimum approving roles | Decision boundary |
|---|---|---|
| Problem/MVP scope | Business sponsor, architecture owner, security/data representatives | Whether the synthetic HR document automation and knowledge objective is worth pursuing |
| Synthetic data design | Content, data, security, AI engineering | Whether documents may be generated and used for baseline work |
| Baseline to Advanced AI | Architecture, AI engineering, content/security reviewers | Whether measured gaps justify generation, LangGraph, reranking, or rewriting |
| Evaluation to Delivery | Business, AI/evaluation, security, content | Whether quality and risk evidence supports packaging |
| Release candidate | Release authority, engineering, security, business | Whether the exact artifact may be shared or demonstrated |
| Synthetic to real | Business/data owner, security, privacy/legal as required, architecture | Whether approved real sources may enter an isolated environment |
| Production/pilot | Deployment authority plus business, security, data, operations/support | Whether exact users, data, environment, and duration may operate |
| Future integration | Channel business owner, security/privacy/legal as required, operations | Whether email, WhatsApp, or voice behavior may be connected; sending remains human-approved |
| Maintenance change | Change owner plus affected technical/business/control owners | Whether a document, model, prompt, dependency, access, or infrastructure change may release |
| Retirement | Business, data, security, operations | Whether service stops and data/artifacts are retained or deleted |

Every checkpoint records scope, evidence reviewed, decision, conditions, dissent or exceptions, approvers, date, expiry/review date, and rollback or stop criteria. Approval for one checkpoint does not imply approval for later stages.
