# FinPulse — Project Structure

> Status: **design, not implemented.** Target repository layout. Directories are created as the
> phases in `DEVELOPMENT_PLAN.md` reach them — no empty placeholder modules are committed.

## 1. Monorepo layout

```
finpulse/
├── README.md
├── ARCHITECTURE.md · DATA_MODEL.md · API_SPEC.md · PROJECT_STRUCTURE.md · DEVELOPMENT_PLAN.md
├── docs/
│   ├── adr/                      # one file per architecture decision (0001-custom-orchestration.md …)
│   └── methodology/              # generated from the registries (metrics, scoring, rules, scenarios)
├── contracts/
│   └── openapi.json              # exported from FastAPI; source for frontend types
├── apps/
│   ├── api/                      # Python backend + worker (one package, two entrypoints)
│   └── web/                      # Next.js frontend
├── infra/
│   ├── docker-compose.yml        # postgres, api, worker, web
│   └── postgres/init.sql         # pgcrypto; local roles
├── scripts/                      # dev tasks: export-openapi, gen-types, seed-demo-cohort
├── .github/workflows/ci.yml
├── .env.example
└── Makefile                      # one-word entrypoints: make dev / test / lint / gen
```

## 2. Backend — `apps/api`

```
apps/api/
├── pyproject.toml                # uv-managed; ruff, mypy, pytest config
├── alembic.ini
├── alembic/versions/
├── src/finpulse/
│   ├── main.py                   # FastAPI app factory (create_app)
│   ├── worker.py                 # job worker entrypoint
│   ├── config.py                 # Pydantic Settings
│   │
│   ├── core/                     # shared, dependency-free
│   │   ├── errors.py             # domain error taxonomy (→ problem+json in api/)
│   │   ├── money.py              # Money (minor units), rounding rules
│   │   ├── time.py               # Period, Window, month arithmetic — no clock access
│   │   ├── ids.py
│   │   └── types.py              # enums: SubjectKind, Severity, Direction, …
│   │
│   ├── domain/                   # in-memory domain objects consumed by engines
│   │   ├── ledger.py             # Transaction, Account, Counterparty, Ledger
│   │   ├── series.py             # RecurringSeries, ObligationEvent
│   │   └── results.py            # MetricResult, PassportResult, Signal, StressResult
│   │
│   ├── synthetic/                # PURE: seeded generator
│   │   ├── personas/             # one module per persona (gig_worker.py, kirana_store.py, …)
│   │   ├── components/           # income streams, spending, obligations, shocks
│   │   ├── deterioration.py      # mechanisms: income_loss, loan_stacking, customer_loss, …
│   │   ├── bureau.py             # simulated bureau event model (evaluation only)
│   │   └── generator.py          # generate(persona, seed, params) → GeneratedDataset
│   │
│   ├── ingestion/                # PURE: raw → normalised ledger
│   │   ├── validate.py
│   │   ├── counterparties.py
│   │   ├── categorise.py         # rule tables in categorise_rules.yaml
│   │   ├── transfers.py
│   │   └── recurring.py          # series detection + obligation events
│   │
│   ├── analytics/                # PURE: metric registry and metrics
│   │   ├── registry.py           # @metric decorator, MetricContext, catalogue
│   │   ├── stats.py              # robust stats helpers (median/MAD, Theil–Sen, CV, HHI)
│   │   └── metrics/
│   │       ├── income.py · cashflow.py · liquidity.py · obligations.py
│   │       ├── spending.py · business.py · trend.py · data_quality.py
│   │
│   ├── scoring/                  # PURE: Financial Passport
│   │   ├── models/passport_v1.yaml
│   │   ├── model.py              # load + validate model file
│   │   ├── transforms.py         # piecewise-linear curves
│   │   ├── passport.py           # score(metric_results, stress_results, model) → PassportResult
│   │   └── reason_codes.py
│   │
│   ├── early_warning/            # PURE
│   │   ├── rules/                # one module per rule family
│   │   ├── detectors/            # cusum.py, robust_z.py, slope_change.py
│   │   ├── engine.py             # detect(...) → list[Signal]
│   │   ├── alerts.py             # lifecycle transitions (pure state machine)
│   │   ├── deterioration_index.py
│   │   └── backtest.py           # replay + lead-time metrics
│   │
│   ├── stress/                   # PURE
│   │   ├── scenarios/            # one module per scenario + params schema
│   │   ├── projection.py         # baseline projection
│   │   ├── simulator.py          # seeded Monte Carlo
│   │   └── engine.py             # run(baseline, scenario, params, seed) → StressResult
│   │
│   ├── evidence/                 # PURE: evidence pack builder (canonical JSON + hash)
│   │   └── pack.py
│   │
│   ├── verification/             # PURE: deterministic grounding verifier
│   │   ├── numbers.py            # numeric token extraction & normalisation
│   │   ├── checks.py             # evidence_exists, scope, numeric_match, direction, caveats
│   │   └── verifier.py
│   │
│   ├── llm/                      # provider abstraction
│   │   ├── client.py             # LLMClient protocol, LLMResponse, errors
│   │   ├── provider.py           # production adapter (configurable provider/model)
│   │   ├── replay.py             # record/replay adapter for tests
│   │   └── retry.py
│   │
│   ├── agents/
│   │   ├── schemas.py            # Claim, Findings, DraftReport, Challenges, Rebuttal
│   │   ├── specs.py              # AgentSpec registry (role, prompt, tools, output schema, budget)
│   │   ├── runner.py             # tool-use loop, repair attempt, budget enforcement
│   │   ├── prompts/<agent>/v1.md
│   │   └── tools/                # read-only tools; each = args model + handler + scope guard
│   │
│   ├── orchestration/
│   │   ├── workflow.py           # Phase/StepSpec definitions; investigation_v1
│   │   ├── executor.py           # runs phases, persists boundaries, resumes, emits events
│   │   └── budgets.py
│   │
│   ├── services/                 # use cases; own DB transactions; enqueue jobs
│   │   ├── subjects.py · synthetic.py · analysis.py · stress.py
│   │   ├── investigations.py · alerts.py · evidence.py · backtests.py
│   │
│   ├── persistence/
│   │   ├── db.py                 # async engine/session
│   │   ├── models/               # SQLAlchemy ORM, one module per DATA_MODEL section
│   │   ├── repositories/         # org-scoped data access; the only place SQL lives
│   │   └── registry_sync.py      # sync code registries → reference tables
│   │
│   ├── jobs/
│   │   ├── queue.py              # enqueue / dequeue (SKIP LOCKED) / heartbeat / retry policy
│   │   └── handlers.py           # job kind → service call
│   │
│   ├── observability/
│   │   ├── logging.py            # structlog config, redaction processor, context binding
│   │   ├── tracing.py            # optional OpenTelemetry
│   │   └── audit.py
│   │
│   └── api/
│       ├── deps.py               # auth (JWT/JWKS), current user/org, db session, pagination
│       ├── errors.py             # exception → problem+json handlers
│       ├── middleware.py         # request id, access log, rate limit
│       ├── schemas/              # HTTP DTOs (separate from domain objects)
│       └── v1/routers/           # system, meta, subjects, synthetic, data, analyses, metrics,
│                                 # passport, alerts, stress, investigations, evidence,
│                                 # portfolio, jobs, evaluation
└── tests/
    ├── conftest.py               # Postgres fixture, factories, replay LLM
    ├── unit/                     # mirrors src/ for pure modules
    ├── property/                 # Hypothesis invariants
    ├── golden/                   # persona snapshots (fixtures/*.json)
    ├── integration/              # services + repositories + API against real Postgres
    ├── agents/                   # orchestration with recorded LLM fixtures
    │   └── fixtures/recordings/
    └── evaluation/               # early-warning backtest gates (pytest -m evaluation)
```

