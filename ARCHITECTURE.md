# FinPulse — System Architecture

> Status: **design, not implemented.** This document describes the target architecture for the
> MVP. Nothing described here exists in code yet. See `DEVELOPMENT_PLAN.md` for build order.

Companion documents:

| Document | Covers |
|---|---|
| `ARCHITECTURE.md` (this) | System shape, engines, agents, orchestration, cross-cutting concerns |
| `DATA_MODEL.md` | PostgreSQL schema, lineage, versioning, retention |
| `API_SPEC.md` | HTTP API contract between the Next.js app and the FastAPI backend |
| `PROJECT_STRUCTURE.md` | Repository layout and module ownership |
| `DEVELOPMENT_PLAN.md` | Phased build plan, exit criteria, risks |

---

## 1. Product question and what the system must prove

> Can we understand whether a financially thin-file person or business is financially
> trustworthy, and detect if their financial health is deteriorating before a traditional credit
> system would?

That question splits into two testable claims, and the architecture is shaped so both can be
**measured**, not just asserted:

1. **Trustworthiness without a credit file.** From transaction-level behaviour alone we can produce
   a multidimensional, explainable *Financial Passport* whose dimensions are stable, reproducible
   and traceable to raw transactions.
2. **Earlier deterioration detection.** Our early-warning engine fires *before* the event a
   traditional bureau would record (e.g. a 30+ days-past-due delinquency). Because the MVP uses
   synthetic data, the generator emits **ground-truth deterioration onset dates** and a
   **simulated bureau event stream**, so lead time, precision and recall are computed, not
   claimed (§9.4).

## 2. Core principle: deterministic numbers, AI reasoning

```
                ┌──────────────────────────────────────────────┐
                │  SOURCE OF TRUTH (deterministic Python)       │
 transactions → │  normalise → metrics → passport → signals →   │ → persisted, versioned,
                │  stress results                                │   reproducible numbers
                └──────────────────────────────────────────────┘
                                   │ read-only, via typed tools
                                   ▼
                ┌──────────────────────────────────────────────┐
                │  REASONING LAYER (LLM agents)                 │
                │  investigate · hypothesise · challenge ·      │ → claims that cite evidence
                │  explain                                      │
                └──────────────────────────────────────────────┘
                                   │
                                   ▼
                ┌──────────────────────────────────────────────┐
                │  VERIFICATION (deterministic Python)          │
                │  every number and evidence ref in an agent    │ → verified / rejected claims
                │  claim is checked against the source of truth │
                └──────────────────────────────────────────────┘
```

Rules that follow from the principle, enforced in code rather than by prompt alone:

- **R1 — Agents cannot write financial data.** Agent tools are read-only views over persisted
  analytics. There is no tool that inserts or updates metrics, scores, signals or transactions.
- **R2 — Agents cannot compute new metrics.** If an agent needs a number that does not exist, the
  only path is calling a deterministic engine through a tool (e.g. `run_stress_scenario`), which
  persists its own result with its own version. Agents never do arithmetic that is then shown as a
  fact.
- **R3 — Every claim cites evidence.** Agent output is a Pydantic-validated structure of claims;
  each claim carries `evidence_refs` (metric value IDs, signal IDs, stress result IDs, transaction
  IDs).
- **R4 — Every number in agent text is verified.** The grounding verifier extracts numeric tokens
  from claim text and matches each one to a cited evidence value (with a declared rounding
  tolerance). Unmatched numbers → the claim is `rejected` and never rendered as fact.
- **R5 — Deterministic results never depend on the LLM.** Passport, signals and stress results are
  produced and viewable even when the LLM provider is down. Investigations degrade; numbers don't.
- **R6 — No automated credit decision.** FinPulse produces an assessment and evidence for a human.
  Neither the engines nor the agents emit approve/decline outcomes.

## 3. System context

```
┌──────────────┐  HTTPS/JSON   ┌───────────────────────────┐   SQL    ┌──────────────┐
│  Next.js web │ ────────────▶ │  FastAPI (finpulse-api)    │ ───────▶ │  PostgreSQL  │
│  (apps/web)  │ ◀──────────── │  ├ REST /api/v1            │ ◀─────── │  (Supabase-  │
│              │  SSE (events) │  ├ engines (pure Python)   │          │  compatible) │
└──────┬───────┘               │  ├ agent orchestrator      │          └──────▲───────┘
       │ Supabase Auth (JWT)   │  └ job worker (same image) │                 │
       ▼                       └──────────┬────────────────┘                 │
┌──────────────┐                          │ HTTPS                             │
│ Supabase Auth│                          ▼                                   │
│ (or dev stub)│                 ┌──────────────────┐        jobs table (SKIP LOCKED)
└──────────────┘                 │  LLM provider API │
                                 └──────────────────┘
```

Deployable units in the MVP:

| Unit | Runtime | Responsibility |
|---|---|---|
| `web` | Node (Next.js App Router) | UI, auth session, server-side data fetching. Holds **no** financial logic. |
| `api` | Python 3.12+, FastAPI, Uvicorn | HTTP API, validation, auth verification, enqueueing work. |
| `worker` | Same image as `api`, different entrypoint | Executes jobs: synthetic generation, analysis runs, stress tests, investigations. |
| `db` | PostgreSQL 15+ | All state, including the job queue. |

