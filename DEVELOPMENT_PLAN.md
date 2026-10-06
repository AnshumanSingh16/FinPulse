# FinPulse — Development Plan

> Status: **plan, nothing built yet.** Phases are ordered so that the deterministic source of
> truth exists and is tested before any LLM is introduced. Each phase ends with something that
> runs and is verified — no stubs presented as features.

## Guiding rules

1. **Numbers before narratives.** Phases 1–6 produce a fully working, LLM-free product
   (synthetic data → passport → early warnings → stress tests → UI). Agents arrive in Phase 7.
2. **Every phase is shippable and honest.** UI only shows features whose backend exists. Anything
   not yet built is absent, not mocked.
3. **Measure the product question early.** The early-warning backtest (Phase 4) is built in the
   same phase as the rules, not at the end.
4. **Versions and golden tests from day one** for every engine.

## Phase overview

| # | Phase | Main output | Depends on |
|---|---|---|---|
| 0 | Foundations | Monorepo, tooling, CI, Docker Postgres, API skeleton with health/errors/logging, auth | — |
| 1 | Domain & synthetic data | Persona generator with ground truth + simulated bureau; persistence of subjects/ledger | 0 |
| 2 | Ingestion & analytics | Normalisation, recurring detection, metric registry + catalogue, analysis-run pipeline, job queue | 1 |
| 3 | Scoring engine | Financial Passport v1 with factors, reason codes, confidence | 2 |
| 4 | Early-warning engine + evaluation | Rules, detectors, alerts lifecycle, deterioration index, backtest harness | 2 (3 for index on passport) |
| 5 | Stress-testing engine | Scenarios, projection, Monte Carlo, standard set → Resilience dimension | 2, 3 |
| 6 | Frontend (deterministic product) | Portfolio, subject, passport, health, alerts, stress lab, methodology, evaluation pages | 0; feature pages track 3–5 |
| 7 | LLM layer, evidence & verification | Evidence pack, LLM client + replay, tool layer, grounding verifier | 2–5 |
| 8 | Agents & orchestration | Specialists, synthesiser, red team, rebuttal, workflow executor, SSE | 7 |
| 9 | Investigation UI | Live trace, claims with verification, challenges, report | 8, 6 |
| 10 | Hardening & demo | Evals, performance, security review, retention, docs, demo cohort | all |

Phases 3, 4 and 5 can proceed in parallel once Phase 2's registry is stable. Phase 6 starts
alongside Phase 2 using the generated OpenAPI types (pages land as their endpoints land).

---

## Phase 0 — Foundations

**Build**
- Monorepo layout per `PROJECT_STRUCTURE.md`; `Makefile`; `.env.example`.
- `apps/api`: `uv` project, FastAPI app factory, `Settings`, structlog JSON logging with
  request-ID middleware, problem+json error handlers, `/health`, `/ready`, `/me`.
- Auth dependency: Supabase JWT verification via JWKS; dev-token mode guarded off in production.
- Alembic baseline: `organizations`, `users`, `jobs`, `audit_events`.
- `apps/web`: Next.js + TS strict + Tailwind + shadcn/ui init, app shell, login via Supabase Auth,
  typed API client from generated OpenAPI.
- `infra/docker-compose.yml`: postgres, api, worker (idle loop), web.
- CI: ruff, mypy, pytest (with Postgres service), eslint, tsc, build, OpenAPI drift check,
  import-linter contract.

**Exit criteria**: `make dev` brings up the stack; logged-in user sees an empty shell; CI green;
error responses match `API_SPEC §3` (tested).

**Progress**
- Done: monorepo (npm workspaces + uv), shared `@finpulse/contracts` package with OpenAPI
  export and generated types, `Settings` from one root `.env`, structlog logging with request IDs
  and redaction, problem+json errors, `/health` and `/ready` (database check), async SQLAlchemy
  engine + Alembic (no tables yet), typed web API client, dashboard shell with live
  connectivity checks, docker-compose Postgres, CI (lint, format, types, tests incl. Postgres,
  build, contract drift).
- Remaining: Supabase Auth (JWT verification, `/me`, login page), Alembic baseline tables
  (`organizations`, `users`, `jobs`, `audit_events`), containerised api/worker/web in compose,
  import-linter contract (added with the first pure engine package in Phase 1).

