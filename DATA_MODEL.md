# FinPulse — Data Model

> Status: **design, not implemented.** Target PostgreSQL schema for the MVP. Alembic migrations in
> `apps/api/alembic/` will be the executable source of truth once built; this document is the
> design they implement.

## 1. Conventions

| Convention | Rule |
|---|---|
| Database | PostgreSQL 15+. Supabase-compatible: plain Postgres features only (no extensions beyond `pgcrypto`). Runs on local Docker Postgres or a Supabase project unchanged. |
| Schema | `public` for application tables. Supabase's `auth` schema is referenced only via `users.auth_user_id` (no FK across schemas, so the app also runs without Supabase). |
| Primary keys | `id uuid primary key default gen_random_uuid()` |
| Timestamps | `created_at timestamptz not null default now()`, `updated_at` where rows are mutable. Business dates (`posted_on`, `as_of`) are `date`. |
| Money | `*_minor bigint` (paise/cents) + `currency char(3)`. Signed where direction matters (`amount_minor` < 0 = outflow). Never `float`. |
| Ratios/scores | `numeric(12,6)` for metric values; `numeric(5,2)` for 0–100 scores; `numeric(4,3)` for 0–1 confidence. |
| Enums | Postgres `text` + `check` constraints (easier to migrate than native enums). Listed per table. |
| Tenancy | Every business table carries `org_id uuid not null`. All repository queries filter on it. |
| Immutability | Results of engines (`metric_values`, `passports`, `signals`, `stress_test_results`, `evidence_packs`, `claims`) are **append-only**. Corrections create new runs, never updates. |
| Versioning | Every engine output stores the version of the code/model that produced it (`metric_version`, `scoring_model_version`, `rule_version`, `scenario_version`, `prompt_version`, `workflow_version`). |
| Soft delete | Only on `subjects` (`deleted_at`). Engine outputs are never deleted except by retention jobs. |
| JSONB | Used for lineage, parameters, structured agent output and payloads that are read whole. Anything filtered or joined on is a real column. |

## 2. Entity overview

```
organizations ─┬─ users (org_members)
               │
               └─ subjects ─┬─ accounts ── transactions ── counterparties
                            │                 │
                            │                 └─ recurring_series ── obligation_events
                            │
                            ├─ synthetic_generations (ground truth) ── simulated_bureau_events
                            │
                            ├─ analysis_runs ─┬─ metric_values
                            │                 ├─ passports ── passport_dimensions
                            │                 ├─ signals ──▶ alerts (lifecycle across runs)
                            │                 ├─ evidence_packs
                            │                 └─ stress_test_runs ── stress_test_results
                            │
                            └─ investigations ─┬─ agent_steps ─┬─ tool_calls
                                               │               └─ llm_calls
                                               ├─ claims ── claim_verifications
                                               ├─ challenges
                                               ├─ investigation_events (SSE feed)
                                               └─ reports

reference: metric_definitions · scoring_models · early_warning_rules · stress_scenarios
infra:     jobs · audit_events · backtest_runs
```

## 3. Tables

### 3.1 Tenancy & identity

**`organizations`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| name | text not null | |
| default_currency | char(3) not null default 'INR' | |
| created_at | timestamptz | |

**`users`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id | uuid FK → organizations | |
| auth_user_id | uuid unique not null | Supabase `auth.users.id` (or dev stub subject) |
| email | text not null | |
| role | text check in (`admin`,`analyst`,`viewer`) | |
| created_at | timestamptz | |

### 3.2 Subjects and raw financial data

**`subjects`** — a person or business being assessed.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id | uuid FK | |
| kind | text check in (`individual`,`business`) | |
| display_name | text not null | Synthetic name |
| segment | text | e.g. `gig_worker`, `salaried_thin_file`, `kirana_store`, `freelancer`, `seasonal_business` |
| profile | jsonb | Non-sensitive descriptors (business sector, months of history). **No protected attributes.** |
| data_origin | text check in (`synthetic`,`imported`) default `synthetic` | |
| latest_analysis_run_id | uuid null FK → analysis_runs | Denormalised pointer for list views |
| created_at, updated_at, deleted_at | timestamptz | |

