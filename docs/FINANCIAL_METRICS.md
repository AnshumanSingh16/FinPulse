# Financial metrics

The deterministic analytics engine (`apps/api/src/finpulse/analytics/`) calculates every
financial number FinPulse shows. It is plain Python over an entity's stored records: no LLM, no
clock, no randomness. The same data and `as_of` date always give the same result.

The authoritative method text for each metric is returned with every value, and served by
`GET /api/v1/meta/financial-metrics`.

## Using it

```
GET /api/v1/entities                                            → entities you can analyse
GET /api/v1/entities/{entity_id}/financial-metrics[?as_of=YYYY-MM-DD]      → full report
GET /api/v1/entities/{entity_id}/financial-metrics/{metric_code}[?as_of=…] → one metric
GET /api/v1/meta/financial-metrics                              → definitions (methodology)
```

`as_of` defaults to the last day the entity's data is complete for. A past `as_of` gives the
report as it would have looked that day. A test proves no later record can affect it.

Each metric in the response carries:

| Field | Meaning |
|---|---|
| `code`, `name`, `family` | Stable id (e.g. `receivables.days`), display name, grouping |
| `value` | Decimal **string**, exact. INR in rupees to the paisa; ratios as fractions (0.25 = 25%). `null` unless `availability` is `available`. |
| `unit` | `INR`, `ratio`, `days`, `months`, `score` (0–100) |
| `period` | `start`, `end`, `label` (`2026-09`, `last_6_months`, `trailing_90_days`, `as_of`, …) |
| `availability` | `available`, `insufficient_data` (not enough history yet), `not_applicable` (structurally meaningless, e.g. payable days for someone with no suppliers) |
| `confidence` | `high` (full intended window), `medium` (shorter window, at least the minimum), `low` (approximation, e.g. revenue from bank receipts because there are no sales documents) |
| `method` | How it is calculated |
| `components` | Intermediate values and breakdowns (e.g. receivables ageing buckets, per-lender debt) |
| `sources` | Tables used, record counts and up to five record ids for drill-down |
| `notes`, `version` | Caveats or the reason a value is missing; methodology version |

The report also includes `coverage` (history span, record counts, uncategorised transactions)
and monthly `series` for revenue, expenses, net cash flow and month-end balance (up to 12 months).

## Conventions

- **Months** are complete calendar months covered by the data. A month counts if the history
  starts within its first 7 days. "Last N months" ends with the last complete month on or before
  `as_of`.
- **Point-in-time** values (balance, receivables, debt, liquidity) are at the end of `as_of`.
- **GST is excluded** from revenue, purchases and expenses: it is collected for the government,
  not earned. Receivables and payables include it, because that is what is owed.