## Phase 1 — Domain & synthetic data

**Build**
- `core/` (Money, Period, enums) and `domain/` ledger objects.
- `synthetic/`: personas — `salaried_thin_file`, `gig_worker`, `freelancer`, `kirana_store`,
  `seasonal_business`, `micro_manufacturer`; each with stable and deteriorating variants.
  Deterioration mechanisms: `income_loss`, `income_decline`, `loan_stacking`,
  `top_customer_loss`, `expense_shock`, `receivables_delay`.
- Ground truth (`onset_date`, mechanism) and `bureau.py` simulated bureau events (formal-credit
  EMI misses → DPD reporting with cycle lag).
- Tables: `subjects`, `accounts`, `counterparties`, `transactions`, `quarantined_transactions`,
  `synthetic_generations`, `simulated_bureau_events`.
- `POST /synthetic/generations` (job), `GET /subjects`, `/subjects/{id}`, accounts, transactions.

**Tests**: seed determinism (same seed ⇒ identical dataset hash); each persona's statistical
profile within declared ranges; bureau events never precede the ground-truth onset; ledger balance
reconciliation.

**Exit criteria**: generate any persona via API; browse its ledger; dataset is reproducible from
`(persona, seed, params, generator_version)`.

**Progress**
- Done: deterministic day-by-day generator (`finpulse.synthetic`) with five entities —
  Sharma Electricals (primary demo, deteriorating), a healthy MSME, a thin-file healthy MSME, a
  high-risk MSME and a freelancer — producing bank transactions, a daily sales register,
  invoices/receivables, bills/payables, customers, suppliers, loans with EMI schedules and
  bounces, GST, ground truth and a simulated bureau. Tables and migration for all of it,
  idempotent seeding, `db init|seed|reset` scripts, CSV export, and a consistency test suite
  (see `docs/SYNTHETIC_DATA.md`).
- Changed from the plan: business documents (`invoices`, `bills`, payments, `loans`,
  `loan_installments`, `counter_sales`) were added to the data model so receivables, payables and
  debt reconcile against cash. Scenarios are named entities rather than generic personas.
- Remaining: HTTP endpoints (`POST /synthetic/generations`, subjects, accounts, transactions) and
  the subjects/ledger pages in the web app; import-linter contract for the pure packages.

## Phase 2 — Ingestion & analytics layer

**Build**
- `ingestion/`: validation + quarantine, counterparty normalisation, rule-based categorisation,
  transfer pairing, recurring-series detection, obligation events.
- `analytics/registry.py` + full MVP metric catalogue (ARCHITECTURE §6.3).
- Registry sync into `metric_definitions`; `/meta/metrics`.
- Job queue (`jobs/queue.py`): enqueue, SKIP LOCKED dequeue, heartbeats, retries/backoff, stale
  lock reclaim. Worker process.
- Analysis pipeline service with stage persistence, fingerprint dedup, concurrency guard.
- Tables: `recurring_series`, `obligation_events`, `analysis_runs`, `metric_values`.
- Endpoints: analyses, metrics, metric series, recurring series, obligation events, jobs.

**Tests**: per-metric hand-computed fixtures incl. edge cases; property tests (order invariance,
scaling, self-transfer neutrality); recurring detection precision/recall against generator labels;
golden snapshots per persona; queue concurrency test (two workers, no double execution).

**Exit criteria**: analysis run on every persona succeeds; metrics reproducible bit-for-bit;
failed stage reporting verified by fault-injection test.

**Progress**
- Done (2a): pure analytics engine (`finpulse.analytics`) with 20 versioned metrics — revenue,
  expenses, net cash flow, growth, volatility, cash balance, runway, receivables, receivable and
  payable days, debt outstanding, debt-service burden, customer and supplier concentration,
  income stability, payment consistency, liquidity ratio, financial buffer, transaction
  consistency. Each has a typed value, unit, period, availability, confidence, components and
  source references. Exposed via `GET /api/v1/entities`, `/entities/{id}/financial-metrics[/{code}]`
  and `/meta/financial-metrics`. Tests: hand-checked unit cases, no-look-ahead property,
  reconciliation with the synthetic books, archetype behaviour, and a Postgres round trip.
- Remaining (2b): rule-based categorisation from narrations, transfer pairing, recurring-series
  detection, and persisted analysis runs (`analysis_runs`, `metric_values`) via the job queue.