Index: `(org_id, kind)`, `(org_id, created_at desc)`.

**`accounts`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id | uuid FK | |
| kind | text check in (`bank_savings`,`bank_current`,`wallet`,`upi`,`card`,`loan`) | |
| institution | text | Synthetic institution label |
| currency | char(3) | |
| opened_on | date | |
| masked_number | text | e.g. `XXXX1234` |
| created_at | timestamptz | |

**`counterparties`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id | uuid FK | Counterparties are per subject in the MVP |
| normalized_name | text not null | |
| kind | text check in (`employer`,`platform`,`customer`,`supplier`,`landlord`,`utility`,`lender`,`merchant`,`government`,`self`,`unknown`) | |
| aliases | text[] | Raw strings that normalised to this |
| unique | (subject_id, normalized_name) | |

**`transactions`** — the ledger. Largest table.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id, account_id | uuid FK | `subject_id` denormalised for query speed |
| posted_on | date not null | |
| posted_at | timestamptz null | When time-of-day is known |
| amount_minor | bigint not null | Signed: + inflow, − outflow; `<> 0` |
| currency | char(3) not null | |
| balance_after_minor | bigint null | If source provides it |
| description | text | Raw narration (treated as untrusted text) |
| channel | text check in (`upi`,`neft`,`imps`,`card`,`cash`,`wallet`,`ach`,`cheque`,`other`) | |
| counterparty_id | uuid null FK | Set by normalisation |
| category | text null | e.g. `income.salary`, `income.platform_payout`, `housing.rent`, `debt.emi`, `utilities.electricity`, `spend.groceries`, `spend.gambling`, `transfer.self` |
| category_source | text check in (`rule`,`synthetic_label`,`manual`) | |
| category_confidence | numeric(4,3) | |
| transfer_pair_id | uuid null | Links the two legs of a self-transfer |
| recurring_series_id | uuid null FK | |
| external_ref | text | Source-side ID; unique per account |
| ingestion_batch_id | uuid not null | Which load/generation produced it |
| created_at | timestamptz | |

Constraints & indexes: `unique (account_id, external_ref)`; `(subject_id, posted_on)`;
`(subject_id, category, posted_on)`; `(counterparty_id)`.
Partitioning: not in MVP. Seam: range partition by `posted_on` if > ~50M rows.

**`quarantined_transactions`** — raw rows that failed validation (`raw jsonb`, `reason text`,
`ingestion_batch_id`). Never silently dropped.

**`recurring_series`** — detected regular flows (income or obligations).

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id | uuid FK | |
| analysis_run_id | uuid FK | Series are re-detected per run (append-only) |
| counterparty_id | uuid FK null | |
| direction | text check in (`inflow`,`outflow`) | |
| kind | text check in (`salary`,`platform_payout`,`customer_revenue`,`rent`,`utility`,`emi`,`subscription`,`supplier`,`other`) | |
| cadence | text check in (`weekly`,`biweekly`,`monthly`,`quarterly`,`irregular`) | |
| expected_amount_minor | bigint | Median |
| amount_tolerance_pct | numeric(5,2) | |
| expected_day | smallint null | Day of month / weekday |
| first_seen_on, last_seen_on | date | |
| is_active | boolean | Expected occurrence not missing beyond grace |
| detector_version | int | |

**`obligation_events`** — one per expected occurrence of an outflow series.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id, recurring_series_id, analysis_run_id | uuid FK | |
| due_on | date | Inferred |
| paid_on | date null | |
| transaction_id | uuid null FK | |
| amount_minor | bigint null | |
| status | text check in (`on_time`,`late`,`missed`,`partial`,`pending`) | |
| days_late | int null | |

### 3.3 Synthetic data & evaluation ground truth

