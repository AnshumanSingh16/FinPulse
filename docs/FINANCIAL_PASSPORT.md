# FinPulse Financial Passport — methodology

> **Prototype — not a credit score.** The Financial Passport is a multidimensional
> financial-health profile built for a hackathon and calculated from **synthetic data**. It is not
> a credit score, is not produced by or comparable to any credit bureau (such as CIBIL), has not
> been validated against real repayment outcomes, and must not be used for lending or any other
> regulated decision. Every API response carries this disclaimer.

## What it is

Six dimensions, each scored 0–100, plus a prototype **Financial Health** score that combines them.
Every number is calculated by deterministic Python (`apps/api/src/finpulse/scoring/`) from the
metrics of the analytics engine ([FINANCIAL_METRICS.md](FINANCIAL_METRICS.md)). No language model
is involved anywhere. Every point traces back to a metric, every metric to records.

```
records ──▶ analytics metrics ──▶ factor points ──▶ dimension scores ──▶ Financial Health
           (25, with sources)     (curves)          (weighted means)       (weighted mean)
```

Example (Mehra Lighting & Electricals, 30 Sep 2026):

```
Financial Health: 50.6 / 100 — Watch   (confidence 1.00)
  Cash-Flow Stability      26.4      Financial Resilience      8.2
  Repayment Capacity       81.9      Debt Health              65.1
  Revenue Stability        55.5      Transaction Consistency  92.1
```

## How a score is calculated

1. **Factor points.** Each factor reads one metric and maps its value to 0–100 points by
   straight-line interpolation between the configured breakpoints. Beyond the first or last
   breakpoint the end value applies. Curves can rise (more is better) or fall (less is better).
2. **Missing data.**
   - If a metric is `insufficient_data`, the factor is **excluded**: its weight is shared among
     the dimension's other factors, and confidence falls.
   - If a metric is `not_applicable` and the factor sets `not_applicable_points`, those points
     apply. For example, cash runway is not applicable when the entity isn't burning cash, so it
     scores 100.
   - Otherwise a `not_applicable` factor is excluded.
3. **Dimension score** = Σ points × weight ÷ Σ weight, over the factors that could be scored.
4. **Financial Health** = Σ dimension score × dimension weight ÷ Σ weight, over the dimensions
   that could be scored.
5. **Traceability.** Each factor reports `contribution_to_overall` = points × its effective weight
   in the dimension × the dimension's effective weight. These contributions **add up exactly to
   the Financial Health score**, and a test checks this for every entity.
6. **Confidence** (0–1). Each factor counts as 1 when its metric has high confidence, 0.75 for
   medium, 0.5 for low, 1 for a scored not-applicable, and 0 when excluded.
   - Dimension confidence is the weight-averaged factor confidence.
   - Overall confidence is the weight-averaged dimension confidence, using configured weights,
     so a missing dimension counts as zero.
   - Below **0.7** the passport is marked `provisional`. This happens in the first months of an
     entity's history.
   - Confidence is reported **alongside** the score, not blended into it.
7. **Band.** A word for the score range, deliberately not a letter grade, to avoid resembling a
   credit rating.

Rounding is for display only. All arithmetic uses exact decimals.

## Dimensions, factors and curves

The tables below are **generated from the configuration**
(`apps/api/src/finpulse/scoring/models/passport_v1.toml`). A test fails if they drift. Regenerate
them with `cd apps/api && uv run python -m finpulse.scoring.methodology ../../docs/FINANCIAL_PASSPORT.md`.

<!-- generated:factors:start -->

### Cash-Flow Stability — 20% of the score (`cash_flow_stability`)

Does the entity keep more cash than it spends, month after month, without borrowing to do so?

| Metric | Weight | Curve (metric value → points) | If not applicable |
|---|---|---|---|
| `cashflow.net_margin` (Net cash margin, ratio) | 40% | -0.15 → 0 · -0.05 → 30 · 0 → 50 · 0.05 → 75 · 0.15 → 95 · 0.25 → 100 | excluded |
| `cashflow.positive_months` (Cash-positive months, ratio) | 30% | 0 → 0 · 0.5 → 50 · 0.8333 → 85 · 1 → 100 | excluded |
| `income.stability` (Income stability, score) | 30% | 0 → 0 · 100 → 100 | excluded |

### Repayment Capacity — 20% of the score (`repayment_capacity`)

Does it meet its obligations on time, and how much of its income do repayments absorb?

