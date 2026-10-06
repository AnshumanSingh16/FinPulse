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
├── apps/
│   ├── api/                      # Python backend + worker (one package, two entrypoints)
│   └── web/                      # Next.js frontend
├── packages/
│   └── contracts/                # @finpulse/contracts: openapi.json exported from FastAPI +
│                                 # schema.gen.ts generated from it (shared API types)
├── infra/
│   ├── docker-compose.yml        # postgres, api, worker, web
│   └── postgres/init.sql         # pgcrypto; local roles
├── docs/SYNTHETIC_DATA.md        # the synthetic dataset: entities, structure, guarantees, how to extend
├── scripts/                      # dev.mjs (API + web), db-init.sh, db-seed.sh, db-reset.sh
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
│   ├── cli.py                    # `finpulse db init|seed|reset|counts`, `finpulse synthetic …`
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
│   ├── synthetic/                # PURE: seeded day-by-day simulation (see docs/SYNTHETIC_DATA.md)
│   │   ├── spec.py               # ScenarioSpec + shocks: the knobs a scenario sets
│   │   ├── engine.py             # simulation: sales, invoices, bills, payroll, tax, loans, cash
│   │   ├── scenarios/            # one module per entity (sharma_electricals.py, …) + registry
│   │   ├── model.py              # Dataset and its records
│   │   ├── loans.py · bureau.py  # amortisation; simulated bureau (evaluation only)
│   │   ├── summary.py            # month-by-month bookkeeping roll-up
│   │   ├── export.py             # table-shaped records, fingerprint, CSV export
│   │   └── sampling.py · calendar.py · ids.py · categories.py
│   ├── ingestion/                # PURE: raw → normalised ledger
│   │   ├── validate.py
│   │   ├── counterparties.py
│   │   ├── categorise.py         # rule tables in categorise_rules.yaml
│   │   ├── transfers.py
│   │   └── recurring.py          # series detection + obligation events
│   │
│   ├── analytics/                # PURE: financial metrics (see docs/FINANCIAL_METRICS.md)
│   │   ├── inputs.py             # FinancialData: the read-only snapshot the engine consumes
│   │   ├── classify.py           # how transaction categories group into receipts/expenses/…
│   │   ├── context.py            # months, balances, receivables: computed once per report
│   │   ├── registry.py           # metric definitions (catalogue), value & output helpers
│   │   ├── metrics.py            # the 20 metric functions
│   │   ├── engine.py             # compute_report(data, as_of) → FinancialMetricsReport
│   │   └── schemas.py            # Pydantic outputs (also the API response models)
│   │
│   ├── scoring/                  # PURE: Financial Passport (see docs/FINANCIAL_PASSPORT.md)
│   │   ├── models/passport_v1.toml  # the methodology: dimensions, weights, curves, bands
│   │   ├── config.py             # load + strictly validate a model file
│   │   ├── engine.py             # score_passport(report, model), explain_change(a, b)
│   │   ├── history.py            # month-end history, change since previous month
│   │   ├── methodology.py        # renders the config into the methodology document
│   │   ├── format.py · schemas.py
│   │
│   ├── early_warning/            # PURE: early warnings (see docs/EARLY_WARNING.md)
│   │   ├── config/early_warning_v1.toml  # every threshold, window and weight
│   │   ├── config.py             # strict loader: each rule section validated by its Params
│   │   ├── snapshots.py          # memoised per-date analytics contexts; month-end medians
│   │   ├── rules.py              # Rule / LevelRule / VolatilityRule, @register'd rules, grading
│   │   ├── engine.py             # detect_warnings(), risk_summary(): streaks, IDs, timeline
│   │   └── schemas.py            # EarlyWarning, WarningsReport, RiskSummary
│   │
│   ├── stress/                   # PURE: stress tests (see docs/STRESS_TESTING.md)
│   │   ├── baseline.py           # 3-month baseline + loan schedules from the analytics context
│   │   ├── shocks.py             # Levers, @register'd shock types + typed Params, ShockSpec
│   │   ├── presets.py            # the named scenarios (data)
│   │   ├── projection.py         # simulate(levers): month-by-month cash, failure point
│   │   ├── risk.py · health.py   # risk levels; projected metrics → stressed passport
│   │   ├── engine.py             # run_stress_test(data, as_of, request, model)
│   │   └── schemas.py
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
│   ├── agents/                   # AI layer (see docs/AI_AGENTS.md)
│   │   ├── evidence.py           # deterministic evidence pack: citable, typed, hashed items
│   │   ├── numbers.py · verifier.py  # number reading; claim verification, pruning
│   │   ├── llm.py                # LLMClient protocol; Claude adapter (structured outputs)
│   │   ├── schemas.py            # Claim + each agent's output; AgentRun
│   │   ├── prompts.py            # shared rules + one role prompt per agent
│   │   ├── base.py               # AgentSpec, run_agent: verify → repair → prune
│   │   ├── catalogue.py          # the seven AgentSpecs
│   │   └── orchestrator.py       # one agent + its dependencies (single-agent endpoint)
│   │
│   ├── investigation/            # the investigation workflow (see docs/INVESTIGATIONS.md)
│   │   ├── orchestrator.py       # 11 recorded stages; events mirrored to structured logs
│   │   ├── analysis.py           # deterministic: disagreements, review, confidence, audit
│   │   ├── schemas.py            # Investigation record
│   │   ├── store.py              # recent investigations (memory + optional JSON files)
│   │   └── report.py             # terminal rendering for demos
│   │
│   ├── orchestration/
│   │   ├── workflow.py           # Phase/StepSpec definitions; investigation_v1
│   │   ├── executor.py           # runs phases, persists boundaries, resumes, emits events
│   │   └── budgets.py
│   │
│   ├── services/                 # use cases (entities.py: load entity, resolve as_of; more to come)
│   │   ├── subjects.py · synthetic.py · analysis.py · stress.py
│   │   ├── investigations.py · alerts.py · evidence.py · backtests.py
│   │
│   ├── persistence/
│   │   ├── db.py                 # async engine/session
│   │   ├── models.py             # SQLAlchemy ORM (split per DATA_MODEL section as it grows)
│   │   ├── seed.py               # load synthetic datasets (idempotent)
│   │   ├── repositories/         # org-scoped data access (financial_data.py → FinancialData)
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
│   │   │   ├── client.ts                       # openapi-fetch + @finpulse/contracts types, unwrap()
│   │   │   ├── errors.ts                       # problem+json / network failure → ApiError
│   │   │   ├── server.ts                       # client for Server Components (FINPULSE_API_URL)
│   │   │   └── browser.ts                      # client for Client Components (NEXT_PUBLIC_API_URL)
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
| Contracts | `openapi-typescript`, `openapi-fetch` |
| Local stack | Docker Compose |
| CI | GitHub Actions: lint → typecheck → unit/property → integration (Postgres service) → evaluation gates → web build → e2e (replay LLM) |