**`synthetic_generations`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id | uuid FK | |
| persona_code | text | e.g. `gig_worker_stable`, `kirana_deteriorating` |
| generator_version | int | |
| seed | bigint not null | Reproducibility |
| params | jsonb | months of history, income level, deterioration config |
| ground_truth | jsonb | `{ "deteriorates": bool, "onset_date": date?, "mechanism": "income_loss|loan_stacking|customer_loss|…" }` |
| status | text | `pending`/`succeeded`/`failed` |
| created_at | timestamptz | |

**`simulated_bureau_events`** — what a traditional bureau would have recorded. **Evaluation only**;
never an input to engines (enforced: engines' repositories don't read this table, tested).

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id, synthetic_generation_id | uuid FK | |
| event_type | text check in (`account_opened`,`dpd_30`,`dpd_60`,`dpd_90`,`default`,`closed`) | |
| event_on | date | Reporting date (lagged) |
| reported_on | date | |

**`backtest_runs`** — early-warning evaluation results.

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id | uuid | |
| engine_versions | jsonb | metric/rule/scoring versions under test |
| cohort | jsonb | persona codes + seeds |
| step | text check in (`weekly`,`monthly`) | |
| results | jsonb | per-subject first-alert date, bureau date, lead days; aggregate precision/recall/false-alarm |
| status, created_at, completed_at | | |

### 3.4 Reference / registry tables

Code is the source of truth for definitions; on startup the registry is **synced** into these
tables (insert new versions, never mutate old ones) so that every stored result can be joined to a
human-readable definition of the exact version that produced it.

**`metric_definitions`**: `(code, version)` PK · `name` · `family` · `unit` (`minor_currency`,
`ratio`, `percent`, `days`, `count`, `months`, `score`) · `direction` (`higher_is_better`,
`lower_is_better`, `neutral`) · `window` · `applies_to text[]` · `description_md` · `created_at`.

**`scoring_models`**: `version` PK · `definition jsonb` (weights, breakpoints, bands) ·
`definition_hash` · `is_active` · `created_at`.

**`early_warning_rules`**: `(code, version)` PK · `name` · `severity` · `definition jsonb` ·
`description_md`.

**`stress_scenarios`**: `(code, version)` PK · `name` · `params_schema jsonb` (JSON Schema) ·
`default_params jsonb` · `applies_to text[]` · `is_standard boolean` (part of the Resilience set) ·
`description_md`.

### 3.5 Analysis results

**`analysis_runs`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id | uuid FK | |
| as_of | date not null | |
| status | text check in (`queued`,`running`,`succeeded`,`failed`) | |
| failed_stage | text null | `load`,`normalise`,`recurring`,`metrics`,`passport`,`signals`,`evidence` |
| error | jsonb null | `{code, message}` |
| input_fingerprint | text not null | sha256 (see ARCHITECTURE §5.2) |
| engine_versions | jsonb not null | `{ingestion, recurring, metrics:{code:ver}, scoring_model, rules:{code:ver}, scenarios:{…}}` |
| stage_timings_ms | jsonb | |
| triggered_by | uuid null FK → users | null = system/backtest |
| job_id | uuid FK → jobs | |
| started_at, completed_at, created_at | timestamptz | |

Constraints: `unique (subject_id, as_of, input_fingerprint)`; partial unique index on
`(subject_id, as_of) where status in ('queued','running')` to prevent concurrent duplicate runs.

**`metric_values`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | Referenced by agents as evidence |
| org_id, subject_id, analysis_run_id | uuid FK | |
| metric_code | text | |
| metric_version | int | FK (code, version) → metric_definitions |
| period_start, period_end | date | Window this value covers. Time series = many rows with different periods. |
| is_headline | boolean | The value for the run's `as_of` window (vs. historical series points) |
| value | numeric(18,6) null | Null when not computable |
| unit | text | |
| quality | text check in (`ok`,`insufficient_data`,`degraded`) | |
| lineage | jsonb | `{txn_count, series_ids[], window, params}` |
| created_at | timestamptz | |