No Redis, Celery, Kafka or vector DB in the MVP. The job queue is a Postgres table consumed with
`SELECT … FOR UPDATE SKIP LOCKED`. This keeps the system to three moving parts and is sufficient for
MVP throughput (tens of concurrent jobs). The `jobs` module exposes an interface so it can be swapped
for a dedicated queue later without touching engines.

## 4. Frontend architecture (`apps/web`)

**Stack:** Next.js (App Router) · TypeScript (strict) · Tailwind CSS · shadcn/ui · Recharts ·
TanStack Query (client-side polling/mutations) · Zod (only for form input) · `openapi-typescript`
generated API types.

### 4.1 Responsibilities and non-responsibilities

- Renders data produced by the backend. **The frontend does not calculate financial metrics,
  scores or thresholds.** Its only numeric work is formatting (currency, %, dates) and chart
  scaling.
- API types are **generated** from the backend OpenAPI schema (`packages/contracts/openapi.json` → `@finpulse/contracts`), never
  hand-written, so the contract cannot drift silently. CI fails if the generated file is stale.

### 4.2 Route map

| Route | Purpose | Main data |
|---|---|---|
| `/` | Portfolio overview: subjects, band distribution, open alerts | `GET /portfolio/summary`, `GET /alerts` |
| `/subjects` | Searchable list of individuals and businesses | `GET /subjects` |
| `/subjects/new` | Generate a synthetic subject from a persona | `GET /meta/personas`, `POST /synthetic/generations` |
| `/subjects/[id]` | Financial Passport: overall band, 7 dimensions (radar), confidence, factor contributions | passport, metrics |
| `/subjects/[id]/health` | Health timeline: balance, inflow/outflow, metric time series with signal markers | metric timeseries, signals |
| `/subjects/[id]/transactions` | Paginated ledger with categories and recurring-series tags | transactions |
| `/subjects/[id]/alerts` | Early warnings with evidence and lifecycle (ack/resolve) | signals, alerts |
| `/subjects/[id]/stress` | Stress lab: choose scenario, run, compare fan charts | stress tests |
| `/subjects/[id]/investigations/[invId]` | Agent investigation: live step trace, claims with evidence chips, red-team challenges, verification status, final report | investigation, steps, SSE |
| `/methodology` | Metric registry, scoring model, rules, scenario definitions — rendered from `/meta/*` | meta endpoints |
| `/evaluation` | Early-warning backtest: lead time vs simulated bureau, precision/recall | evaluation endpoints |

### 4.3 Layering

```
app/(routes)          Server Components: fetch via lib/api/server.ts, pass plain props down
  └ components/features/<feature>/   Client components where interactivity is needed
       └ components/charts/           Recharts wrappers (one per chart type, theme-aware)
       └ components/ui/               shadcn/ui primitives (generated, lightly customised)
lib/api/                typed fetch client (generated types + thin wrapper), error mapping
lib/format/             money (minor units → display), percent, dates — the ONLY numeric code
lib/hooks/              TanStack Query hooks for polling jobs, SSE subscription for investigations
```

- **Server Components by default.** Pages fetch on the server with the user's JWT forwarded as a
  bearer token. Client Components are used for charts, forms, polling and SSE.
- **Long-running work** (analysis, stress, investigation) returns `202` + a job/resource ID. The UI
  polls `GET /jobs/{id}` via TanStack Query (backoff 1s→5s) or subscribes to the investigation SSE
  stream.
- **Error UX:** API errors arrive as RFC 7807 `problem+json`; `lib/api` maps them to a typed
  `ApiError`. Route-level `error.tsx` boundaries render a recoverable state; `not-found.tsx` for 404.
  Partial investigations (LLM failure) render with a visible "partial — verification incomplete"
  banner, never silently.
- **Explainability-first components:** every score tile links to its factor contributions; every
  agent claim renders its verification badge (`verified` / `rejected` / `unverifiable`) and
  clickable evidence chips that open the underlying metric, signal or transactions.
- **Accessibility & theming:** shadcn/ui + Tailwind tokens, light/dark, charts use a validated
  palette and never encode meaning by colour alone (severity also uses icon + label).

## 5. Backend architecture (`apps/api`)

**Stack:** Python 3.12+ · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async, psycopg 3) · Alembic ·
NumPy / pandas (analytics only) · structlog · httpx · pytest + Hypothesis · `uv` for packaging.

### 5.1 Layered design

```
┌───────────────────────────────────────────────────────────────────────────┐
│ api/          FastAPI routers, request/response DTOs, auth deps, error map │  I/O edge
├───────────────────────────────────────────────────────────────────────────┤
│ services/     Use-case orchestration: "run analysis", "start investigation"│  application
│               Owns transactions (DB unit of work) and job enqueueing        │
├───────────────────────────────────────────────────────────────────────────┤
│ engines (pure):  ingestion · analytics · scoring · early_warning · stress  │  domain core
│                  verification · synthetic                                   │  (no I/O)
├───────────────────────────────────────────────────────────────────────────┤
│ agents/ + orchestration/ + llm/   reasoning layer; reads via tools only     │  reasoning
├───────────────────────────────────────────────────────────────────────────┤
│ persistence/  SQLAlchemy models, repositories     jobs/  queue + worker     │  infrastructure
│ observability/ logging, tracing, audit                                      │
└───────────────────────────────────────────────────────────────────────────┘
```

