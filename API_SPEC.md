# FinPulse — API Specification

> Status: **design, not implemented.** This is the contract the FastAPI backend will expose and
> the Next.js frontend will consume. Once built, the generated OpenAPI document
> (`packages/contracts/openapi.json`) is authoritative and this file describes intent and conventions.

## 1. Boundaries

```
Browser ──▶ Next.js (apps/web) ──▶ FastAPI /api/v1 ──▶ engines / orchestrator ──▶ Postgres
                                                     └▶ LLM provider (worker only)
```

| Boundary | Rule |
|---|---|
| Browser ↔ Next.js | Session cookie (Supabase Auth). The browser may call `/api/v1` directly only for SSE and polling, with the same bearer token. |
| Next.js ↔ FastAPI | HTTPS JSON, bearer JWT forwarded. Next.js holds no financial logic and no DB credentials. |
| API ↔ engines | In-process Python calls through `services/`. Routers never call engines directly. |
| API ↔ LLM | **Never on the request path.** LLM calls happen only inside worker jobs. A request that needs agents returns `202` and a resource to poll/stream. |
| Agents ↔ data | Only via the agent tool layer (read-only, scoped server-side to one subject + analysis run). Not exposed over HTTP. |

## 2. Conventions

- **Base path:** `/api/v1` for all business endpoints. Breaking changes → `/api/v2`.
  Operational probes (`/health`, `/ready`) are unversioned at the root so infrastructure can
  reach them without knowing the API version.
- **Auth:** `Authorization: Bearer <JWT>` on every endpoint except `/health` and `/ready`.
  Roles: `viewer` (read), `analyst` (read + run analyses/stress/investigations + alert actions),
  `admin` (+ backtests, org settings).
- **Content type:** `application/json; charset=utf-8`. Errors: `application/problem+json`.
- **IDs:** UUID strings.
- **Money:** `{ "amount_minor": 1234500, "currency": "INR" }` — integer minor units. Never floats.
- **Metric values:** `value` is a decimal **string** to preserve precision, plus `unit`. INR
  metric values are rupees exact to the paisa (`"589345.00"`); ratios are fractions. `null` with
  `availability: "insufficient_data" | "not_applicable"` when not computable.
- **Dates:** `YYYY-MM-DD` for business dates; RFC 3339 UTC for timestamps.
- **Pagination:** cursor-based. `?limit=50&cursor=<opaque>`; response
  `{ "data": [...], "next_cursor": "..." | null }`. Max `limit` 200.
- **Async work:** `POST` that starts work returns `202 Accepted` with the created resource (status
  `queued`) and `Location` header. Poll the resource or `GET /jobs/{id}`.
- **Idempotency:** all `POST` creating work accept `Idempotency-Key` (24h window, scoped to user).
  Engine-level dedup also applies (same inputs + versions ⇒ same run returned with `200`).
- **Request tracing:** clients may send `X-Request-ID`; the server always returns one.
- **Rate limits:** per-user token bucket; investigations have a tighter limit (default 10/hour).
  `429` + `Retry-After`.
- **Versions in payloads:** every engine result includes the versions that produced it.

## 3. Error format (RFC 7807)

```json
{
  "type": "https://finpulse.dev/errors/analysis-required",
  "title": "Analysis required",
  "status": 412,
  "code": "analysis_required",
  "detail": "Subject 5b1e… has no succeeded analysis run as of 2026-09-30.",
  "request_id": "req_01J9…",
  "errors": []
}
```

`errors[]` is populated for `422 validation_error`: `[{ "loc": ["body","horizon_months"],
"msg": "must be ≤ 24", "type": "less_than_equal" }]`.

| Status | Codes |
|---|---|
| 400 | `bad_request`, `invalid_cursor` |
| 401 | `missing_token`, `invalid_token`, `token_expired` |
| 403 | `forbidden` |
| 404 | `<resource>_not_found` |
| 409 | `analysis_in_progress`, `idempotency_key_reused`, `invalid_state_transition` |
| 412 | `analysis_required`, `analysis_not_succeeded` |
| 422 | `validation_error`, `insufficient_history`, `scenario_not_applicable` |
| 429 | `rate_limited` |
| 500 | `internal_error` |
| 502/503 | `llm_unavailable`, `dependency_unavailable` |

## 4. Endpoints

### 4.1 System

`/health` and `/ready` are at the root (no `/api/v1` prefix); `/me` is versioned.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness. `200 {"status":"ok","service","version","environment","timestamp"}`. Never touches dependencies. **Implemented.** |
| GET | `/ready` | Readiness: `{status: "ready"\|"not_ready", checks: [{name, status, latency_ms, detail}]}`; `503` when any check fails. **Implemented** with the database check; migrations-at-head and registry-synced checks are added when those exist. |
| GET | `/me` | Current user, org, role |