Indexes: `(analysis_run_id, metric_code)`, `(subject_id, metric_code, period_end)`.

**`passports`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id, analysis_run_id | uuid FK | unique (analysis_run_id) |
| scoring_model_version | int FK | |
| overall_score | numeric(5,2) | 0–100 |
| band | text check in (`A`,`B`,`C`,`D`,`E`) | |
| confidence | numeric(4,3) | 0–1 |
| reason_codes | jsonb | `[{code, direction:"positive|negative", points, dimension}]` ordered |
| deterioration_index | numeric(5,2) | From early-warning engine |
| created_at | timestamptz | |

**`passport_dimensions`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| passport_id | uuid FK | |
| dimension | text check in (`income_stability`,`cash_flow_health`,`liquidity_buffer`,`obligation_discipline`,`spending_behaviour`,`resilience`,`business_vitality`) | |
| score | numeric(5,2) null | Null if no inputs available |
| confidence | numeric(4,3) | |
| weight | numeric(5,4) | Effective (renormalised) weight in overall |
| factors | jsonb | `[{metric_value_id, metric_code, sub_score, weight, contribution_points}]` |

unique `(passport_id, dimension)`.

**`signals`** (immutable detections per run)

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id, analysis_run_id | uuid FK | |
| rule_code, rule_version | text, int | |
| detector_type | text check in (`rule`,`cusum`,`robust_z`,`slope_change`) | |
| severity | text check in (`low`,`medium`,`high`) | |
| detected_on | date | Date condition first held within this run's data |
| window_start, window_end | date | |
| evidence | jsonb | `{metric_value_ids[], transaction_ids[], obligation_event_ids[], observed, threshold}` |
| alert_id | uuid FK → alerts | |

**`alerts`** (lifecycle across runs)

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id | uuid FK | |
| rule_code | text | |
| severity | text | Max severity seen while open |
| state | text check in (`open`,`acknowledged`,`resolved`) | |
| first_detected_on, last_seen_on | date | |
| resolved_reason | text null check in (`condition_cleared`,`manual`) | |
| acknowledged_by, resolved_by | uuid null FK → users | |
| note | text null | Analyst note |
| updated_at, created_at | timestamptz | |

Partial unique index: `(subject_id, rule_code) where state <> 'resolved'` — one live alert per
rule per subject.

**`evidence_packs`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id, analysis_run_id | uuid FK | unique (analysis_run_id) |
| schema_version | int | |
| content | jsonb | See ARCHITECTURE §10.4 |
| content_hash | text | sha256 of canonical JSON |
| created_at | timestamptz | |

### 3.6 Stress testing

**`stress_test_runs`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id, analysis_run_id | uuid FK | Baseline it projects from |
| scenario_code, scenario_version | text, int | |
| params | jsonb | Validated against scenario `params_schema` |
| horizon_months | smallint check 1–24 | |
| paths | int check 1–2000 | |
| seed | bigint | |
| origin | text check in (`standard_set`,`user`,`agent`) | |
| requested_by_user_id | uuid null | |
| requested_by_agent_step_id | uuid null FK | |
| engine_version | int | |
| status | text (`queued`,`running`,`succeeded`,`failed`) | |
| error | jsonb null | |
| job_id | uuid FK | |
| created_at, completed_at | timestamptz | |

Unique `(analysis_run_id, scenario_code, scenario_version, params_hash, horizon_months, paths,
seed)` — identical requests return the existing result (dedup, determinism).

**`stress_test_results`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| stress_test_run_id | uuid FK unique | |
| p_balance_below_zero | numeric(5,4) | |
| p_missed_obligation | numeric(5,4) | |
| median_runway_months | numeric(5,2) null | null = no breach within horizon |
| min_balance_p5_minor | bigint | |
| worst_month_index | smallint | |
| balance_bands | jsonb | `[{month, p5, p25, p50, p75, p95}]` minor units |
| baseline_bands | jsonb | Same, without shock |
| stressed_dimensions | jsonb | `[{dimension, baseline, stressed, delta}]` |