Dependency rule: arrows point downward only. **Engines are pure functions over in-memory domain
objects** (`Transaction`, `Account`, `RecurringSeries`, `MetricValue`, …) and import nothing from
`api`, `persistence`, `llm` or `agents`. This is what makes them deterministic, fast to test, and
reusable from the worker, tests and notebooks alike.

### 5.2 Determinism contract for engines

Every engine:

- takes an explicit `as_of: date` (never reads the clock),
- takes an explicit `seed` where randomness is involved (synthetic, Monte Carlo stress),
- uses `Decimal` / integer minor units for money (never `float` for stored money; NumPy floats are
  allowed for statistical intermediates, rounded at the boundary with a documented rule),
- declares a `VERSION` constant; output rows record the version that produced them,
- is covered by golden tests: same inputs + versions ⇒ byte-identical outputs.

An **analysis run** records `input_fingerprint = sha256(sorted transaction IDs + amounts + as_of +
engine versions)`. Re-running with an identical fingerprint is a no-op that returns the existing run.

### 5.3 The analysis pipeline

One `analysis_run` per (subject, as_of). Executed by the worker as a single job with persisted
stage boundaries:

```
1. load        transactions, accounts for subject up to as_of
2. normalise   counterparty normalisation, categorisation, transfer pairing (ingestion/)
3. recurring   detect recurring series (income, rent, utilities, EMIs) and obligation events
4. metrics     compute all registered metrics → metric_values (with lineage)
5. passport    scoring engine → passport + dimensions + factor contributions
6. signals     early-warning engine → signals; alert manager updates alert lifecycle
7. evidence    build immutable evidence pack (snapshot of 4–6) for agents
8. finalise    status=succeeded, timings, versions
```

Stages 2–7 are pure engine calls; the service persists each stage's output in one DB transaction
per stage, so a failure leaves a clear `failed_stage` and nothing half-written within a stage.

## 6. Financial analytics layer

### 6.1 Ingestion & normalisation (`ingestion/`)

Synthetic data arrives already shaped like bank/UPI/wallet exports, but the pipeline treats it as
untrusted raw input so the same code path works for real integrations later.

- **Schema validation** — Pydantic models for raw transactions; invalid rows are quarantined with
  a reason (not silently dropped).
- **Counterparty normalisation** — deterministic string normalisation + alias table.
- **Categorisation** — rule-based (merchant/category code → category, keyword rules), each row
  records `category_source` (`rule`, `synthetic_label`, `manual`) and a confidence. **No LLM
  categorisation in the MVP**: it would make the source of truth non-deterministic.
- **Transfer pairing** — matches debits/credits between the subject's own accounts so self-transfers
  don't inflate income or spending.
- **Recurring series detection** — groups by counterparty + amount band, infers cadence (weekly,
  bi-weekly, monthly), expected amount, and emits `obligation_events` with `on_time / late / missed`
  status against the inferred schedule.

### 6.2 Metric registry (`analytics/registry.py`)

Every metric is a registered, versioned, documented function:

```python
@metric(
    code="liq.buffer_days", version=1, unit="days", direction=Direction.HIGHER_IS_BETTER,
    window=Window.TRAILING_90D, applies_to={SubjectKind.INDIVIDUAL, SubjectKind.BUSINESS},
    description="Average end-of-day balance divided by average daily essential outflow.",
)
def liquidity_buffer_days(ctx: MetricContext) -> MetricResult: ...
```

`MetricResult` = `value` (Decimal or None) + `quality` (`ok` / `insufficient_data` /
`degraded`) + `inputs` (lineage: counts, window bounds, contributing series IDs). A metric that
can't be computed returns `None` with a quality flag — **never a default number**.

The registry is the single catalogue used by the scoring engine, early-warning rules, the
`/meta/metrics` endpoint, the methodology page and agent tools.

> **Implemented (Phase 2a):** the analytics engine and 20 financial metrics, exposed at
> `GET /api/v1/entities/{id}/financial-metrics`. The implemented catalogue, conventions and
> methods are in [docs/FINANCIAL_METRICS.md](docs/FINANCIAL_METRICS.md). The codes below were the
> initial sketch. Still to come from this section: narration-based categorisation, recurring-series
> detection, and persisting results as analysis runs.

### 6.3 MVP metric catalogue (initial)

