# FinPulse

AI-powered financial intelligence for individuals and small businesses with thin or no credit
history.

> Can we understand whether a financially thin-file person or business is financially
> trustworthy, and detect if their financial health is deteriorating before a traditional credit
> system would?

**Status: deterministic core, AI agent layer and frontend built.** The platform foundation is in place,
along with:

- a deterministic synthetic-data layer: six fictional entities, led by the demo business
  **Sharma Electricals** — see the [demo guide](docs/DEMO.md);
- an analytics engine with 25 financial metrics;
- the **Financial Passport**: six dimensions and a prototype Financial Health score;
- the **early-warning engine**: 19 configurable rules that detect deterioration;
- the **stress-testing engine**: cash projections under ten scenarios;
- the **AI agent layer**: seven Claude agents that interpret those verified results, every
  claim cited and every number checked by a deterministic verifier;
- the **frontend** (`apps/web`): a risk-intelligence workspace with seven views per entity,
  all reading the live API:
  - Overview
  - Financial Passport
  - Early Warning Center
  - Financial Health
  - Stress Test
  - AI Investigation, which shows the agent pipeline live
  - Evidence, which traces any AI claim to the metrics and records behind it

The agents need an `ANTHROPIC_API_KEY`; everything else runs without one. Plan and progress:
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
scripts/              dev helpers (run API + web together, db init/seed/reset)
docs/                 SYNTHETIC_DATA.md · FINANCIAL_METRICS.md · FINANCIAL_PASSPORT.md ·
                      EARLY_WARNING.md · STRESS_TESTING.md · AI_AGENTS.md · INVESTIGATIONS.md · DEMO.md
