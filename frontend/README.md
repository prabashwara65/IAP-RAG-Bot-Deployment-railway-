# OIAP HR Assistant frontend

A minimal React + Vite + TypeScript interface for the OIAP grounded HR answer
endpoint. It proves one flow end to end: ask a question, see a grounded answer
with its approved sources, and get a clear state when evidence is missing or
the backend is unavailable.

## Prerequisites

The OIAP FastAPI backend must be running and reachable. From the repository
root:

```bash
uvicorn app.main:app --reload --port 8000
```

## Running

```bash
cd frontend
npm install
npm run dev
```

The dev server binds to <http://localhost:3000> because that is the origin in
the backend CORS allowlist. The port is pinned with `strictPort`, so a clash
fails loudly instead of silently moving to an origin the backend would reject.

## Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Dev server on port 3000 |
| `npm run build` | Type-check and produce a production bundle in `dist/` |
| `npm run preview` | Serve the production bundle on port 3000 |
| `npm run typecheck` | Strict TypeScript project check |
| `npm run lint` | oxlint |
| `npm run test` | Vitest unit and component tests |
| `npm run test:watch` | Vitest in watch mode |

## Configuration

Copy `.env.example` to `.env.local` to point at a different backend:

```bash
cp .env.example .env.local
```

`VITE_API_BASE_URL` defaults to `http://localhost:8000`. Only `VITE_`-prefixed
variables are exposed to the browser bundle, so never put a secret in them.

## Scope

This is a single-page MVP. The tenant ID field is temporary internal routing
for local development; it is not sign-in and grants no access rights. There is
no authentication, document management, or chat history in this branch.