| Metric | Weight | Curve (metric value → points) | If not applicable |
|---|---|---|---|
| `payments.consistency` (Payment consistency, ratio) | 55% | 0.5 → 0 · 0.8 → 40 · 0.9 → 70 · 0.97 → 90 · 1 → 100 | excluded |
| `debt.service_burden` (Debt-service burden, ratio) | 45% | 0 → 100 · 0.1 → 85 · 0.25 → 55 · 0.4 → 25 · 0.6 → 0 | excluded |

### Revenue Stability — 15% of the score (`revenue_stability`)

Are sales steady, holding up or growing, and spread across customers?

| Metric | Weight | Curve (metric value → points) | If not applicable |
|---|---|---|---|
| `revenue.volatility` (Revenue volatility, ratio) | 40% | 0 → 100 · 0.1 → 88 · 0.2 → 70 · 0.35 → 45 · 0.6 → 10 · 0.8 → 0 | excluded |
| `revenue.growth` (Revenue growth, ratio) | 35% | -0.3 → 0 · -0.15 → 30 · -0.05 → 55 · 0 → 65 · 0.1 → 85 · 0.25 → 100 | excluded |
| `customers.concentration` (Customer concentration, ratio) | 25% | 0.15 → 100 · 0.3 → 75 · 0.5 → 45 · 0.8 → 10 · 1 → 0 | excluded |

### Financial Resilience — 20% of the score (`financial_resilience`)

Could it absorb a disruption — how long would its own cash last?

| Metric | Weight | Curve (metric value → points) | If not applicable |
|---|---|---|---|
| `buffer.months` (Financial buffer, months) | 40% | 0 → 0 · 0.5 → 30 · 1 → 55 · 3 → 85 · 6 → 100 | excluded |
| `cash.runway` (Cash runway, months) | 35% | 0 → 0 · 1 → 25 · 3 → 55 · 6 → 80 · 12 → 100 | 100 points |
| `liquidity.ratio` (Liquidity ratio, ratio) | 25% | 0.2 → 0 · 0.5 → 25 · 1 → 60 · 1.5 → 80 · 2.5 → 100 | excluded |

### Debt Health — 15% of the score (`debt_health`)

How much does it owe relative to its size, how hard is it leaning on its overdraft, and is it piling on new loans?

| Metric | Weight | Curve (metric value → points) | If not applicable |
|---|---|---|---|
| `debt.leverage` (Debt leverage, ratio) | 40% | 0 → 100 · 0.1 → 90 · 0.25 → 70 · 0.5 → 40 · 1 → 0 | excluded |
| `liquidity.overdraft_utilisation` (Overdraft utilisation, ratio) | 35% | 0 → 100 · 0.25 → 80 · 0.5 → 50 · 0.8 → 20 · 1 → 0 | 100 points |
| `debt.new_loans_6m` (New loans in 6 months, count) | 25% | 0 → 100 · 1 → 70 · 2 → 35 · 3 → 10 · 4 → 0 | excluded |

### Transaction Consistency — 10% of the score (`transaction_consistency`)

Is its banking activity regular — money coming in week after week?

| Metric | Weight | Curve (metric value → points) | If not applicable |
|---|---|---|---|
| `transactions.consistency` (Transaction consistency, score) | 100% | 0 → 0 · 100 → 100 | excluded |

### Bands

| Score | Band | Meaning |
|---|---|---|
| ≥ 80 | Strong | Healthy across most dimensions. |
| ≥ 65 | Sound | Generally healthy, with some areas to watch. |
| ≥ 50 | Watch | Mixed picture: several dimensions show strain. |
| ≥ 35 | Strained | Significant financial strain in several dimensions. |
| ≥ 0 | Critical | Severe strain: cash, repayments or revenue are under acute pressure. |

<!-- generated:factors:end -->

Why these weights: cash generation, repayment and resilience carry most weight (20% each),
because they show most directly whether an entity can meet its commitments. Revenue and debt
structure follow (15% each), and transaction regularity is a supporting signal (10%). The weights
and curves are expert judgement for a prototype. They have **not** been fitted to outcomes; with
synthetic data there are no real outcomes to fit to.

## Explanations

- **Factor explanations:** every factor carries a sentence such as *"Net cash margin of −14.8%
  scores 0.7/100 (40% of the dimension)."* Excluded factors say why.
- **Dimension summaries:** the score plus the strongest and weakest factor.
- **Strengths and concerns:** up to three each.
  - A factor is a *strength* at ≥ 70 points and a *concern* below 50.
  - They are ranked by impact: (points − 50) × the factor's effective share of the overall
    score.
  - The wording comes from the configuration, followed by the metric and its value.

## Explaining score changes

`change_from_previous_month` compares the passport with the one at the previous month-end.
`passport/history` includes the same explanation for every step.