```

Details: [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

## Prerequisites

- Node.js ≥ 22.12 and npm (see `.nvmrc`)
- [uv](https://docs.astral.sh/uv/) (installs a suitable Python for you if needed)
- PostgreSQL 15+: Docker (`make db-up`), a local install, or a Supabase project

## Quick start

**One command (Windows, macOS, Linux):**

```bash
npm run demo
```

It checks Node and uv, creates `.env` from `.env.example` if missing, and installs dependencies.
It then applies migrations, starting the Docker database if PostgreSQL isn't reachable, seeds the
demo data, and starts the API and web app. Open **http://localhost:3000/demo**. You need Node.js
≥ 22.12, [uv](https://docs.astral.sh/uv/), and either Docker Desktop or a PostgreSQL database
in `DATABASE_URL`.

Install uv on Windows (PowerShell), then open a new terminal:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Step by step (with `make`):**

```bash
cp .env.example .env     # one config file for both apps; edit DATABASE_URL if needed
make setup               # uv sync + npm install
make db-up               # optional: local Postgres in Docker (matches .env.example)
make db-init             # create the database if missing + apply migrations
make db-seed             # load the synthetic entities (idempotent)
make dev                 # API on http://127.0.0.1:8000, web on http://localhost:3000
```

## The demo

Open **http://localhost:3000/demo**: Sharma Electricals, a small business with limited credit
history that looks healthy — revenue growing, every bill paid — while its receivables, collection
time and dependence on one builder rise and its cash drains. FinPulse rates it **medium** risk,
led by **Liquidity deterioration**; a 60-day payment delay by its largest customer takes its
six-month outlook from low to high risk; the AI investigation (runnable without an API key in a
clearly labelled, verified demo-script mode) explains why and the red team argues the other side.

`make demo-reset` (or the **Reset demo** button) restores the exact demo state at any time. The
script, the expected figures and how the AI part works: [docs/DEMO.md](docs/DEMO.md).

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

## Security

[SECURITY.md](SECURITY.md) covers the security architecture. In short:

- the API needs an API key (`finpulse auth new-key`), with viewer, analyst and admin roles, and
  data is isolated per organisation;
- financial data is integrity-checked before analysis;
- text from the data is neutralised before any agent reads it;
- the verifier rejects invented numbers and any lending-decision language;
- AI output can never write financial records;
- every AI investigation leaves an append-only, hash-chained audit trail
  (`GET /api/v1/investigations/{id}/audit`, `finpulse audit verify`).

Without `API_KEYS`, authentication is off; that is allowed only for local development.

## Everyday commands

| Task | Command |
|---|---|
| Run everything / one side | `make dev` · `make dev-api` · `make dev-web` |
| Lint · format · type-check | `make lint` · `make format` · `make typecheck` |
| Tests | `make test` (database tests run when `TEST_DATABASE_URL` is set) |
| Production build of web | `make build` |
| All CI checks | `make check` |
| Apply migrations | `make migrate` |
| Database: create + migrate / load data / start over | `make db-init` · `make db-seed` · `make db-reset` |
| Restore the exact demo state (re-seed, clear investigations) | `make demo-reset` |
| Inspect a scenario without a database | `cd apps/api && uv run finpulse synthetic summary sharma_electricals` |
| Regenerate API contract | `make contracts` (after changing any backend schema) |

Without `make`, every target is a one-line command — see the [Makefile](Makefile).

## Synthetic data

Six fictional entities, generated by a seeded day-by-day simulation in Python (no LLM involved):

| Entity | Archetype |
|---|---|
| **Sharma Electricals** (primary demo, 18 months) | Strained MSME: growing, but funding its largest customer out of its own cash; thin credit history |
| Mehra Lighting & Electricals | Deteriorating MSME: collapses from Nov 2025 while its credit-bureau record stays clean |
| Kaveri Packaging Solutions | Healthy MSME |
| Annapurna Home Kitchen | Thin-file but healthy MSME (no credit history at all) |
| Rapid Mobile Hub | High-risk MSME |
| Ananya Rao | Freelancer / independent professional |

Each has bank transactions, invoices and receivables, bills and payables, customers, suppliers,
loans with repayment schedules, and cash balances that reconcile with one another, plus ground
truth and a simulated bureau record for evaluation. See
[docs/SYNTHETIC_DATA.md](docs/SYNTHETIC_DATA.md) for the structure, the guarantees, and how to add
scenarios.

## Financial analytics

```
GET /api/v1/entities
GET /api/v1/entities/{entity_id}/financial-metrics[?as_of=YYYY-MM-DD]
GET /api/v1/entities/{entity_id}/financial-metrics/{metric_code}
GET /api/v1/meta/financial-metrics
```

Twenty-five metrics, from monthly revenue and cash runway to receivable days, debt-service burden and
payment consistency. Each comes with its value, unit, period, availability, confidence, method,
breakdown and source records. All are calculated in plain Python (no LLM) and covered by
hand-checked tests. See [docs/FINANCIAL_METRICS.md](docs/FINANCIAL_METRICS.md).

## Financial Passport

> A prototype multidimensional financial-health profile on synthetic data — **not a credit
> score**, not a credit-bureau product, and not for lending decisions.

```
GET /api/v1/entities/{entity_id}/passport[?as_of=YYYY-MM-DD]
GET /api/v1/entities/{entity_id}/passport/history[?months=12]
GET /api/v1/meta/passport-model
```

```
Sharma Electricals, 30 Sep 2026 — Financial Health 79.0/100 (Sound)
  Cash-Flow Stability 49.5 · Repayment Capacity 99.4 · Revenue Stability 79.8
  Financial Resilience 65.3 · Debt Health 99.6 · Transaction Consistency 92.5
  (was 75.1, Sound, on 31 Oct 2025)
```

Scores come from a versioned TOML configuration, applied deterministically. Every point traces
to a metric, changes are attributed to the factors that moved, and history is tracked month by
month. See [docs/FINANCIAL_PASSPORT.md](docs/FINANCIAL_PASSPORT.md).

## Early warnings

> Deterministic rules on synthetic data. Warnings flag changes to investigate; they are not
> predictions or a credit assessment.

```
GET /api/v1/entities/{entity_id}/warnings[?as_of=&min_severity=&category=]
GET /api/v1/entities/{entity_id}/risk-summary[?as_of=]
GET /api/v1/meta/early-warning-rules
```

Eighteen rules compare each entity with its own earlier state. They cover:

- revenue decline and accelerating expenses;
- falling cash, overdraft reliance, liquidity and runway;
- receivables growth, collection days and late payments;
- debt burden, loan stacking and bounced instalments;
- customer and supplier concentration, and loss of a major customer;
- unusual transactions and volatility.

Every threshold is in one TOML file. No LLM decides whether a warning exists.

```
EARLY WARNING — MEDIUM   Sharma Electricals, 30 Sep 2026
Liquidity deterioration.
Over 3 months the average cash balance fell from ₹8,13,593 to ₹6,98,191 while receivables rose
from ₹10,18,669 to ₹14,82,538: ₹5,79,271 (0.45 months of revenue) has moved out of the bank into
unpaid invoices. Collection time went from 36 to 46 days. 25% of receivables are overdue. The
liquidity ratio (1.33×) counts receivables as liquid, so it does not show this.
```

Sharma's revenue is still growing and every obligation is paid on time; the warning comes before
anything has gone wrong. Mehra Lighting & Electricals, the collapse story, reaches **high** risk in
Dec 2025, a month after its hidden decline begins and 8–9 months before its loan auto-debits
bounce, while its credit-bureau record stays clean. See [docs/EARLY_WARNING.md](docs/EARLY_WARNING.md).

## Stress testing

> Hypothetical scenarios on synthetic data, not forecasts.

```
POST /api/v1/entities/{entity_id}/stress-test     {"preset": "revenue_down_20"} or {"shocks": [...]}
GET  /api/v1/meta/stress-scenarios
```

Ten presets: revenue −10/20/30%, the largest customer stops paying for 30/60/90 days, operating
costs +15%, new debt, interest rates +300 bps and the largest supplier +10%. Custom shocks can be
combined. Each run projects the baseline and the scenario month by month, with the actual loan
schedules and overdraft. It reports revenue, expenses, cash flow, cash balance, liquidity, runway,
the Financial Health impact, the risk level and the failure point, with numbered evidence.

```
Sharma Electricals, largest customer delays payment by 60 days, 6 months from 30 Sep 2026
  Shree Ganesh Builders pays nothing for 60 days: ₹9,25,725 withheld, received in Dec 2026
  Risk: Low → High · lowest cash ₹5,52,062 → −₹2,50,470 (Nov 2026) · Health 77.7 → 76.2