| Family | Codes (illustrative) | Notes |
|---|---|---|
| Income | `inc.monthly_mean`, `inc.cv_6m`, `inc.source_count`, `inc.top_source_share`, `inc.regular_share`, `inc.gap_months_12m` | Regular share = income from detected recurring series |
| Cash flow | `cf.net_monthly`, `cf.net_margin`, `cf.inflow_outflow_ratio`, `cf.volatility_6m`, `cf.negative_months_6m` | |
| Liquidity | `liq.avg_daily_balance`, `liq.min_balance_90d`, `liq.buffer_days`, `liq.days_below_floor_90d`, `liq.negative_balance_days_90d` | |
| Obligations | `obl.on_time_rate_12m`, `obl.late_count_6m`, `obl.missed_count_6m`, `obl.avg_days_late`, `obl.obligation_to_income`, `obl.debt_service_ratio`, `obl.new_lender_inflows_60d` | `new_lender_inflows` detects loan stacking |
| Spending | `spd.essential_share`, `spd.discretionary_trend_slope`, `spd.cash_withdrawal_share`, `spd.high_risk_merchant_share`, `spd.savings_rate` | High-risk = gambling/betting category list |
| Business | `biz.revenue_growth_3m`, `biz.revenue_trend_slope_6m`, `biz.customer_hhi`, `biz.top_customer_share`, `biz.supplier_on_time_rate`, `biz.seasonality_index`, `biz.margin_proxy` | Only for `kind=business` |
| Trend | `trd.balance_slope_90d`, `trd.inflow_slope_6m` | Robust (Theil–Sen) slopes |
| Data quality | `dq.history_months`, `dq.txn_count_90d`, `dq.coverage_gap_days`, `dq.categorised_share` | Drives score confidence |

Exact formulas, windows and edge-case rules are written in the metric docstring and surfaced via
`/meta/metrics/{code}`; that text is the methodology of record.

## 7. Scoring engine — the Financial Passport (`scoring/`)

> **Implemented (Phase 3)** as a prototype; see [docs/FINANCIAL_PASSPORT.md](docs/FINANCIAL_PASSPORT.md).
> It differs from the sketch below:
> - **Dimensions** are the six requested ones: Cash-Flow Stability, Repayment Capacity, Revenue
>   Stability, Financial Resilience, Debt Health and Transaction Consistency.
> - **Configuration** is TOML (`scoring/models/passport_v1.toml`).
> - **Confidence** is reported alongside the score rather than shrinking it toward 50.
> - **Bands** are words (Strong … Critical), not letters.
> - **Explanations** are strengths and concerns plus factor-level change attribution, instead
>   of reason codes.
> - **History** is recomputed per month-end rather than stored.
> - **Resilience** comes from buffer, runway and liquidity metrics. The stress engine (Phase 5,
>   [docs/STRESS_TESTING.md](docs/STRESS_TESTING.md)) re-scores the passport on projected
>   metrics to show a scenario's health impact. It is deterministic and has no Monte Carlo yet.

### 7.1 Shape

The passport is **multidimensional first**; the overall score is a derived summary, not the product.

| Dimension | Question it answers | Primary inputs |
|---|---|---|
| Income Stability | How reliable and diversified is money coming in? | `inc.*` |
| Cash-Flow Health | Does money in exceed money out, consistently? | `cf.*` |
| Liquidity Buffer | How long can they absorb a disruption? | `liq.*` |
| Obligation Discipline | Do they pay recurring commitments on time? | `obl.*` |
| Spending Behaviour | Is spending controlled and essential-weighted? | `spd.*` |
| Resilience | How do they fare under standard stress scenarios? | baseline stress results (§8) |
| Business Vitality *(business only)* | Is the business growing and not over-concentrated? | `biz.*` |

Each dimension = **score 0–100** + **confidence 0–1** + **factor contributions**. Confidence is
separate from score: a thin history yields a *wide* answer, not a low one.

### 7.2 Method (transparent, not a black-box model)

1. **Transform**: each input metric → 0–100 sub-score via a declared piecewise-linear curve
   (`breakpoints` in the scoring model file). Direction-aware.
2. **Combine**: dimension score = weighted mean of available sub-scores; missing metrics are
   dropped and weights renormalised; confidence falls with each missing/degraded input.
3. **Overall**: weighted mean of dimensions, shrunk toward a neutral prior (50) in proportion to
   `1 − confidence` so thin files aren't rewarded or punished for absence of data.
4. **Band**: `A`–`E` from overall score; band thresholds live in the model file.
5. **Reason codes**: top positive and negative factor contributions (`Δpoints` vs neutral) are
   emitted as deterministic reason codes, e.g. `OBL_LATE_PAYMENTS_RECENT`. These are the
   explanation of record; agents narrate them, they don't replace them.

The model is a versioned YAML file (`scoring/models/passport_v1.yaml`) — weights, breakpoints,
bands. Changing it bumps `scoring_model_version`; old passports keep their version.

**Fairness guardrail:** no protected attributes (gender, religion, caste, age, location proxies)
are inputs. The synthetic generator doesn't emit them. A test asserts the scoring model's input
set is a subset of the registered, approved metric list.

**Why not ML for v1:** with synthetic data, a trained model would learn the generator, not
people. A transparent rules model is honest about what we know, is fully explainable, and gives
a baseline that a later learned model must beat on the evaluation harness.

## 8. Stress-testing engine (`stress/`)

### 8.1 Scenarios

Scenarios are versioned, parameterised definitions:

| Code | Shock | Key params |
|---|---|---|
| `income_shock` | Reduce income by x% for n months | `pct`, `months`, `start_offset` |
| `income_loss` | Income to zero (job loss / platform deactivation) | `months` |
| `expense_inflation` | Essential spend +x% | `pct`, `months` |
| `emergency_expense` | One-off lump-sum outflow | `amount_minor`, `month` |
| `top_customer_loss` *(business)* | Remove top customer's revenue | `months` |
| `receivables_delay` *(business)* | Shift customer inflows by d days | `days` |
| `rate_rise` | Increase detected EMI amounts by x% | `pct` |
| `seasonal_trough` *(business)* | Apply worst historical month pattern | `months` |
| `combined` | Ordered composition of the above | `components[]` |

### 8.2 Method

1. **Baseline projection** (monthly, horizon 3–12 months): recurring series projected on their
   cadence; non-recurring flows modelled as a bootstrap over the subject's own historical
   residuals by month-of-year/day-of-week.
2. **Monte Carlo**: N paths (default 500, max 2,000) with an explicit `seed` → deterministic for a
   given seed. Shocks are applied as transformations of each path.
3. **Outputs per run**: balance percentile bands (P5/P25/P50/P75/P95) per month,
   `p_balance_below_zero`, `p_missed_obligation`, `median_runway_months`, `worst_month`,
   `min_balance_p5`, and a **stressed passport** (Liquidity, Cash-Flow and Resilience recomputed on
   the median stressed path) with deltas vs baseline.
4. A fixed **standard scenario set** is run during analysis to feed the Resilience dimension, so
   Resilience is itself deterministic and versioned.

Stress runs can be triggered by users (stress lab) or by agents via a tool; both go through the
same service, are persisted, and are referenced by ID.

## 9. Early-warning engine (`early_warning/`)

> **As built (Phase 4, first part)** — see [docs/EARLY_WARNING.md](docs/EARLY_WARNING.md).
>
> - **Rules.** 18 rules with readable codes (e.g. `receivables_growth`). Each computes one
>   measure from historical comparisons: the same entity at earlier dates, or month-end medians.
> - **Configuration.** Thresholds live in `config/early_warning_v1.toml`, not in code.
> - **Grading.** Severity comes from configured tiers. A condition that is not worsening is
>   reported one step lower.
> - **Detectors.** The statistical detectors, persisted signals and alert lifecycle described
>   below are not built yet.

### 9.1 Detectors

Two families, both deterministic:

- **Rules** over metric values with persistence requirements, e.g.

| Code | Condition | Severity |
|---|---|---|
| `EW-INC-001` | Monthly income < 75% of trailing-3m baseline for ≥ 2 consecutive months | high |
| `EW-INC-002` | Regular income series stopped (expected credit missing > cadence + grace) | high |
| `EW-LIQ-001` | `liq.buffer_days` < 7 and falling | high |
| `EW-LIQ-002` | Negative balance days in last 30 > 3 | medium |
| `EW-OBL-001` | First late obligation after ≥ 6 months fully on time | medium |
| `EW-OBL-002` | Loan stacking: ≥ 2 new lender credits in 60 days | high |
| `EW-CF-001` | ≥ 3 consecutive months of negative net cash flow | medium |
| `EW-BIZ-001` | Top customer's revenue absent for > 1.5× their usual cadence | high |
| `EW-SPD-001` | Cash-withdrawal or high-risk-merchant share spike (> baseline + 3 MAD) | low |

- **Statistical change detectors** on time series: CUSUM on daily balance and monthly inflow;
  robust z-score vs trailing median/MAD; Theil–Sen slope sign change. Each detector has declared
  parameters and minimum data requirements.

### 9.2 Signals vs alerts

- A **signal** is an immutable detection in one analysis run (`rule_code`, `severity`,
  `evidence` = referenced metric value IDs + window).
- An **alert** is the lifecycle object across runs: `open → acknowledged → resolved`, with
  `first_detected_at`, `last_seen_at`. The alert manager de-duplicates signals of the same rule
  into one open alert and auto-resolves when the condition clears for a configured number of runs.

### 9.3 Deterioration index

A composite 0–100 **deterioration index** (severity-weighted, recency-decayed sum of active
signals) gives the portfolio a single sortable risk-of-decline number. Its formula is versioned
like everything else.

### 9.4 Evaluation harness — proving "earlier than traditional"

The synthetic generator emits for each deteriorating persona:
`ground_truth.onset_date` (when financial health actually starts to decline) and a **simulated
bureau stream** (`dpd_30`, `dpd_60`, `default` events, produced by a deterministic model of how a
bureau would record missed formal-credit payments, lagged by reporting cycles).

The backtest replays analysis at monthly (or weekly) `as_of` steps and reports:

- **lead time** = first FinPulse high-severity signal date − first simulated bureau event date,
- **precision / recall** of high-severity alerts against ground-truth deterioration,
- **false-alarm rate** on stable personas.

These metrics gate releases of rule/score changes (§13.1). Their limits are stated plainly in the
UI: they measure performance against *our generator's* model of deterioration, not real-world
validity.

## 10. Agent architecture

### 10.1 Design stance