### 3.7 Investigations (agent layer)

**`investigations`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id, subject_id, analysis_run_id | uuid FK | |
| evidence_pack_id | uuid FK | |
| question | text not null | |
| trigger | text check in (`manual`,`alert`) | |
| trigger_alert_id | uuid null FK | |
| workflow_version | int | |
| status | text check in (`queued`,`running`,`succeeded`,`partial`,`failed`,`cancelled`) | |
| current_phase | text | |
| budget | jsonb | Limits applied |
| usage | jsonb | `{input_tokens, output_tokens, cost_estimate, tool_calls, wall_ms}` |
| error | jsonb null | |
| requested_by | uuid FK → users | |
| job_id | uuid FK | |
| created_at, started_at, completed_at | timestamptz | |

**`agent_steps`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| investigation_id | uuid FK | |
| step_key | text | e.g. `specialist.cash_flow`, `redteam`, `rebuttal.obligations` — unique per investigation (idempotent resume) |
| phase | text | `specialists`,`verify_findings`,`synthesis`,`red_team`,`rebuttal`,`final` |
| agent | text | |
| prompt_version | text | e.g. `cash_flow/v3` |
| prompt_hash | text | |
| model | text | Recorded per call; configured, not hard-coded |
| status | text check in (`pending`,`running`,`succeeded`,`failed`,`budget_exceeded`,`skipped`) | |
| input | jsonb | Messages sent (system prompt by ref + hash) |
| output | jsonb | Validated structured output (Findings/DraftReport/Challenges) |
| raw_output | text | Last raw model text (for debugging invalid outputs) |
| repair_attempted | boolean | |
| usage | jsonb | |
| error | jsonb null | |
| started_at, completed_at | timestamptz | |

**`tool_calls`**: `id` · `agent_step_id` FK · `seq` · `tool_name` · `arguments jsonb` ·
`result jsonb` (bounded) · `result_refs jsonb` (IDs of evidence returned) · `status`
(`ok`,`invalid_arguments`,`error`) · `duration_ms` · `created_at`.

**`llm_calls`**: `id` · `agent_step_id` FK · `attempt` · `provider` · `model` ·
`input_tokens` · `output_tokens` · `latency_ms` · `finish_reason` · `status`
(`ok`,`timeout`,`rate_limited`,`provider_error`,`invalid_output`) · `error` · `created_at`.

**`claims`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| investigation_id, agent_step_id | uuid FK | |
| local_id | text | Agent-local id (`c1`) |
| agent | text | |
| statement | text | |
| claim_type | text check in (`observation`,`inference`,`hypothesis`,`recommendation`) | |
| evidence_refs | jsonb | `[{kind, id}]` |
| confidence | text check in (`low`,`medium`,`high`) | |
| caveats | text[] | |
| supersedes_claim_id | uuid null FK | Revised claim after rebuttal |
| final_status | text check in (`verified`,`rejected`,`unverifiable`,`disputed`,`withdrawn`) | Denormalised from latest verification/challenge outcome |

**`claim_verifications`** (deterministic verifier output, append-only)

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| claim_id | uuid FK | |
| verifier_version | int | |
| result | text check in (`verified`,`rejected`,`unverifiable`) | |
| checks | jsonb | `[{check:"evidence_exists"|"evidence_scope"|"numeric_match"|"direction_match"|"caveat_required", passed, detail}]` |
| created_at | timestamptz | |

**`challenges`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| investigation_id | uuid FK | |
| agent_step_id | uuid FK | Red-team step |
| target_claim_id | uuid FK → claims | |
| challenge_type | text check in (`alternative_explanation`,`data_quality`,`unsupported`,`overstated`,`missing_context`,`fairness`) | |
| argument | text | |
| evidence_refs | jsonb | |
| severity | text check in (`minor`,`major`,`critical`) | |
| resolution | text null check in (`conceded`,`defended`,`revised`,`unresolved`) | |
| resolution_step_id | uuid null FK → agent_steps | |
| resolution_text | text null | |