- A factor's **impact** is the change in its `contribution_to_overall`. Because contributions add
  up to the score, the impacts add up to the change in score, before display rounding.
- The largest movements are listed (up to five; three in history steps), each with the metric's
  old and new value. Example: *"Debt Health: overdraft utilisation rose (39.2% → 68.5%), −1.7
  points"*.
- Dimension deltas and band changes are included, with a one-paragraph summary.

## Historical tracking

`GET …/passport/history?months=N` (1–24, default 12) returns the passport at each month-end, then
at `as_of`, oldest first.

- **Each point is recomputed** from the data as it stood on that date. The analytics engine
  guarantees no look-ahead, and a test recomputes history points from truncated data and gets
  identical scores. History is therefore always consistent with the current methodology version.
- **History is not stored.** Every response names the configuration (`model.version`,
  `model.config_sha256`) that produced it. Storing snapshots, to preserve exactly what was shown
  on a past date, is a later addition.

Mehra Lighting & Electricals, month-end scores (provisional while history is short):

| 2025-04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 2026-01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 84.7 | 85.0 | 79.3 | 82.3 | 79.3 | 78.7 | 75.1 | 83.4 | 72.1 | 66.1 | 69.0 | 69.9 | 69.8 | 67.9 | 66.7 | 65.6 | 55.2 | 50.6 |

Its decline starts in November 2025 (see [SYNTHETIC_DATA.md](SYNTHETIC_DATA.md)). The score
sits in the Sound/Strong range before that and ends at 50.6 (Watch), while its credit-bureau
record stays clean.

## Current results for the demo entities

| Entity | Health | Band | Cash-flow | Repayment | Revenue | Resilience | Debt | Transactions |
|---|---|---|---|---|---|---|---|---|
| Annapurna Home Kitchen (thin file) | 91.9 | Strong | 95.1 | 100.0 | 71.0 | 89.2 | 100.0 | 93.6 |
| Kaveri Packaging (healthy) | 84.1 | Strong | 70.1 | 99.3 | 80.7 | 75.2 | 99.0 | 82.4 |
| Ananya Rao (freelancer) | 83.8 | Strong | 86.0 | 94.4 | 59.1 | 100.0 | 99.6 | 38.8 |
| Rapid Mobile Hub (high risk) | 58.3 | Watch | 58.9 | 57.7 | 79.1 | 21.0 | 65.3 | 91.4 |
| Sharma Electricals (demo: growth draining cash) | 79.0 | Sound | 49.5 | 99.4 | 79.8 | 65.3 | 99.6 | 92.5 |
| Mehra Lighting & Electricals (deteriorating) | 50.6 | Watch | 26.4 | 81.9 | 55.5 | 8.2 | 65.1 | 92.1 |

Two things to notice:

- **The thin-file business scores well without any credit history.** Having no loans gives full
  marks on debt and repayment rather than a penalty, which is the point of the product.
- **The freelancer's weak spot is transaction consistency.** Clients pay a few times a month, so
  many weeks have no receipts. This is a known limitation of a weekly measure for individuals
  (see below).

## API

```
GET /api/v1/entities/{entity_id}/passport[?as_of=YYYY-MM-DD]
GET /api/v1/entities/{entity_id}/passport/history[?months=12&as_of=YYYY-MM-DD]
GET /api/v1/meta/passport-model          ← the full configuration as JSON
```

Errors follow the API's problem+json format: `404 entity_not_found`, `422 insufficient_history`,
`422 validation_error` (e.g. `months` outside 1–24).

## Changing the methodology

1. Edit `passport_v1.toml`, or copy it to `passport_v2.toml` and bump `version`. The loader
   rejects weights that don't sum to 1, curves that aren't increasing, points outside 0–100,
   unknown metrics and malformed bands.
2. Regenerate this document's tables (command above).
3. Run `uv run pytest tests/scoring`. The scenario tests show whether the entities still tell
   their stories.

## Limitations and responsible use

- **Not a credit score**, not a regulated product, and not validated. Weights and curves are
  judgement, and the data is synthetic.
- **No protected attributes.** Only financial-behaviour metrics are used; nothing about gender,
  religion, caste, age or location.
- **Categories are an input.** Misclassified transactions would distort cash-flow and expense
  metrics, and so the passport.
- **Weekly transaction consistency** favours businesses with frequent receipts. A monthly variant
  would suit individuals better.
- **Behaviours such as large cash withdrawals or betting spend are not yet scored.** They are
  visible in the data and are candidates for the early-warning engine.
- **Scores are recomputed, not stored.** See *Historical tracking*.