- **Custom, small orchestration layer** — no LangChain/LangGraph/CrewAI/AutoGen. The workflow is a
  fixed, auditable DAG with one bounded debate loop; a framework would add abstraction over the one
  thing we must control tightly (what goes in and out of each LLM call). The core is expected to be
  a few hundred lines: an agent runner (tool-use loop), a workflow runner, and budgets.
- **LLM provider abstraction** (`llm/`) — a `LLMClient` protocol (`complete(messages, tools,
  output_schema, model, max_tokens, timeout) → LLMResponse`). One production adapter (configurable
  provider/model via env) and a **record/replay adapter for tests**. Native tool-calling and
  structured output are used where the provider supports them; output is always re-validated by
  Pydantic.
- **Prompts are versioned files** (`agents/prompts/<agent>/v<n>.md`), hashed and recorded on every
  step.

### 10.2 Agents

| Agent | Role | Tools (read-only) | Output schema |
|---|---|---|---|
| **Cash-Flow Analyst** | Interpret income, cash flow, liquidity patterns | `get_metrics`, `get_metric_timeseries`, `get_recurring_series`, `query_transactions` | `Findings` |
| **Obligations & Risk Investigator** | Explain signals/alerts, look for root causes (lost income source, new lenders, missed rent) | `get_signals`, `get_alert_history`, `get_obligation_events`, `query_transactions`, `get_metric_timeseries` | `Findings` |
| **Stress Analyst** | Assess resilience; may request scenario runs | `get_stress_results`, `run_stress_scenario` (deterministic engine), `get_passport` | `Findings` |
| **Business Analyst** *(business only)* | Revenue trend, concentration, receivables | `get_metrics(family=biz)`, `get_counterparty_breakdown`, `get_metric_timeseries` | `Findings` |
| **Synthesiser** | Merge findings into a coherent assessment answering the investigation question | none beyond reading findings + evidence pack | `DraftReport` |
| **Red Team** | Attack the draft: alternative explanations, data-quality artefacts (e.g. income moved to an unseen account), over-generalisation, unsupported or overstated claims, fairness concerns | same read tools as specialists (no `run_stress_scenario`) | `Challenges` |

Plus one **non-LLM** step:

| Step | Role |
|---|---|
| **Grounding Verifier** (deterministic) | Checks every claim: evidence refs exist and belong to this subject/run; numeric tokens match cited values within tolerance; claimed direction (rising/falling/above/below) matches the sign of the cited data; required caveats present for `insufficient_data` metrics. Produces `verified` / `rejected` / `unverifiable`. |

### 10.3 Structured outputs

```python
class EvidenceRef(BaseModel):
    kind: Literal["metric_value", "signal", "stress_result", "transaction", "obligation_event",
                  "passport_dimension"]
    id: UUID

class Claim(BaseModel):
    claim_id: str                      # agent-local, e.g. "c1"
    statement: str                     # natural language; any number must come from evidence
    claim_type: Literal["observation", "inference", "hypothesis", "recommendation"]
    evidence_refs: list[EvidenceRef]   # min 1 for observation/inference
    confidence: Literal["low", "medium", "high"]
    caveats: list[str] = []

class Findings(BaseModel):
    agent: str
    claims: list[Claim]
    open_questions: list[str]

class Challenge(BaseModel):
    target_claim_id: str
    challenge_type: Literal["alternative_explanation", "data_quality", "unsupported",
                            "overstated", "missing_context", "fairness"]
    argument: str
    evidence_refs: list[EvidenceRef]
    severity: Literal["minor", "major", "critical"]
```

`hypothesis` and `recommendation` claims may have zero evidence refs but are always rendered as
such (never as fact) and may not contain numbers.

### 10.4 Context given to agents: the evidence pack

Agents do **not** receive raw ledgers. They receive an **evidence pack** — an immutable JSON
snapshot built deterministically at the end of the analysis run: passport + dimensions + reason
codes, metric values (with IDs, units, quality), active signals/alerts, standard stress results,
recurring series summary and data-quality metrics. Detail beyond the pack is fetched via tools,
which return bounded, paginated results (e.g. `query_transactions` caps at 200 rows and returns
aggregates by default). The pack has a hash; every agent step records which pack hash it saw.

## 11. Orchestration flow (`orchestration/`)

### 11.1 Investigation workflow v1