## Phase 3 — Scoring engine (Financial Passport)

**Build**
- `scoring/models/passport_v1.yaml` (weights, breakpoints, bands); model loader with validation.
- Transforms, dimension scoring with renormalisation, confidence, shrinkage, bands, reason codes.
- Resilience dimension wired with a placeholder **absence** (score `null`, confidence 0) until
  Phase 5 provides stress inputs — shown in UI as "not yet available", not as a number.
- Tables: `scoring_models`, `passports`, `passport_dimensions`. Endpoints: passport, history,
  `/meta/scoring-model`.

**Tests**: monotonicity (improving a higher-is-better metric never lowers its dimension);
bounds; missing-input renormalisation; confidence behaviour on thin history; fairness test (input
set ⊆ approved metrics); persona ordering sanity (stable salaried > deteriorating gig worker at
the same as_of).

**Exit criteria**: every persona gets a passport with traceable factors; changing the model file
creates a new version without altering stored passports.

**Progress**
- Done: TOML scoring configuration with strict validation; a deterministic engine (piecewise-linear
  curves, re-normalised weights, confidence, provisional flag, word bands); factor-level
  contributions that sum exactly to the score; strengths and concerns; change attribution;
  month-end history; `GET /entities/{id}/passport`, `/passport/history` and
  `/meta/passport-model`. Five supporting metrics were added to the analytics engine. The
  methodology document is generated from the config and tested for drift.
- Deferred: storing passports (history is recomputed and stamped with the config hash), and the
  stress-based Resilience inputs (Phase 5).

## Phase 4 — Early-warning engine + evaluation harness

**Build**
- Rule framework + MVP rules (ARCHITECTURE §9.1); detectors (CUSUM, robust z, slope change).
- Signal persistence, alert lifecycle state machine, deterioration index.
- `backtest.py`: replay analyses over `as_of` steps for a cohort; lead time vs simulated bureau,
  precision/recall, false-alarm rate. Tables: `signals`, `alerts`, `early_warning_rules`,
  `backtest_runs`.
- Endpoints: signals, alerts (+PATCH), `/meta/early-warning-rules`, evaluation backtests.