### 4.2 Methodology registry (read-only, from code-synced reference tables)

| Method | Path | Description |
|---|---|---|
| GET | `/meta/metrics` | All metric definitions (latest version unless `?version=all`) |
| GET | `/meta/metrics/{code}` | One metric: description, formula notes, unit, direction, window, versions |
| GET | `/meta/scoring-model` | Active scoring model: dimensions, weights, breakpoints, bands (`?version=`) |
| GET | `/meta/early-warning-rules` | Rules and detectors with thresholds |
| GET | `/meta/stress-scenarios` | Scenarios with `params_schema` (JSON Schema) and defaults |
| GET | `/meta/personas` | Synthetic personas available for generation, with descriptions |

`GET /meta/metrics/liq.buffer_days`
```json
{
  "code": "liq.buffer_days", "version": 1, "name": "Liquidity buffer",
  "family": "liquidity", "unit": "days", "direction": "higher_is_better",
  "window": "trailing_90d", "applies_to": ["individual", "business"],
  "description_md": "Average end-of-day balance ÷ average daily essential outflow …"
}
```

### 4.3 Subjects & synthetic data

| Method | Path | Description |
|---|---|---|
| GET | `/subjects` | List. Filters: `kind`, `segment`, `band`, `has_open_alerts`, `q`. Sort: `created_at`, `overall_score`, `deterioration_index`. |
| GET | `/subjects/{id}` | Subject with latest passport summary |
| DELETE | `/subjects/{id}` | Soft delete (admin) |
| POST | `/synthetic/generations` | Generate a synthetic subject + accounts + transactions (async) |
| GET | `/synthetic/generations/{id}` | Status, persona, seed, params. Ground truth only for `admin` (it's evaluation data). |

`POST /synthetic/generations`
```json
{
  "persona_code": "kirana_store",
  "seed": 4211,
  "months_of_history": 18,
  "end_date": "2026-09-30",
  "deterioration": { "enabled": true, "mechanism": "top_customer_loss", "onset_month_offset": -4 },
  "auto_analyze": true
}
```
`202` →
```json
{ "id": "…", "status": "queued", "subject_id": "…", "job_id": "…" }
```

### 4.3a Entities and financial metrics *(implemented)*

"Entity" is the API name for a subject (a person or business). These routes are live; the full
metric definitions are in [docs/FINANCIAL_METRICS.md](docs/FINANCIAL_METRICS.md).

| Method | Path | Description |
|---|---|---|
| GET | `/entities` | Entities in the caller's organisation: `id`, `display_name`, `kind`, `segment`, `data_origin` |
| GET | `/entities/{entity_id}/financial-metrics` | Full report: `entity`, `as_of`, `currency`, `engine_version`, `coverage`, `metrics[]` (25), `series[]` (monthly revenue, expenses, net cash flow, month-end balance). Optional `?as_of=YYYY-MM-DD` (default: end of the data). |
| GET | `/entities/{entity_id}/financial-metrics/history` | Metric values recomputed at each month-end: `metrics[]` (definitions), `points[]` (`as_of`, `values{code: value|null}`). `?months=12` (1–24), repeatable `?codes=` (default: all), optional `?as_of=`. Used by the frontend's history charts; the UI never derives values itself |
| GET | `/entities/{entity_id}/financial-metrics/{metric_code}` | One metric |
| GET | `/meta/financial-metrics` | Metric definitions: code, name, family, unit, version, method |

Errors: `404 entity_not_found` · `404 metric_not_found` (lists known codes in `extra.known`) ·
`422 insufficient_history` (no data on or before `as_of`) · `422 validation_error` (malformed
id or date) · `503 database_unavailable` (with `Retry-After`).

Metrics are computed at request time from stored records. Persisted analysis runs (§4.5) come
later; until authentication exists, every request is scoped to the demo organisation.

### 4.4 Raw data

| Method | Path | Description |
|---|---|---|
| GET | `/subjects/{id}/accounts` | Accounts |
| GET | `/subjects/{id}/transactions` | Paginated ledger. Filters: `from`, `to`, `account_id`, `category`, `direction`, `counterparty_id`, `recurring_series_id`. |
| GET | `/subjects/{id}/recurring-series` | Latest detected series (`?analysis_run_id=` for a specific run) |
| GET | `/subjects/{id}/obligation-events` | On-time/late/missed history |

Transaction item:
```json
{
  "id": "…", "account_id": "…", "posted_on": "2026-08-03",
  "amount": { "amount_minor": -1250000, "currency": "INR" },
  "description": "UPI/RENT/…", "channel": "upi",
  "category": "housing.rent", "category_source": "rule",
  "counterparty": { "id": "…", "name": "Landlord – S. Verma", "kind": "landlord" },
  "recurring_series_id": "…", "transfer_pair_id": null
}
```

### 4.5 Analysis runs

| Method | Path | Description |
|---|---|---|
| POST | `/subjects/{id}/analyses` | Start an analysis run. Body `{ "as_of": "2026-09-30" }` (default: latest transaction date). `202`, or `200` if an identical fingerprint already succeeded. `409 analysis_in_progress` if one is running for that as_of. |
| GET | `/subjects/{id}/analyses` | Run history |
| GET | `/analyses/{run_id}` | Status, `failed_stage`, versions, timings |
| GET | `/subjects/{id}/analyses/latest` | Latest succeeded run |

### 4.6 Metrics

| Method | Path | Description |
|---|---|---|
| GET | `/analyses/{run_id}/metrics` | Headline metric values. Filter `family`. |
| GET | `/subjects/{id}/metrics/{code}/series` | Time series of a metric across periods (from latest run unless `analysis_run_id`). |

Metric value:
```json
{
  "id": "…", "metric_code": "obl.on_time_rate_12m", "metric_version": 1,
  "period_start": "2025-10-01", "period_end": "2026-09-30",
  "value": "0.916667", "unit": "ratio", "quality": "ok",
  "lineage": { "obligation_event_count": 24, "series_ids": ["…", "…"] }
}
```

### 4.7 Financial Passport

**Implemented (Phase 3), computed per request:**

| Method | Path | Description |
|---|---|---|
| GET | `/entities/{entity_id}/passport` | Financial Health score, band, confidence, provisional flag; six dimensions with factor-level points, weights, contributions and explanations; strengths and concerns; `change_from_previous_month`; model version and config hash; `disclaimer`. Optional `?as_of=`. |
| GET | `/entities/{entity_id}/passport/history` | Passport at each month-end, then `as_of` (`?months=1..24`, default 12), with each step's change explained |
| GET | `/meta/passport-model` | The scoring configuration (dimensions, weights, curves, bands, disclaimer) |

Methodology: [docs/FINANCIAL_PASSPORT.md](docs/FINANCIAL_PASSPORT.md). A prototype financial-health
profile, **not a credit score**. The run-based endpoints below follow once analysis runs are
persisted.

| Method | Path | Description |
|---|---|---|
| GET | `/analyses/{run_id}/passport` | Passport for a run |
| GET | `/subjects/{id}/passport` | Latest passport |
| GET | `/subjects/{id}/passport/history` | Overall + dimension scores over runs |

```json
{
  "id": "…", "analysis_run_id": "…", "scoring_model_version": 1,
  "overall_score": "64.20", "band": "C", "confidence": "0.780",
  "deterioration_index": "41.00",
  "dimensions": [
    {
      "dimension": "obligation_discipline", "score": "52.00", "confidence": "0.900",
      "weight": "0.2000",
      "factors": [
        { "metric_value_id": "…", "metric_code": "obl.late_count_6m",
          "sub_score": "35.00", "weight": "0.40", "contribution_points": "-6.00" }
      ]
    }
  ],
  "reason_codes": [
    { "code": "OBL_LATE_PAYMENTS_RECENT", "direction": "negative", "points": "-6.00",
      "dimension": "obligation_discipline" }
  ]
}
```

### 4.8 Early warnings

**Implemented (Phase 4, first part), computed per request:**

| Method | Path | Description |
|---|---|---|
| GET | `/entities/{entity_id}/warnings` | Warnings detected by the deterministic rules. Each has `id`, `category`, `severity`, `title`, `description`, `evidence`, `affected_metric`, `current_value`, `previous_value`, `threshold` and `detected_at`, plus trend, status and `first_detected_on`. Also the state of every rule. Filters: `as_of`, `min_severity`, `category`. |
| GET | `/entities/{entity_id}/risk-summary` | Risk level and 0–100 early-warning index, categories, top warnings, trend against 3 months earlier, and a 12-month timeline. Optional `?as_of=`. |
| GET | `/meta/early-warning-rules` | Every rule with its configured tiers and windows, plus the summary points and levels |

Methodology: [docs/EARLY_WARNING.md](docs/EARLY_WARNING.md). No LLM decides whether a warning
exists. The persisted signals, alerts and lifecycle below follow later.

| Method | Path | Description |
|---|---|---|
| GET | `/analyses/{run_id}/signals` | Signals detected in a run |
| GET | `/alerts` | Portfolio alerts. Filters: `state`, `severity`, `subject_id`, `rule_code`. |
| GET | `/subjects/{id}/alerts` | Alerts for a subject |
| GET | `/alerts/{id}` | Alert with its signal history |
| PATCH | `/alerts/{id}` | `{ "state": "acknowledged" | "resolved", "note": "…" }`. Invalid transitions → `409 invalid_state_transition`. Audited. |

### 4.9 Stress testing

**Implemented (Phase 5), computed per request:**

| Method | Path | Description |
|---|---|---|
| POST | `/entities/{entity_id}/stress-test` | Run a preset or custom shocks. Returns the baseline and stressed projections, comparisons (absolute and % change), risk change, health impact and evidence |
| GET | `/meta/stress-scenarios` | The six shock types with their parameter JSON Schemas, and the ten presets |

```json
{ "preset": "revenue_down_20" }
{
  "shocks": [
    { "type": "customer_payment_stop", "days": 45 },
    { "type": "new_debt", "principal": "200000", "annual_rate": "0.2", "tenor_months": 12 }
  ],
  "horizon_months": 9,
  "as_of": "2026-06-30"
}
```

The request takes exactly one of `preset` or `shocks` (1–10, applied in order). `horizon_months`
is 1–24 (default 6). Unknown presets, types or fields, and out-of-range parameters return `422
validation_error`. A shock that cannot apply (no suppliers, unknown `customer_id`, start beyond
the horizon) returns `422 scenario_not_applicable`. An unknown entity returns `404`.
Methodology: [docs/STRESS_TESTING.md](docs/STRESS_TESTING.md).

The run-based design below (persisted runs, Monte Carlo paths) follows later.

| Method | Path | Description |
|---|---|---|
| POST | `/subjects/{id}/stress-tests` | Run a scenario against the latest (or given) analysis run |
| GET | `/subjects/{id}/stress-tests` | History (incl. standard-set runs) |
| GET | `/stress-tests/{id}` | Status + result |

```json
{
  "analysis_run_id": null,
  "scenario_code": "income_shock",
  "params": { "pct": 40, "months": 3, "start_offset": 0 },
  "horizon_months": 6,
  "paths": 500,
  "seed": 7
}
```
`params` is validated against the scenario's `params_schema`; `422 scenario_not_applicable` for e.g.
`top_customer_loss` on an individual. Result shape mirrors `stress_test_results` (DATA_MODEL §3.6).

### 4.10 Investigations (agents)

**Implemented (Phases 7–8, first part), synchronous:**

| Method | Path | Description |
|---|---|---|
| GET | `/entities/{entity_id}/evidence-pack` | The verified evidence the agents read: citable items of kind fact, calculated_metric, forecast or assumption. Deterministic (no AI). Optional `?as_of=` |
| POST | `/entities/{entity_id}/investigate` | Runs the full investigation workflow and returns the `Investigation` record. Body `{"as_of"?}`. No free-text questions. See [docs/INVESTIGATIONS.md](docs/INVESTIGATIONS.md). The record contains: <ul><li>stages with timestamps</li><li>triggered warnings and the metrics used</li><li>agent analyses</li><li>disagreements and red-team findings</li><li>the final assessment, separated into FACT / CALCULATED_METRIC / FORECAST / ASSUMPTION / AI_INTERPRETATION</li><li>recommendations and confidence</li><li>evidence references, the claim audit and the event log</li></ul> |
| POST | `/entities/{entity_id}/investigations` | Starts the same workflow in the background and returns `202` with an `InvestigationProgress`. Body `{"as_of"?}` |
| GET | `/investigations/{id}/progress` | Live state of a background run, built from the orchestrator's real events: `status` (running · completed · failed), `current_stage`, completed `stages[]`, per-agent `agents[]` (pending · running · succeeded · failed · skipped, claims, attempts), `events[]`, `error{code,message}`. When completed the full record is at `/investigations/{id}`. `404 investigation_not_found` |
| GET | `/investigations` · `/investigations/{id}` · `/investigations/{id}/events` | Recent investigations (in memory; `?entity_id=` filters), one record, its event log. `404 investigation_not_found` |
| POST | `/entities/{entity_id}/agents/{agent_name}` | One agent, plus the agents whose findings it needs. `404 agent_not_found` |
| GET | `/meta/agents` | Agents, dependencies, prompt versions, output schemas |

`503 llm_unavailable` when no model is configured or reachable (for a background run, the progress
reports `status: failed` with `error.code: llm_unavailable` after the deterministic stages). Methodology:
[docs/AI_AGENTS.md](docs/AI_AGENTS.md). The persisted, asynchronous investigations below follow.

| Method | Path | Description |
|---|---|---|
| POST | `/subjects/{id}/investigations` | Start. `412 analysis_required` without a succeeded analysis. |
| GET | `/subjects/{id}/investigations` | History |
| GET | `/investigations/{id}` | Status, phase, usage, budget |
| GET | `/investigations/{id}/steps` | Agent steps with tool calls (prompt text only for `admin`) |
| GET | `/investigations/{id}/claims` | Claims with verification checks and challenges |
| GET | `/investigations/{id}/report` | Final report (`404` until complete; `is_partial` flag) |
| GET | `/investigations/{id}/events` | **SSE** stream of `investigation_events`; supports `Last-Event-ID` |
| POST | `/investigations/{id}/cancel` | Cooperative cancel at next step boundary |

`POST /subjects/{id}/investigations`
```json
{
  "question": "Is this business's financial health deteriorating, and why?",
  "analysis_run_id": null,
  "trigger_alert_id": null
}
```

SSE frame:
```
id: 1842
event: step_completed
data: {"step_key":"specialist.cash_flow","status":"succeeded","claims":5,"tool_calls":4}
```

Claim item:
```json
{
  "id": "…", "agent": "obligations_risk", "claim_type": "observation",
  "statement": "Rent was paid late in 2 of the last 3 months, after 14 months on time.",
  "evidence_refs": [{ "kind": "metric_value", "id": "…" }, { "kind": "signal", "id": "…" }],
  "confidence": "high", "caveats": [],
  "final_status": "verified",
  "verification": { "result": "verified", "verifier_version": 1,
    "checks": [{ "check": "numeric_match", "passed": true, "detail": "2 ↔ obl.late_count_3m=2" }] },
  "challenges": []
}
```

### 4.11 Evidence resolution

| Method | Path | Description |
|---|---|---|
| GET | `/evidence/{kind}/{id}` | Resolve any evidence ref (`metric_value`, `signal`, `stress_result`, `transaction`, `obligation_event`, `passport_dimension`) to a display payload. Scoped to caller's org. |

### 4.12 Portfolio

| Method | Path | Description |
|---|---|---|
| GET | `/portfolio/summary` | Counts by kind/band, open alerts by severity, top deterioration-index subjects |

### 4.13 Jobs

| Method | Path | Description |
|---|---|---|
| GET | `/jobs/{id}` | `{ id, kind, status, attempts, last_error, result_ref }` |

### 4.14 Evaluation (admin)

| Method | Path | Description |
|---|---|---|
| POST | `/evaluation/backtests` | Run early-warning backtest over a persona cohort `{ personas:[…], seeds:[…], step:"monthly" }` → `202` |
| GET | `/evaluation/backtests/{id}` | Lead-time distribution, precision/recall, false-alarm rate, per-subject detail |

## 5. Agent tool contract (internal, not HTTP)

Listed here because it is an API boundary in its own right. All tools: Pydantic arguments, scoped
server-side to `(org_id, subject_id, analysis_run_id)`, bounded output, every returned item carries
its evidence ID.

| Tool | Arguments | Returns |
|---|---|---|
| `get_passport` | — | Passport + dimensions + reason codes |
| `get_metrics` | `family?`, `codes?[]` | Headline metric values |
| `get_metric_timeseries` | `code`, `periods? ≤ 24` | Series points |
| `get_signals` | `severity_min?` | Signals in run |
| `get_alert_history` | `rule_code?` | Alerts + state history |
| `get_recurring_series` | `direction?`, `kind?` | Series summaries |
| `get_obligation_events` | `series_id?`, `status?`, `limit ≤ 100` | Events |
| `query_transactions` | `from?`, `to?`, `category?`, `counterparty_id?`, `group_by? (month|category|counterparty)`, `limit ≤ 200` | Aggregates by default; rows only when `group_by` is null |
| `get_counterparty_breakdown` | `direction`, `top_n ≤ 20` | Share by counterparty |
| `get_stress_results` | `scenario_code?` | Existing results |
| `run_stress_scenario` | `scenario_code`, `params`, `horizon_months ≤ 12` | Runs the deterministic engine (seed fixed by server), persists, returns result + ID. Max 3 per investigation. |

## 6. OpenAPI & type generation

- FastAPI generates OpenAPI 3.1; `npm run contracts:generate` exports it to
  `packages/contracts/openapi.json` and runs `openapi-typescript` →
  `packages/contracts/src/schema.gen.ts`, consumed by the web app as `@finpulse/contracts`.
- CI regenerates both and fails if either differs from what's committed (contract drift check).