```
           ┌──────────────────────────────┐
 trigger → │ 0. Preflight (deterministic) │  analysis run succeeded? evidence pack present?
           │    budget allocation          │  subject kind → which specialists run
           └──────────────┬───────────────┘
                          ▼
           ┌──────────────────────────────┐
           │ 1. Specialists (parallel)     │  Cash-Flow · Obligations/Risk · Stress · [Business]
           │    each: tool-use loop        │  ≤ 8 tool calls, ≤ N tokens, timeout each
           └──────────────┬───────────────┘
                          ▼
           ┌──────────────────────────────┐
           │ 2. Verify findings (determ.)  │  reject ungrounded claims before synthesis
           └──────────────┬───────────────┘
                          ▼
           ┌──────────────────────────────┐
           │ 3. Synthesiser → DraftReport  │  only verified claims are available to cite
           └──────────────┬───────────────┘
                          ▼
           ┌──────────────────────────────┐
           │ 4. Red Team → Challenges      │
           └──────────────┬───────────────┘
                          ▼
           ┌──────────────────────────────┐
           │ 5. Rebuttal round (max 1)     │  owning specialist: concede / defend with evidence /
           │                               │  revise claim. Unresolved → "disputed"
           └──────────────┬───────────────┘
                          ▼
           ┌──────────────────────────────┐
           │ 6. Final synthesis + verify   │  verifier runs again over the final report
           └──────────────┬───────────────┘
                          ▼
           ┌──────────────────────────────┐
           │ 7. Persist report             │  verified claims · disputed claims · rejected
           │                               │  claims (shown collapsed) · open questions ·
           │                               │  verification summary · cost/latency
           └──────────────────────────────┘
```

### 11.2 Mechanics

- **Workflow as data:** a workflow is a list of phases; each phase is a list of `StepSpec`s that run
  concurrently (`asyncio.gather` with per-step timeouts). Phase boundaries are persisted; a crashed
  worker resumes from the last completed phase (steps are idempotent by `(investigation_id,
  step_key)`).
- **Agent runner:** standard tool-use loop — call LLM → if tool calls, validate arguments with the
  tool's Pydantic schema, execute, append result → repeat until a final structured answer or budget
  exhaustion. Invalid structured output gets **one** repair attempt with the validation error
  attached; then the step fails.
- **Budgets:** per-step (tool calls, tokens, wall time) and per-investigation (total tokens, cost
  ceiling, max wall time 5 min). Exceeding a budget ends the step as `budget_exceeded`; the
  workflow continues with what it has and marks the report `partial`.
- **Streaming progress:** each persisted step transition emits an event row; the API exposes them
  over SSE (`/investigations/{id}/events`) so the UI shows the live trace.
- **Triggers:** manual (user asks a question) or automatic on a new high-severity alert
  (configurable, off by default to control cost).

## 12. Cross-cutting concerns

### 12.1 Error handling

**Error taxonomy** (`core/errors.py`), each mapped to an HTTP status and a stable `code`:

| Exception | HTTP | `code` example | Notes |
|---|---|---|---|
| `ValidationError` (Pydantic/request) | 422 | `validation_error` | field-level `errors[]` |
| `NotFound` | 404 | `subject_not_found` | |
| `Conflict` | 409 | `analysis_in_progress` | e.g. concurrent run for same subject/as_of |
| `PreconditionFailed` | 412 | `analysis_required` | investigation without a succeeded analysis |
| `InsufficientData` | 422 | `insufficient_history` | engines refuse rather than guess |
| `AuthError` / `Forbidden` | 401 / 403 | `invalid_token`, `forbidden` | |
| `RateLimited` | 429 | `rate_limited` | `Retry-After` header |
| `UpstreamLLMError` | 502 / 503 | `llm_unavailable` | only from investigation endpoints |
| unhandled | 500 | `internal_error` | no stack traces to clients; `request_id` returned |

All errors are returned as RFC 7807 `application/problem+json` with `type`, `title`, `status`,
`detail`, `code`, `request_id` (see `API_SPEC.md §3`).

**Engine-level rules:** engines raise typed domain errors or return quality-flagged `None`
values; they never swallow exceptions or substitute defaults.

**Job-level rules:** jobs have `max_attempts` (default 3) with exponential backoff for transient
errors (DB connection, LLM 5xx/timeout/429). Deterministic errors (validation,
`InsufficientData`) fail immediately — retrying them is pointless. Failed jobs keep `last_error`
and `failed_stage`.

**LLM-specific:** timeouts and retries with jitter in the adapter; schema-invalid output → one
repair attempt; persistent failure → step `failed`, investigation `partial` or `failed`; the
deterministic passport/signals remain fully available (R5).

### 12.2 Logging, tracing, audit

- **Structured JSON logs** via `structlog`, one event per line, with bound context:
  `request_id`, `user_id`, `org_id`, `subject_id`, `job_id`, `analysis_run_id`,
  `investigation_id`, `agent`, `step_key`. Context propagates into the worker via job payload.
- **Request logs:** method, route template (not raw path), status, latency.
- **Engine logs:** stage start/end, durations, row counts, versions — never raw transaction
  descriptions or amounts at INFO.
- **LLM call logs** (also persisted in `llm_calls`): provider, model, prompt version + hash,
  input/output tokens, latency, retry count, finish reason, cost estimate. Full prompts/responses
  are stored in the DB (`agent_steps`) for auditability, not in log streams.
- **PII policy:** synthetic only in MVP, but the logging processors already redact fields tagged
  sensitive (`description`, `counterparty_name`, account numbers) so the policy is in place before
  real data arrives.
- **Tracing:** OpenTelemetry-compatible spans around HTTP requests, jobs, engine stages and LLM
  calls; exporter disabled by default, enabled by env.
- **Audit log** (`audit_events` table): who ran/viewed/acknowledged what and when — analyses,
  investigations, alert state changes, scoring model changes.

### 12.3 Security & multi-tenancy