**Enforced dependency rule** (import-linter contract in CI): the PURE packages
(`core`, `domain`, `synthetic`, `ingestion`, `analytics`, `scoring`, `early_warning`, `stress`,
`evidence`, `verification`) may import only each other and the standard/scientific libraries —
never `persistence`, `api`, `services`, `llm`, `agents`, `orchestration` or `jobs`.

## 3. Frontend — `apps/web`

```
apps/web/
├── package.json · tsconfig.json (strict) · next.config.ts · tailwind.config.ts · components.json
├── src/
│   ├── app/
│   │   ├── layout.tsx · globals.css · error.tsx · not-found.tsx
│   │   ├── (auth)/login/page.tsx
│   │   └── (app)/
│   │       ├── layout.tsx                      # shell: nav, org, user
│   │       ├── page.tsx                        # portfolio overview
│   │       ├── subjects/page.tsx
│   │       ├── subjects/new/page.tsx
│   │       ├── subjects/[id]/layout.tsx        # header + tabs
│   │       ├── subjects/[id]/page.tsx          # passport
│   │       ├── subjects/[id]/health/page.tsx
│   │       ├── subjects/[id]/transactions/page.tsx
│   │       ├── subjects/[id]/alerts/page.tsx
│   │       ├── subjects/[id]/stress/page.tsx
│   │       ├── subjects/[id]/investigations/[invId]/page.tsx
│   │       ├── methodology/page.tsx
│   │       └── evaluation/page.tsx
│   ├── components/
│   │   ├── ui/                                 # shadcn/ui generated primitives
│   │   ├── charts/                             # radar, timeseries-with-markers, fan-chart, bars
│   │   └── features/
│   │       ├── passport/ · health/ · alerts/ · stress/
│   │       ├── investigation/                  # step trace, claim card, evidence chip, challenge
│   │       ├── subjects/ · portfolio/ · methodology/
│   ├── lib/
│   │   ├── api/
│   │   │   ├── schema.d.ts                     # GENERATED from contracts/openapi.json
│   │   │   ├── client.ts                       # typed fetch, auth header, problem+json → ApiError
│   │   │   └── server.ts                       # server-component helpers
│   │   ├── format/                             # money, percent, date, score band
│   │   ├── hooks/                              # useJob, useInvestigationEvents (SSE)
│   │   └── auth/                               # Supabase session helpers
│   └── middleware.ts                           # auth redirect
└── tests/
    ├── unit/                                   # Vitest
    └── e2e/                                    # Playwright
```

## 4. Ownership map

| Concern | Lives in | Never in |
|---|---|---|
| Financial calculation | `analytics/`, `scoring/`, `early_warning/`, `stress/` | `agents/`, `api/`, `apps/web` |
| Truth checking of AI output | `verification/` | prompts |
| What the LLM sees | `evidence/`, `agents/tools/`, `agents/prompts/` | ad-hoc in services |
| SQL | `persistence/repositories/` | engines, routers |
| HTTP shapes | `api/schemas/` | domain objects |
| Number formatting for display | `apps/web/src/lib/format/` | components inline |

## 5. Tooling

| Area | Tool |
|---|---|
| Python env/deps | `uv` |
| Lint/format | `ruff` (lint + format) |
| Types | `mypy --strict` on pure packages; standard elsewhere |
| Architecture lint | `import-linter` |
| Tests | `pytest`, `pytest-asyncio`, `hypothesis`, `syrupy` (snapshots) |
| JS | `npm`, ESLint, `tsc --noEmit`, Vitest, Playwright |
| Contracts | `openapi-typescript` |
| Local stack | Docker Compose |
| CI | GitHub Actions: lint → typecheck → unit/property → integration (Postgres service) → evaluation gates → web build → e2e (replay LLM) |
