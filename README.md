# FinPulse

AI-powered financial intelligence for individuals and small businesses with thin or no credit
history.

> Can we understand whether a financially thin-file person or business is financially
> trustworthy, and detect if their financial health is deteriorating before a traditional credit
> system would?

**Status: Phase 0 (foundations).** The monorepo, backend skeleton, database layer, shared API
contract and web shell are in place. No financial analytics, scoring or AI agents exist yet — see
[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md).

## Core principle

Python performs deterministic financial calculations. AI agents investigate, reason, challenge and
explain those calculations. The LLM never invents financial metrics and is never the source of
truth — every number an agent states is checked against persisted, versioned engine output by a
deterministic verifier.

## Repository layout

```
apps/api/             FastAPI backend (Python 3.12+, uv)           → apps/api/README.md
apps/web/             Next.js frontend (TypeScript, Tailwind, shadcn/ui)
packages/contracts/   Shared API contract: OpenAPI exported from FastAPI + generated TS types
infra/                docker-compose for local PostgreSQL
scripts/              dev helpers (run API + web together)
```

Details: [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

## Prerequisites

- Node.js ≥ 22.12 and npm (see `.nvmrc`)
- [uv](https://docs.astral.sh/uv/) (installs a suitable Python for you if needed)
- PostgreSQL 15+: Docker (`make db-up`), a local install, or a Supabase project

## Quick start

```bash
cp .env.example .env     # one config file for both apps; edit DATABASE_URL if needed
make setup               # uv sync + npm install
make db-up               # optional: local Postgres in Docker (matches .env.example)
make dev                 # API on http://127.0.0.1:8000, web on http://localhost:3000
```

Open http://localhost:3000. The overview page shows three live checks:

| Card | Path it proves |
|---|---|
| Backend API | Next.js server → FastAPI `GET /health` |
| Database | FastAPI → PostgreSQL, via `GET /ready` |
| Browser connection | Your browser → FastAPI directly (exercises CORS) |

The API's interactive docs are at http://127.0.0.1:8000/docs (disabled in production).
Without a database the API still starts: `/health` is OK and `/ready` reports `not_ready` (503).

## Configuration

All configuration is environment variables, documented in [`.env.example`](.env.example). Both
apps read the repository-root `.env` (git-ignored); real environment variables take precedence.
No secrets are committed and none have defaults. A Supabase connection string can be pasted into
`DATABASE_URL` unchanged.

## Everyday commands

| Task | Command |
|---|---|
| Run everything / one side | `make dev` · `make dev-api` · `make dev-web` |
| Lint · format · type-check | `make lint` · `make format` · `make typecheck` |
| Tests | `make test` (database tests run when `TEST_DATABASE_URL` is set) |
| Production build of web | `make build` |
| All CI checks | `make check` |
| Apply migrations | `make migrate` |
| Regenerate API contract | `make contracts` (after changing any backend schema) |

Without `make`, every target is a one-line command — see the [Makefile](Makefile).

## How the frontend talks to the backend

1. FastAPI generates an OpenAPI document from its Pydantic models.
2. `npm run contracts:generate` exports it to `packages/contracts/openapi.json` and generates
   `packages/contracts/src/schema.gen.ts` with `openapi-typescript`. CI fails if these are stale.
3. `apps/web/src/lib/api` wraps `openapi-fetch` with those types, so request paths, parameters
   and response shapes are type-checked against the backend.
4. Server Components use `getServerApiClient()` (base URL `FINPULSE_API_URL`, never cached).
   Client Components use `getBrowserApiClient()` (base URL `NEXT_PUBLIC_API_URL`, needs CORS).
5. Errors arrive as RFC 7807 `application/problem+json` and become a typed `ApiError`; network
   failures and timeouts become an `ApiError` with `status: 0`. Every response carries
   `X-Request-ID`, which also appears on the matching API log lines.

## Design documents

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design: engines, agents, orchestration, errors, logging, testing |
| [DATA_MODEL.md](DATA_MODEL.md) | PostgreSQL schema (Supabase-compatible), lineage, versioning |
| [API_SPEC.md](API_SPEC.md) | REST API contract and agent tool contract |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Monorepo layout and module boundaries |
| [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) | Phased build plan with exit criteria |