- Auth via **Supabase Auth JWTs** verified in FastAPI (JWKS, audience, expiry). A local dev mode
  uses a signed dev token; it is impossible to enable when `ENV=production`.
- Every business table has `org_id`; repositories always filter by the caller's org. Supabase **RLS
  policies** mirror this as defence-in-depth (documented in `DATA_MODEL.md`), but the API doesn't
  rely on RLS alone because it connects with a service role.
- LLM prompts include only the subject's evidence; tool calls are scoped to the investigation's
  `subject_id` and `analysis_run_id` server-side (the model cannot widen scope by argument).
- Prompt-injection resilience: transaction descriptions are data. They are passed inside clearly
  delimited JSON fields, truncated, and agent tools never expose an action with side effects
  beyond `run_stress_scenario` (which is itself deterministic and scoped).

### 12.4 Configuration

Pydantic `Settings` from env: `DATABASE_URL`, `SUPABASE_JWKS_URL`, `LLM_PROVIDER`, `LLM_MODEL_*`
(per agent role), `LLM_API_KEY`, budgets, `ENABLE_AUTO_INVESTIGATION`, `OTEL_*`. No secrets in
code or committed files; `.env.example` lists every variable.

## 13. Testing strategy

| Layer | What | How |
|---|---|---|
| **Metrics (unit)** | Each metric on hand-built ledgers with hand-computed expected values, incl. edge cases (no income, one month of history, all-negative balance) | pytest, table-driven |
| **Engines (property)** | Invariants: metrics independent of transaction order; scaling all amounts scales money metrics linearly and leaves ratios unchanged; self-transfers don't change income; score ∈ [0,100]; stress with zero shock ≈ baseline | Hypothesis |
| **Golden** | Each synthetic persona (fixed seed) → full analysis output snapshot; any diff requires a version bump + reviewed snapshot update | pytest snapshot files |
| **Synthetic generator** | Seed determinism; personas hit their target statistical profiles; ground-truth and bureau streams consistent | pytest |
| **Early-warning evaluation** | Backtest over the persona suite; assert lead time ≥ target and false-alarm rate ≤ target; regressions fail CI | pytest `-m evaluation` |
| **Verifier** | Adversarial cases: fabricated numbers, wrong-subject refs, sign flips, rounding edge cases, numbers spelled out in words, percentages vs ratios | pytest, table-driven |
| **Agents / orchestration** | Workflow with record/replay LLM fixtures: tool loop, budget exhaustion, invalid output repair, provider timeout → partial report, resume after crash | pytest + fixtures (no network) |
| **Live LLM evals** | Small suite against the real provider, scored on groundedness (verifier pass rate), coverage of reason codes, red-team usefulness | manual/nightly, not in PR CI |
| **API** | Route contracts, auth, error shape, pagination; OpenAPI snapshot | pytest + httpx `AsyncClient` against a real Postgres (testcontainers / CI service) |
| **DB** | Alembic upgrade/downgrade on empty DB; constraints | pytest |
| **Frontend unit** | Formatters, API error mapping, components with mock data | Vitest + Testing Library |
| **E2E** | Generate persona → run analysis → view passport → run stress → start investigation (replay LLM) | Playwright against docker-compose stack |
| **Static** | ruff, mypy (strict for engines), eslint, tsc, OpenAPI types up to date | CI |

**Test data rule:** tests never rely on the LLM for anything numeric, and the LLM is never called
from CI unit/integration runs.

### 13.1 Release gates

A change to metrics, scoring model, rules or scenarios must: bump the relevant version, update
golden snapshots in the same PR, and keep the early-warning evaluation within thresholds.

## 14. Key decisions (ADR summary)

| # | Decision | Alternative rejected | Reason |
|---|---|---|---|
| 1 | Deterministic engines are the only source of numbers; verifier enforces it | Let LLM compute/explain freely | Core product principle; auditability |
| 2 | Custom orchestration | LangGraph / CrewAI / AutoGen | Fixed DAG, small surface, full control and audit of each call |
| 3 | Postgres-backed job queue | Celery + Redis | Fewer moving parts; adequate for MVP load |
| 4 | Transparent rules-based scoring v1 | Gradient-boosted model | Synthetic data would teach the generator; explainability |
| 5 | Money as integer minor units + currency | Floats / NUMERIC everywhere | Exactness; simple JSON transport |
| 6 | Evidence pack + bounded tools | Raw ledger in prompt | Token cost, injection surface, reproducibility |
| 7 | Generated TS types from OpenAPI | Hand-written types | No contract drift |
| 8 | Synthetic generator emits ground truth + simulated bureau | Only synthetic transactions | Makes "earlier than traditional" measurable |
| 9 | Alembic owns schema; Supabase used as plain Postgres + Auth | Supabase migrations / client SDK in backend | Portability; one migration tool |

## 15. Out of scope for the MVP

Real bank/AA (Account Aggregator) integrations, automated lending decisions, learned scoring
models, real-time streaming ingestion, mobile apps, multi-currency conversion, vector search/RAG.
The architecture leaves seams for each (ingestion adapters, scoring model interface, jobs
interface) without building them.