**Tests**: each rule on crafted series (fires / doesn't fire / persistence boundary); alert
transitions; evaluation gates in CI (`pytest -m evaluation`) with thresholds agreed at phase start
(proposed: median lead time ≥ 30 days ahead of first DPD-30; high-severity precision ≥ 0.8;
false-alarm rate on stable personas ≤ 10%).

**Exit criteria**: backtest report produced for the full persona cohort; numbers recorded in
`docs/methodology/early-warning-evaluation.md` with their synthetic-data caveats.

## Phase 5 — Stress-testing engine

**Build**
- Scenario definitions + JSON-Schema params; baseline projection; seeded Monte Carlo; result
  aggregation; stressed passport recompute.
- Standard scenario set executed inside the analysis pipeline → Resilience dimension live.
- Tables: `stress_scenarios`, `stress_test_runs`, `stress_test_results`. Endpoints: stress tests,
  `/meta/stress-scenarios`.

**Tests**: zero-shock ≈ baseline; monotonicity (larger shock ⇒ not better outcome);
seed determinism; dedup of identical requests; performance budget (500 paths × 12 months < 2s per
subject on CI hardware).

**Exit criteria**: stress lab runs on every persona; Resilience dimension populated and versioned.

## Phase 6 — Frontend: deterministic product

Built incrementally alongside Phases 2–5.

**Build**: portfolio overview, subject list/new (persona generator form), passport page (radar +
dimension cards + factor drill-down + reason codes + confidence), health timeline (metric series
with signal markers), transactions, alerts (ack/resolve), stress lab (scenario form from
`params_schema`, fan chart vs baseline, stressed dimension deltas), methodology (rendered from
`/meta/*`), evaluation page.

**Tests**: Vitest for formatters, API error mapping, key components; Playwright e2e:
generate → analyse → passport → stress.

**Exit criteria**: a reviewer can answer the product question for any persona **without any AI**,
purely from deterministic outputs and their explanations.

## Phase 7 — LLM layer, evidence pack, verification

**Build**
- `evidence/pack.py` (canonical JSON + hash), stored per analysis run.
- `llm/`: client protocol, production adapter (provider/model via env), retry/timeout, usage and
  cost accounting, `llm_calls` persistence; record/replay adapter.
- `agents/tools/`: all read-only tools from `API_SPEC §5` with scope guards and output bounds.
- `verification/`: numeric extraction (digits, %, ₹/lakh/crore formats, written numbers), checks,
  verifier versioning.

**Tests**: tool scope guard (cannot read another subject even with forged IDs); output bounds;
verifier adversarial suite (fabricated numbers, sign flips, wrong units, rounding edges, unit
conversions like ratio↔percent); evidence pack determinism.

**Exit criteria**: verifier catches 100% of the adversarial suite; tools return only scoped,
ID-bearing evidence.

## Phase 8 — Agents & orchestration

**Build**
- Agent schemas, specs and v1 prompts for Cash-Flow, Obligations & Risk, Stress, Business,
  Synthesiser, Red Team.
- Agent runner (tool loop, one repair attempt, budgets); workflow `investigation_v1`;
  executor with phase persistence, resume, cancel, events.
- Tables: investigations, agent_steps, tool_calls, llm_calls, claims, claim_verifications,
  challenges, investigation_events, reports. Endpoints incl. SSE.
- Optional auto-investigation on high-severity alerts (flag, default off).

**Tests**: replay-fixture runs covering happy path, tool argument errors, invalid structured
output → repair, budget exhaustion → partial, provider outage → partial with deterministic data
intact, worker crash → resume, cancel. Live-LLM eval suite (nightly/manual): groundedness rate,
reason-code coverage, red-team challenge acceptance rate.

**Exit criteria**: on every persona, the final report contains only verified or explicitly
disputed claims; live eval groundedness ≥ 95% of claims verified before red-team (target to be
calibrated).

## Phase 9 — Investigation UI

**Build**: start-investigation dialog (question presets + free text), live phase/step trace via
SSE, claim cards with verification badge and evidence chips (resolved via `/evidence`), red-team
challenge threads with resolutions, final report with partial/disputed indicators, cost/latency
footer.

**Exit criteria**: e2e with replay LLM; a user can click any sentence in a report through to the
underlying metric and transactions.

## Phase 10 — Hardening & demo readiness

- Security review (authz on every route, scope guards, prompt-injection tests with hostile
  transaction descriptions), rate limits, retention job, OpenTelemetry option.
- Performance: analysis run < 5s per subject for 18 months of data; portfolio of 200 subjects.
- Documentation: ADRs, methodology pages generated from registries, runbook.
- Demo cohort script: fixed seeds covering every persona × stable/deteriorating.

## Cross-phase Definition of Done

- Code + tests + docs in the same PR; CI green incl. golden and (where relevant) evaluation gates.
- Engine changes bump versions; snapshot updates reviewed.
- No hard-coded financial numbers in frontend or prompts.
- New endpoints in OpenAPI and regenerated TS types committed.
- Logs carry correlation IDs; errors use the taxonomy.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Synthetic data makes results look better than reality | Ground truth + backtest are reported with explicit caveats; generator includes noise, data gaps, irregular earners and "false alarm" personas (stable people with one bad month) |
| Rules overfit to the generator | Generator and rules developed by separate passes; hold-out seeds and a hold-out persona variant used only for evaluation |
| LLM fabricates or overstates | Structured claims, deterministic verifier, red team, rejected claims never shown as fact |
| LLM cost/latency | Evidence pack instead of raw data; per-investigation budgets; no LLM on request path; auto-investigation off by default |
| Scope creep into real integrations | Explicitly out of scope; ingestion seam documented |
| Fairness concerns | No protected attributes; tested input whitelist; red-team `fairness` challenge type |

## Open questions for the product owner

1. Primary market/currency for synthetic personas — default assumes India (INR, UPI, lakh/crore
   formatting). Confirm or change.
2. LLM provider and model preferences, and the per-investigation cost ceiling.
3. Target users for the MVP UI: lender analysts, the individuals/businesses themselves, or both?
   (The current design targets analysts; a self-view would need a separate, simplified surface.)
4. Hosting: Supabase-hosted Postgres + Auth, or self-hosted Postgres with Supabase only for auth?
5. Evaluation thresholds in Phase 4 — accept the proposed defaults?