```

See [docs/STRESS_TESTING.md](docs/STRESS_TESTING.md) for the methodology and how to add scenarios.

## AI agents

> AI interpretation of deterministic results. Agents never calculate; every number they state
> must appear in the evidence they cite.

```
GET  /api/v1/entities/{entity_id}/evidence-pack      what the agents may use (no AI)
POST /api/v1/entities/{entity_id}/investigate        full investigation → structured record
GET  /api/v1/investigations[/{id}[/events]]          inspect recent investigations
POST /api/v1/entities/{entity_id}/agents/{agent}     one agent (+ its dependencies)
```

There are seven agents:

- **Financial Profile**, **Credit Intelligence**, **Early Warning Investigation**, **Risk
  Investigation** and **Stress-Test Interpretation** run in parallel.
- A **Red Team** then challenges their verified conclusions.
- A **Senior Financial Intelligence** agent writes the final report. It separates **FACT**,
  **CALCULATED METRIC**, **FORECAST**, **ASSUMPTION** and **AI INTERPRETATION**, and cites
  evidence ids for every claim.

A deterministic verifier checks every claim's citations, type and numbers. Arithmetic such as a
difference of two cited figures is rejected. A failing claim is sent back for repair, then
dropped. Set `ANTHROPIC_API_KEY` (model `claude-opus-5-5` by default) to enable them. See
[docs/AI_AGENTS.md](docs/AI_AGENTS.md).

**Investigations** orchestrate the full workflow, in this order:

1. data;
2. analytics;
3. the Financial Passport;
4. early warnings;
5. stress tests;
6. evidence assembly;
7. the specialist agents;
8. disagreement detection;
9. mandatory red-team review of significant risk assessments;
10. the senior synthesis;
11. the final assessment.

The result is one record with the triggered warnings, the metrics used, each agent's analysis,
the red-team findings, the final assessment, recommendations, confidence, timestamps and a full
event log. `uv run finpulse investigate show FILE --events` prints it for a demo. See
[docs/INVESTIGATIONS.md](docs/INVESTIGATIONS.md).

## How the frontend talks to the backend

1. FastAPI generates an OpenAPI document from its Pydantic models.
2. `npm run contracts:generate` exports it to `packages/contracts/openapi.json` and generates
   `packages/contracts/src/schema.gen.ts` with `openapi-typescript`. CI fails if these are stale.
3. `apps/web/src/lib/api` wraps `openapi-fetch` with those types, so request paths, parameters
   and response shapes are type-checked against the backend.
4. Server Components use `getServerApiClient()` (base URL `FINPULSE_API_URL`, never cached,
   sends the server-only `FINPULSE_API_KEY`). Client Components use `getBrowserApiClient()`,
   which calls this app's same-origin proxy (`/api/finpulse/...`). The proxy forwards only an
   allow-listed set of requests and adds the key, so the browser never holds one.
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
| [SECURITY.md](SECURITY.md) | Security and reliability architecture, AI guarantees, audit trail, residual risks |
