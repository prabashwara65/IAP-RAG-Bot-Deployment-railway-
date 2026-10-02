# Office Intelligence Automation Platform

## Overview

The Office Intelligence Automation Platform (OIAP) is an AI engineering project
for controlled internal knowledge retrieval, built around one principle: an
assistant should answer only from approved source documents, and should show
which ones it used.

The current focus is an **HR RAG MVP** — a retrieval-augmented generation
service that answers HR questions strictly from an approved, versioned document
set, returns validated citations for supported answers, and says so plainly when the
available sources do not support an answer.

The longer-term goal is governed office automation: document ingestion with
human approval, workflow orchestration, and assistive automation that keeps a
person in the decision loop rather than acting autonomously.

**Current status: a deployed portfolio demo running on AWS.** The assistant is
publicly reachable through CloudFront and answers real questions against a
synthetic HR corpus. It is a demonstration system, not an enterprise product:
signup uses email and password, login adds a Gmail OTP as 2FA, there is still
no authorisation, and the HR content is synthetic throughout. See
[Current Limitations](#current-limitations) for the full list — that section is
deliberately specific rather than reassuring.

## Current Milestone

**Deployed public demo on AWS.** The conversational HR assistant runs end to end
on deployed AWS infrastructure, served from CloudFront and backed by ECS Fargate,
RDS PostgreSQL with pgvector, and the Gemini APIs. Deployment is automated:
merging to `main` builds and ships both the backend image and the frontend
bundle through GitHub Actions.

The grounded answer flow behind it:

```
User
  -> React chat UI
    -> FastAPI
      -> query embedding (Gemini)
        -> pgvector semantic retrieval (PostgreSQL)
          -> grounded LLM answer (Gemini)
            -> validated citation(s) shown under the answer
```

A question typed into the browser is embedded, matched against approved
synthetic HR chunks by cosine distance, assembled into a bounded prompt
context, answered by the model under a grounding instruction, checked so that
every citation the answer claims actually exists in the retrieved evidence, and
returned to the UI with its sources. When retrieval finds nothing usable, the
service returns an explicit insufficient-evidence result instead of an
unsupported answer.

Each question is answered independently. The browser keeps the conversation
transcript for the session, but no prior turn is sent to the backend and the
model holds no memory between questions — every answer is grounded solely in
the sources retrieved for that one question.

The deployment has not been load-tested or security-tested, and is sized and
configured as a demonstration rather than as a production service.

## Public Demo

<!-- MAINTAINER: paste the public CloudFront URL below when you are ready to
     publish it. It is deliberately left blank here rather than copied out of
     the deployment workflow. -->

**Live demo:** https://d2d2u4ttuwfwlz.cloudfront.net

The demo answers questions from a small synthetic HR corpus covering leave,
remote work, expenses, and probation. Ask something outside that corpus and it
will say so rather than guess.

`POST /api/v1/hr/ask` is rate limited to **5 requests per minute per client**;
exceeding that returns `429` and the interface shows a dedicated rate-limit
message rather than a generic error.

## Screenshots

### Conversational HR Assistant

![OIAP conversational HR assistant](docs/images/oiap-conversational-hr-assistant.png)

The deployed interface, showing a multi-turn conversation, a grounded answer
with its collapsible **Sources** control, and the explicit insufficient-evidence
state for a question the approved corpus cannot support.

<!-- Future screenshots to add when captured:
     - GitHub Actions CI/CD run
     - AWS deployment architecture diagram
     - rate-limit (429) behaviour in the UI -->

## Implemented Capabilities

Only features that exist in this repository are listed here.

### Backend and RAG

- FastAPI modular monolith with a typed application composition root.
- Typed configuration via Pydantic Settings, with validation of environment,
  version, log level, API prefix, CORS origins, database URL, pool, timeout,
  and embedding dimension.
- PostgreSQL with the pgvector extension, accessed through SQLAlchemy 2.0 and
  Psycopg 3, with Alembic migrations.
- Document lifecycle foundation: documents, versions, chunks, embedding sets,
  and embeddings, with candidate/approved/active/superseded states and
  repository-controlled transitions.
- Vendor-neutral embedding and LLM provider protocols, with a Gemini embedding
  provider, a Gemini LLM provider, and deterministic
  test-only implementations behind the same interfaces.
- Semantic retrieval over pgvector using cosine distance, filtered by tenant,
  active document version, active embedding set, model, and dimension, with
  deterministic ordering for ties.
- Grounded HR RAG service: bounded prompt context, a grounding system prompt
  that treats retrieved content as untrusted evidence rather than instructions,
  citation validation that rejects any source the answer invented, and an
  explicit insufficient-evidence outcome.
- Stable, non-revealing API error contract — internal exceptions, provider
  messages, and stack traces are never returned to clients.
- Structured JSON-compatible logging and request correlation IDs
  (`X-Correlation-ID` on every response).

### Frontend

- React + Vite + TypeScript conversational interface.
- Multi-turn transcript held in browser-session state: earlier questions and
  answers stay visible instead of being replaced.
- Assistant header stays fixed while the transcript scrolls, with the composer
  pinned at the bottom.
- Enter sends, Shift+Enter inserts a newline, and the view auto-scrolls to the
  newest turn.
- Per-answer collapsible **Sources** control, collapsed by default.
- Typed API client with runtime validation of every response field, including
  each citation object.
- Dedicated insufficient-evidence state, visually distinct from an error.
- Dedicated rate-limit message for `429`, distinct from a generic failure.
- Safe error states — no raw backend exception text or internal detail is shown.

### Citations and Sources

Citation data is fully preserved end to end. The backend still validates every
citation the model claims, and the API response still carries the complete
citation objects.

What changed is presentation only: the internal markers (`[S1]`, `[S2]`) are
hidden from the visible answer text so it reads naturally, and the supporting
detail — source title, section or heading path, and document identifier — is
available under the **Sources** control on that specific answer. Nothing was
removed from the data model or from the grounding checks.

### Evaluation and Testing

- Synthetic HR evaluation corpus of four documents and twelve questions.
- Evidence-aware retrieval evaluation that distinguishes the correct document
  with the correct evidence chunk, the correct document with the wrong chunk,
  and a wrong document, reported as Hit@1 / Hit@3 / Hit@5.
- Structural grounding checks covering citation validity and correct
  insufficient-evidence behaviour.
- Deterministic unit and integration test suites, with database integration
  tests running against real PostgreSQL and pgvector rather than a substitute.
- Frontend tests with Vitest and Testing Library.
- Manual smoke scripts for the Gemini LLM and embedding providers, and a
  manual evaluation runner.

### Engineering and Safety

- Strict typing (`mypy --strict`) and linting (Ruff for the backend, oxlint
  for the frontend). See [Quality Checks](#quality-checks) for exactly which
  checks run in CI, which run at deploy time, and which are local only.
- Continuous delivery on merge to `main`: the backend image is built and pushed
  to ECR, a new ECS task definition revision is registered with only the
  container image changed, the service is updated and waited on for stability,
  and the frontend bundle is built, synced to S3, and followed by a CloudFront
  invalidation.
- GitHub Actions authenticates to AWS with an OIDC-federated IAM role. No
  long-lived AWS access keys are stored as repository secrets.
- Secrets handled as `SecretStr`; database credentials and query parameters are
  kept out of logs.
- Synthetic-only HR content, with tests that guard the data boundary.
- Explicit CORS allowlist; wildcard origins are rejected by configuration
  validation.
- Governance documents: [LICENSE](LICENSE), [SECURITY.md](SECURITY.md),
  [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md),
  and [AI_USAGE.md](AI_USAGE.md).

## Architecture

### Application architecture

```
React/Vite frontend
        |
        v
   FastAPI API
        |
        v
  HR RAG service
   |          |
   v          v
  Gemini   PostgreSQL
   LLM     + pgvector
             |
             v
       approved synthetic
          HR chunks
```

OIAP is a **modular monolith**. The API layer owns HTTP concerns only;
retrieval, prompting, grounding, and citation decisions live in the service
layer; persistence sits behind repository contracts; and embedding and LLM
access sits behind provider protocols, so a vendor can be replaced without
touching business logic.

There are no microservices, no message bus, and no service mesh, and none are
planned for this phase.

### AWS deployment architecture

```
User
  |
  v
CloudFront  (single public entry point, HTTPS)
  |
  |-- default behaviour ----> S3            (static frontend bundle)
  |
  '-- /api/* behaviour -----> ALB
                               |
                               v
                          ECS Fargate       (FastAPI container from ECR)
                               |
              +----------------+----------------+
              v                                 v
     RDS PostgreSQL + pgvector            Gemini API
                                   (generation and embeddings)
```

Serving the UI and the API from one CloudFront distribution keeps the browser
on a single origin, so the frontend needs no cross-origin configuration.

Application secrets are supplied to the ECS task from AWS Secrets Manager and
are never baked into the image or committed to the repository. Container logs go
to CloudWatch as structured JSON, each line carrying the request correlation ID.

Specific AWS resource identifiers — account ID, distribution ID, cluster and
service names, secret ARNs — are deliberately kept out of this README.

## HR RAG API

```
POST /api/v1/hr/ask
```

Request fields:

| Field | Type | Description |
|---|---|---|
| `question` | string | The HR question to answer. Non-empty, length-bounded. |
| `tenant_id` | string | Identifies whose approved HR content to search. |

`tenant_id` is currently supplied by the caller because there is no
authentication layer to derive it from. It is request routing, not
authorization — it does not prove the caller may read that tenant's content.

Response fields:

| Field | Type | Description |
|---|---|---|
| `answer` | string | The grounded answer text, with inline source markers. |
| `citations` | array | The approved sources the answer referenced — business document key, title, heading path, chunk position, and similarity distance. |
| `insufficient_evidence` | boolean | `true` when the approved sources did not support an answer. |

Internal identifiers — chunk, document, version, and embedding-set UUIDs — are
deliberately not exposed. Citations carry the stable business document key
instead.

An insufficient-evidence result is a normal `200` response, not an error.
Failures return a stable status code with a curated message; internal detail is
logged rather than returned.

## Synthetic Evaluation Baseline

The repository includes a reproducible evaluation harness built on a **fully
synthetic** HR corpus:

- **4 synthetic HR documents** — leave, remote work, expenses, and probation.
- **12 evaluation questions** — 9 that should be answerable from a specific
  document, and 3 that should correctly produce an insufficient-evidence
  result.
- **Evidence-aware retrieval scoring** — a question counts as a hit only when
  the expected evidence chunk is retrieved, not merely when some chunk from the
  right document appears. Reported as Hit@1 / Hit@3 / Hit@5.
- **Grounding checks** — that citations are valid and that questions without
  supporting evidence produce the insufficient-evidence outcome.

No evaluation results are committed to this repository. Numbers are produced by
running the harness locally, against either the deterministic providers or the
real Gemini providers.

Any result produced this way is a **synthetic evaluation baseline** only. It
measures behaviour on twelve authored questions over four authored documents.
It is not a measure of production accuracy, and it should not be read as one.

## Technology Stack

| Area | Technologies |
|---|---|
| Language and runtime | Python 3.12 |
| API | FastAPI, Uvicorn, Pydantic, Pydantic Settings |
| Data | PostgreSQL, pgvector, SQLAlchemy 2.0, Psycopg 3, Alembic |
| AI providers | Gemini API — generate content for answers, embeddings for vectors |
| Frontend | React, TypeScript, Vite |
| Backend quality | Pytest, Ruff, MyPy |
| Frontend quality | Vitest, Testing Library, oxlint, TypeScript project builds |
| AWS — delivery | ECR, ECS Fargate, Application Load Balancer |
| AWS — edge and storage | CloudFront, S3 |
| AWS — data and platform | RDS for PostgreSQL (pgvector), Secrets Manager, CloudWatch |
| CI/CD | GitHub Actions with OIDC-federated AWS access |

## Repository Structure

```
app/           FastAPI application: api, core, domain, models,
               repositories, schemas, services, providers, evaluation
frontend/      React + Vite + TypeScript interface and its tests
migrations/    Alembic environment and versioned migrations
scripts/       Manual smoke tests and the evaluation runner
tests/         Unit tests and PostgreSQL integration tests
docs/          Architecture, ADRs, framework, implementation,
               and synthetic-data policy documents
docs/images/   Screenshots used by this README
.github/       ci.yml (pull-request checks) and cd.yml (production delivery)
```

`Dockerfile` and `.dockerignore` at the repository root build the backend image
that CD pushes to ECR.

## Local Setup

Commands below are for Linux or WSL, run from the repository root.

### Backend

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
```

Edit `.env` for local development: set `DB_HOST`, `DB_PORT`, `DB_NAME`,
`DB_USER`, and `DB_PASSWORD` for your local database and, if you intend to use
the real providers, set `GEMINI_API_KEY`. Never commit `.env`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
```

`VITE_API_BASE_URL` defaults to `http://localhost:8000`. Only `VITE_`-prefixed
variables reach the browser bundle, so no secret belongs in that file.

## Local PostgreSQL + pgvector

A disposable local database can be started with Docker:

```bash
docker run --rm --detach --name oiap-postgres-dev \
  --env POSTGRES_USER=oiap \
  --env POSTGRES_PASSWORD=change-me \
  --env POSTGRES_DB=oiap \
  --publish 5432:5432 \
  pgvector/pgvector:pg16
```

- This is for **local development only**.
- `change-me` is a placeholder. Replace it in any environment that persists,
  and keep real credentials out of Git and logs.
- Database integration tests use a separate disposable database configured
  through `TEST_DATABASE_URL`. That suite upgrades and downgrades its target
  database, so it must never point at a shared, development, staging, or
  production database.

## Database Migrations

From the repository root, with the virtual environment active:

```bash
alembic upgrade head
alembic current
```

`alembic downgrade` exists but is destructive: it drops OIAP-owned tables. Use
it only against a disposable local or test database, never against a database
holding data you need. The initial downgrade deliberately retains the shared
PostgreSQL `vector` extension. Re-run `alembic upgrade head` before using
repository operations again.

## Running the Application

Backend, with the virtual environment active:

```bash
python -m uvicorn app.main:app --reload
```

Frontend, in a second terminal:

```bash
cd frontend
npm run dev
```

- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`

The frontend dev server uses port 3000 because the backend CORS allowlist
contains `http://localhost:3000` by default.

Available endpoints:

- `GET /api/v1/health`
- `GET /api/v1/ready`
- `POST /api/v1/hr/ask`

The API accepts a safe `X-Correlation-ID` request header or generates one.
Every response includes it. Correlation IDs support tracing only; they are not
authentication or authorization values.

## API Documentation

FastAPI serves interactive OpenAPI documentation while the backend is running:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI schema: `http://localhost:8000/openapi.json`

## Quality Checks

Backend, from the repository root with the virtual environment active:

```bash
python -m pytest
ruff check .
mypy app
```

Database integration tests require a disposable PostgreSQL database with
pgvector and never substitute SQLite:

```bash
TEST_DATABASE_URL=postgresql+psycopg://oiap:change-me@localhost:5432/oiap_test \
  python -m pytest tests/integration/database
```

Frontend, from the `frontend/` directory:

```bash
npm test
npm run lint
npm run typecheck
npm run build
```

### What runs where

| Check | Pull request CI | Deploy (merge to `main`) | Local |
|---|---|---|---|
| `ruff check .` | yes | — | yes |
| `mypy app` | yes | — | yes |
| `pytest` (non-database) | yes | — | yes |
| `pytest` (full, PostgreSQL + pgvector) | yes, for PRs targeting `main` | — | yes |
| `tsc -b` (frontend types) | — | yes, via `npm run build` | yes |
| `npm run build` | — | yes | yes |
| `oxlint` | — | — | yes |
| `npm test` (Vitest) | — | — | yes |

Backend CI runs on pull requests to `dev` and `main`. The frontend is type
checked and built during deployment, so a type error or a broken build blocks a
release — but **frontend linting and unit tests are not yet wired into any
workflow** and must be run locally before opening a pull request. Adding a
frontend CI job is the next obvious gap to close.

Latest local frontend run: `oxlint` 0 warnings and 0 errors, `tsc -b` passing,
25 Vitest tests passing, and a successful production build.

## Configuration

Backend settings are read from the environment, or from `.env` in local
development. All values are validated at application startup; invalid values
fail with a clear error.

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `office-intelligence-automation-platform-oiap` | Application name reported by the API |
| `APP_ENV` | `development` | One of `development`, `test`, `staging`, `production` |
| `APP_VERSION` | `0.1.0` | Semantic version string |
| `LOG_LEVEL` | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `API_PREFIX` | `/api/v1` | Absolute, normalized API path prefix |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON array of explicit browser origins; wildcards are rejected |
| `DB_HOST` | `localhost` | Database host; the RDS endpoint in a deployed environment |
| `DB_PORT` | `5432` | Database port, 1–65535 |
| `DB_NAME` | `oiap` | Database name |
| `DB_USER` | `oiap` | Database user |
| `DB_PASSWORD` | local placeholder | Database password; handled as a secret |
| `DATABASE_POOL_SIZE` | `5` | Connection pool size, 1–50 |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | `5` | Connection timeout in seconds, 1–60 |
| `AUTO_ACTIVATE_UPLOADS` | `true` in development/test; `false` otherwise | Automatically approves and activates completed uploads; can be explicitly overridden |
| `EMBEDDING_DIMENSION` | `768` | Embedding dimension enforced against each embedding set |
| `RATE_LIMIT_REQUESTS` | `5` | Requests allowed per client per window on `/hr/ask`, 1–10000 |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window length in seconds, 1–3600 |
| `RATE_LIMIT_TRUSTED_PROXY_HOPS` | `1` | Proxies appending to `X-Forwarded-For` in front of the app (CloudFront + ALB = 1) |
| `GEMINI_API_KEY` | unset | Required only for the real Gemini providers; handled as a secret |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model used for grounded generation |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Model used for embeddings |
| `SMTP_HOST` | `smtp.gmail.com` | Gmail SMTP host for OTP mail |
| `SMTP_PORT` | `587` | Gmail submission port |
| `SMTP_USE_TLS` | `true` | STARTTLS before login |
| `SMTP_USERNAME` | unset | Gmail address used to authenticate SMTP |
| `SMTP_PASSWORD` | unset | Gmail App Password; handled as a secret |
| `SMTP_FROM` | unset | From address on OTP messages; defaults to `SMTP_USERNAME` |

Frontend configuration:

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Base URL of the backend API |

The application builds the `postgresql+psycopg://` SQLAlchemy URL from the five
`DB_*` values, so no complete connection string is configured or stored. This
lets a deployment inject `DB_USER` and `DB_PASSWORD` straight from a managed
secret without assembling a URL by hand.

**`GEMINI_API_KEY` and `SMTP_PASSWORD` must never be committed.** They are
supplied through the environment and held as secret values in configuration.
`.env.example` contains placeholders only; `.env` is ignored by Git and must
stay that way. Gmail SMTP needs a Google App Password, not the account
password. When SMTP credentials are present, signup and login email the OTP and
the API does not return the code. When they are absent and `APP_ENV` is
`development` or `test`, the code is returned so local work can continue.

Note: `.env.example` also lists `GEMINI_MAX_OUTPUT_TOKENS`, and
`TEST_DATABASE_URL` is read directly by the database test fixtures.
`GEMINI_MAX_OUTPUT_TOKENS` is **not** currently read by application settings,
so setting it has no effect; it is a known cleanup item rather than active
configuration.

## Current Limitations

This section is intentionally direct. OIAP is a deployed **demonstration**, not
an enterprise production system, and the list below is the honest reason why.

- **Demonstration-grade authentication.** Signup is email plus password. Login
  checks the password, then emails a Gmail OTP as 2FA. Sessions are bearer
  tokens on `/hr/ask` and profile routes. This is not SSO, not hardware 2FA,
  and not an enterprise identity provider.
- **`tenant_id` is request-supplied.** The caller states which tenant's content
  to search, and nothing verifies that claim.
- **No production tenant enforcement.** Tenant isolation is a query filter, not
  a security boundary backed by an authenticated identity.
- **Rate limiting is in-process only.** `/hr/ask` allows 5 requests per client
  per minute, but the counters live in each application instance, so N running
  tasks permit N times that rate and every deployment resets the windows. It is
  a cost control against casual abuse and runaway clients, not a distributed
  production limiter; that needs shared storage or an edge WAF rate rule. There
  is still no spend quota on the Gemini account itself.
- **No authorisation.** There are no roles, permissions, or per-document access
  rules. Any signed-in account can query the whole synthetic corpus.
- **Conversation lives in the browser only.** The transcript is React state for
  the current session. It is lost on refresh, is not stored server-side, and is
  never sent back to the API — each question is answered independently, with no
  model memory of earlier turns.
- **Synthetic HR data only.** Every document is authored demonstration content.
  No real company, employee, or customer information is present, and none
  belongs in this repository.
- **Portfolio-scale deployment.** It is sized and configured to demonstrate the
  architecture, not to meet production availability, capacity, backup, or
  incident-response expectations.
- **No ANN vector index yet.** Retrieval performs an exact scan, which is
  correct but does not scale to large corpora.
- **`/ready` is configuration-level only.** It confirms that application
  configuration loaded; it is not a full dependency readiness probe and makes no
  database, vector-store, or provider health claim.
- **LangGraph orchestration is not implemented.**
- **MCP integration is not implemented.**
- **Human-in-the-loop approval workflows are not implemented.**
- **Demo-mode uploads are auto-activated.** This bypasses the human-approval
  step; keep `AUTO_ACTIVATE_UPLOADS=false` when that behavior is not appropriate.
- **Document ingestion from real PDFs is not implemented.** The corpus is
  authored synthetic content.

## Roadmap

Delivered:

1. Public, recruiter-ready repository.
2. AWS deployment.
3. CI/CD continuous deployment.
4. Public-demo rate limiting.
5. Conversational chat interface.

Planned, without committed dates:

6. Frontend CI job covering lint and unit tests.
7. Authentication and enforced tenant isolation.
8. Shared or edge-level rate limiting, plus a Gemini spend quota.
9. LangGraph orchestration.
10. MCP integration.
11. Human-in-the-loop approval workflows.
12. Broader office automation modules.

## Data and Security

All HR content in this repository is **synthetic and clearly labelled as such**.
No real company, employee, customer, confidential, or credential data belongs
in this repository, in any form — including tests, fixtures, examples, and
screenshots.

Real company documents are a later, controlled replacement rather than a
parallel development source. They would have to pass extraction, human review
and correction, metadata and version checks, sensitive-data and redaction
checks, standardized-Markdown conversion, and explicit human approval before
entering retrieval. Raw documents must never be sent directly to embeddings.

- Vulnerability reporting and security expectations: [SECURITY.md](SECURITY.md)
- Synthetic-data rules: [docs/synthetic-data-policy.md](docs/synthetic-data-policy.md)
- No secrets, credentials, keys, or tokens are committed to Git; configuration
  is supplied through the environment.

## AI Usage

AI tools were used selectively during development, with maintainer review and
validation of AI-assisted changes before acceptance. See
[AI_USAGE.md](AI_USAGE.md) for what was used, where, and the standards
applied.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch flow, quality
requirements, pull request expectations, and data rules. Participation is
subject to the [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Documentation

Current design and policy references:

- [Synthetic-data policy](docs/synthetic-data-policy.md)
- [ADR-001: PostgreSQL with pgvector as the initial vector store](docs/decisions/ADR-001-vector-database.md)
- [ADR-002: HR-first document automation and knowledge agent](docs/decisions/ADR-002-hr-first-document-automation.md)

Earlier **planning and reference** documents, written before the current
implementation existed. They record intended design and sequencing, and should
be read as planning material rather than as a description of what the code does
today:

- [System architecture](docs/architecture/system-architecture.md)
- [MVP architecture](docs/architecture/mvp-architecture.md)
- [Phase 1: HR document automation](docs/architecture/hr-document-automation-phase1.md)
- [MVP implementation plan](docs/implementation/mvp-implementation-plan.md)
- [Framework application plan](docs/framework/framework-application-plan.md)

Where a planning document and this README disagree, this README and the code
are authoritative.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