- **Transaction grouping** (`analytics/classify.py`) is by category:
  - **Operating receipts:** `income.*`.
  - **Operating expenses:** `expense.*`, `personal.*`, `bank.charges`, `cash.*`, and
    uncategorised debits (the conservative choice).
  - **Excluded from operating expenses:** debt service, finance costs, owner drawings, GST and
    income-tax payments, and investments.
  - **Where categories come from:** today, the data source (the synthetic generator's labels).
    The planned rule-based categoriser will assign them from narrations. All metrics share this
    one grouping.

## The metrics

| Code | Unit | Window | Calculation | Not available when |
|---|---|---|---|---|
| `revenue.monthly` | INR | last complete month | Invoices issued (ex-GST) + walk-in sales (ex-GST). With no sales documents: operating receipts (low confidence) | no complete month |
| `expenses.monthly` | INR | last complete month | Supplier bills received (ex-GST) + operating cash expenses (supplier payments instead of bills if there are no bills) | no complete month |
| `cashflow.net_monthly` | INR | last complete month | All credits − all debits (includes loans) | no complete month |
| `revenue.growth` | ratio | 3 vs previous 3 months | Σ revenue last 3 ÷ Σ previous 3 − 1 | < 6 months, or no earlier revenue |
| `revenue.volatility` | ratio | up to 12 months (min 4) | Coefficient of variation of monthly revenue | < 4 months |
| `expenses.growth` | ratio | 3 vs previous 3 months | As revenue growth, on expenses | < 6 months |
| `cash.balance` | INR | as_of | Balance across accounts at end of day; components: overdraft drawn, available funds | no transactions |
| `cash.runway` | months | 3 months → as_of | (balance + undrawn overdraft) ÷ average monthly net outflow | *not applicable* if not burning cash |
| `receivables.outstanding` | INR | as_of | Σ unpaid invoice balances; ageing buckets and overdue share | *n/a* without invoices |
| `receivables.days` | days | 90 days | Receivables ÷ invoices issued in the period × days | *n/a* without invoices; < 30 days of history |
| `payables.days` | days | 90 days | Unpaid bills ÷ bills received in the period × days | *n/a* without supplier bills |
| `debt.outstanding` | INR | as_of | Σ principal disbursed − Σ principal of instalments paid; per-lender components | — (0 with no loans) |
| `debt.service_burden` | ratio | 3 months | Instalments due ÷ operating receipts | no receipts |
| `customers.concentration` | ratio | 6 months (min 3) | Largest customer's share of revenue; walk-in pooled as many small buyers; top-3 share, HHI | < 3 months |
| `suppliers.concentration` | ratio | 6 months (min 3) | Largest supplier's share of purchases; top-3 share, HHI | *n/a* with no suppliers |
| `income.stability` | score | 6 months (min 4) | 100 × (1 − min(CV of monthly receipts, 1)) × share of months with receipts | < 4 months |
| `payments.consistency` | ratio | 12 months (or history) | Mean of: share of instalments paid on time with no bounce; share of bills paid within 5 days of due | *n/a* with no obligations |
| `liquidity.ratio` | ratio | as_of | (cash ≥ 0 + receivables) ÷ (payables + overdraft drawn + overdue instalments + principal due in 12 months) | *n/a* with no current liabilities |
| `buffer.months` | months | 3 months → as_of | Own cash (positive balance only) ÷ average monthly total outflows | no outflows |
| `transactions.consistency` | score | 13 weeks (min 8) | 100 × share of weeks with an operating receipt × (1 − 0.5 × min(CV of weekly transaction counts, 1)) | < 8 weeks |
| `cashflow.positive_months` | ratio | 6 months (min 3) | Share of months with net cash flow ≥ 0 **before new borrowing** (loan disbursements removed) | < 3 months |
| `cashflow.net_margin` | ratio | 6 months (min 3) | Net cash flow before borrowing ÷ money received excluding borrowing | < 3 months, nothing received |
| `debt.leverage` | ratio | as_of vs last 3 months | Debt outstanding ÷ annualised revenue (3 months × 4); 0 with no loans | no revenue while in debt |
| `debt.new_loans_6m` | count | 183 days | Loans disbursed in the period (loan stacking signal) | no transactions |
| `liquidity.overdraft_utilisation` | ratio | 90 days | Average end-of-day overdraft drawn ÷ overdraft limit | *n/a* without an overdraft facility |

The last five were added for the Financial Passport ([FINANCIAL_PASSPORT.md](FINANCIAL_PASSPORT.md)).

## What the metrics show for the demo entities

From `GET …/financial-metrics` at the end of each entity's data:

| | Sharma Electricals | Kaveri (healthy) | Annapurna (thin file) | Rapid Mobile (high risk) | Ananya (freelancer) |
|---|---|---|---|---|---|
| Revenue growth | −20.0% | +0.5% | +7.0% | +3.8% | +25.9% |
| Cash balance | −₹1.68L | ₹27.7L | ₹12.7L | −₹1.86L | ₹9.5L |
| Cash runway | 0.4 months | not burning | not burning | 3.6 months | not burning |
| Receivable days | 47.0 | 35.2 | 2.8 | 48.9 | 26.1 |
| Payment consistency | 0.93 | 1.00 | 1.00 | 0.70 | 1.00 |
| Liquidity ratio | 0.43 | 1.94 | 19.0 | 0.14 | 51.7 |
| Financial buffer | 0.0 months | 0.8 months | 2.2 months | 0.0 months | 9.2 months |

Sharma's own trajectory: at 31 Oct 2025, the last month before its decline, its balance was
positive, its liquidity ratio more than twice today's, and there were no bounce charges. All of
that is checked in `tests/analytics/test_engine.py`.

## Changing or adding a metric

1. Add a `define(...)` and a function `def my_metric(ctx: Context) -> Metric` in
   `analytics/metrics.py`, then append it to `ALL_METRICS`. Use the `Context` helpers (`window`,
   `revenue`, `balance_at`, `receivables_at`, …) so period and money rules stay uniform.
2. Return `available(...)` with a value, period, confidence, components and sources, or
   `unavailable(...)` with the reason.
3. Add hand-checked cases to `tests/analytics/test_metrics.py`. The engine-level tests then also
   check it for every synthetic entity, including the no-look-ahead property.
4. If you change how an existing metric is calculated, bump its `version`.

## Not yet

- Results are computed per request (about 0.1–0.2 s per entity) rather than stored. Persisted
  analysis runs with input fingerprints (`analysis_runs`, `metric_values` in DATA_MODEL.md) come
  with the scoring engine.
- Categories come from the data source. The narration-based categoriser and recurring-series
  detection are still to be built.
- Organisation scoping uses the demo organisation until authentication lands.