**`investigation_events`** — append-only feed for SSE: `id bigserial` · `investigation_id` ·
`type` (`phase_started`, `step_started`, `tool_called`, `step_completed`, `claim_verified`,
`challenge_raised`, `completed`, `failed`) · `payload jsonb` · `created_at`. Clients resume with
`Last-Event-ID` = `id`.

**`reports`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| investigation_id | uuid FK unique | |
| summary | text | Built only from verified claims |
| sections | jsonb | `[{title, claim_ids[]}]` — rendered from claims, not free text |
| verified_claim_count, rejected_claim_count, disputed_claim_count | int | |
| open_questions | text[] | |
| is_partial | boolean | |
| created_at | timestamptz | |

### 3.8 Infrastructure

**`jobs`**

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id | uuid | |
| kind | text check in (`synthetic_generate`,`analysis_run`,`stress_test`,`investigation`,`backtest`) | |
| payload | jsonb | IDs only + logging context (`request_id`) |
| status | text check in (`queued`,`running`,`succeeded`,`failed`,`cancelled`) | |
| priority | smallint default 100 | |
| attempts, max_attempts | smallint | |
| run_after | timestamptz default now() | Backoff scheduling |
| locked_by | text null | Worker id |
| locked_at, heartbeat_at | timestamptz null | Stale lock reclaim after timeout |
| last_error | jsonb null | |
| result_ref | jsonb null | `{type, id}` of produced resource |
| created_at, updated_at, completed_at | timestamptz | |

Index: `(status, run_after, priority) where status = 'queued'`.
Dequeue: `select … where status='queued' and run_after <= now() order by priority, run_after
for update skip locked limit 1`.

**`audit_events`**: `id` · `org_id` · `actor_user_id` null · `actor_type` (`user`,`system`,
`agent`) · `action` (e.g. `analysis.started`, `alert.acknowledged`, `investigation.viewed`) ·
`entity_type` · `entity_id` · `metadata jsonb` · `request_id` · `created_at`. Append-only;
indexed `(org_id, created_at desc)` and `(entity_type, entity_id)`.

## 4. Row-Level Security (Supabase defence-in-depth)

The API connects with a privileged role and enforces tenancy in repositories. When deployed on
Supabase, RLS is additionally enabled on every business table with the pattern:

```sql
alter table subjects enable row level security;
create policy org_isolation on subjects
  using (org_id = (select org_id from users where auth_user_id = auth.uid()));
```

This guards against any future direct-from-browser Supabase access. The MVP frontend never queries
Supabase tables directly — only the FastAPI API.

## 5. Lineage: from a sentence to a transaction

An agent claim can always be traced back to raw data:

```
claims.evidence_refs ──▶ metric_values.id ──▶ lineage.series_ids / window
                                             └▶ analysis_runs.engine_versions + input_fingerprint
                                                    └▶ transactions (subject, ≤ as_of)
          ──▶ signals.evidence.metric_value_ids / transaction_ids
          ──▶ stress_test_results ──▶ stress_test_runs (scenario, params, seed)
```

`GET /api/v1/evidence/{kind}/{id}` (API_SPEC) resolves any ref for the UI's evidence chips.

## 6. Retention

| Data | MVP retention |
|---|---|
| Transactions, engine outputs | Indefinite (synthetic) |
| `agent_steps.input/raw_output` | 180 days, then nulled (metadata kept) |
| `investigation_events` | 30 days |
| `jobs` (completed) | 30 days |
| `audit_events` | Indefinite |

Retention runs as a scheduled job kind added in the hardening phase.

## 7. Migration policy

- Alembic, one revision per PR that changes schema; autogenerate is a draft, reviewed by hand.
- Every migration has a working `downgrade` while pre-production.
- Reference-table content (metric definitions, rules, scenarios, scoring models) is **not** seeded
  by migrations; it is synced from code at startup so code and DB cannot disagree about a version.
