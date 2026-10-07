# FinPulse Stress Testing — methodology

> **Hypothetical scenarios, not forecasts.** A stress test asks "what would happen to this
> business's cash if…?" using simple, documented assumptions on **synthetic data**. Results
> are not predictions, and the Financial Health score they move is a prototype financial-health
> profile, **not a credit score**. Every response carries this disclaimer.

## What it does

Given an entity, an `as_of` date and a scenario (a preset or a list of shocks), the engine:

1. builds a **baseline** from the last 3 complete months before `as_of`. It uses the analytics
   engine's records plus the actual loan schedules.
2. projects **the baseline forward**, month by month, for `horizon_months` (default 6, max 24).
3. applies the scenario's **shocks** to the same projection.
4. compares the two. It reports revenue, expenses, net cash flow, cash balance, liquidity, runway,
   overdraft use, projected Financial Health, risk level and the **failure point** (the date when
   funds, including the overdraft, run out).
5. returns **evidence**: short, numbered statements of every input and outcome, each with its
   values and source records. An AI agent can cite them later without recalculating anything.

Everything is deterministic Python (`apps/api/src/finpulse/stress/`): the same inputs always give
the same output. **No language model is involved in any calculation.**

```
records ─▶ baseline (3-month average + loan schedules) ─▶ levers ─▶ simulate() ─▶ projection
                                                     ▲
                                  shocks adjust ─────┘     baseline levers vs shocked levers
                                                           ─▶ comparisons · risk · health · evidence
```

## The baseline

| Input | How it is derived |
|---|---|
| Revenue, purchases, operating costs | Monthly averages of the 3 complete months before `as_of` (accrual, excluding GST) |
| Customer receipts, supplier payments, other outflows | Monthly averages of bank transactions in the same months. Per-customer and per-supplier shares are kept so a single counterparty can be shocked |
| Debt service | **Actual** instalments from each loan's schedule that fall in the horizon. Overdue instalments are assumed paid in the first month |
| Opening balance, overdraft | Bank balance at `as_of`. The overdraft limit comes from the account. Overdraft interest is 13% a year on negative balances, charged monthly |
| Receivables and payables | Open invoices and bills at `as_of` (for the liquidity ratio) |

Flows are rounded to whole rupees and interest to the paisa. The projection starts in the month
after `as_of`'s month.

## Scenarios

The ten presets (`GET /api/v1/meta/stress-scenarios`) are combinations of six shock types:

| Preset | Shock | Parameters |
|---|---|---|
| `revenue_down_10` · `_20` · `_30` | `revenue_decline` | `decline_pct` 0.10 / 0.20 / 0.30. Costs follow revenue (purchases fall in proportion) unless `costs_follow_revenue=false` |
| `major_customer_stops_paying_30_days` · `_60_days` · `_90_days` | `customer_payment_stop` | `days`. The largest paying customer by default (or `customer_id`). Receipts for those days are withheld and, by default, `recovered` the month after |
| `operating_expenses_up_15` | `operating_expense_increase` | `increase_pct` 0.15 on non-purchase operating costs |
| `new_debt` | `new_debt` | `principal` (default 2 × monthly receipts, rounded to ₹10k, min ₹50k), `annual_rate` 0.18, `tenor_months` 24. Disbursed in the start month, with EMIs from the next |
| `interest_rate_up_300bps` | `interest_rate_increase` | `increase_bps` 300. Remaining instalments are re-amortised at the new rate, and the overdraft rate rises too |
| `major_supplier_cost_up_10` | `supplier_cost_increase` | `increase_pct` 0.10. The largest supplier by default (or `supplier_id`) |

Every shock also takes `start_month` (1-based, default 1). Most take `duration_months`
(default: until the end of the horizon). Shocks can be combined (up to 10 in one request) and are
applied in order.

A shock that cannot apply returns `422 scenario_not_applicable`. Examples: a supplier shock for a
freelancer with no suppliers, an unknown `customer_id`, or a `start_month` beyond the horizon.

## Outputs

`baseline` and `stressed` have the same shape: totals over the horizon (revenue, expenses, net
cash flow), the closing and minimum balance, liquidity ratio, cash runway, peak overdraft
utilisation, projected Financial Health and band, risk and failure point, plus every month.

| Output | Definition |
|---|---|
| Cash runway | (opening balance + overdraft limit) ÷ average monthly burn before borrowing. Shown as `null` when the business does not burn cash |
| Liquidity ratio | (closing cash + receivables) ÷ (payables + overdraft drawn + loan principal due in the following 12 months), at the end of the horizon. Shown as `null` with no liabilities |
| Failure point | The first month when the balance falls below −overdraft limit. The day is interpolated within the month. It also gives the shortfall at month end |
| Projected Financial Health | The passport model re-run on current metrics, with 12 cash, liquidity, revenue and debt metrics replaced by their projected values. The **health impact** is scenario vs baseline projection, which isolates the shock from drift already in the baseline. The impact is attributed to dimensions and factors |

`comparisons` gives each headline metric's baseline value, scenario value, absolute change,
percentage change and direction (better / worse / unchanged). `risk_change` reports both risk
levels, the number of steps between them, and whether risk escalated.

### Risk levels

| Level | Any of |
|---|---|
| **Critical** | Available funds, including the overdraft, run out within the horizon |
| **High** | Runway < 3 months · overdraft ≥ 85% used · lowest available funds < half a month of outgoings |
| **Elevated** | The balance goes negative · runway < 6 months · liquidity ratio < 0.5 |
| **Low** | None of the above |

Each level carries the reasons that triggered it. The thresholds live in `stress/risk.py`, and
tests pin them.

## Results on the synthetic entities (as of 30 Sep 2026, 6 months)

| Entity | Baseline | Typical scenario outcome |
|---|---|---|
| **Sharma Electricals** (demo) | Low | Fragile to one customer: the largest customer delaying payment 60 days takes it to **High** (overdrawn at −₹2,50,470 in Nov 2026), 90 days to **Critical** (funds run out ~16 Dec 2026); a 20% revenue fall keeps it Low |
| Mehra Lighting & Electricals | **Critical**: funds run out ~13 Oct 2026 | Shocks bring failure earlier (revenue −30% → 8 Oct; customer stop → 4 Oct). `new_debt` avoids failure (→ High) but cuts repayment capacity |
| Rapid Mobile Hub | High | Most shocks tip it into **Critical** (revenue −20% → funds out ~24 Oct) |
| Kaveri Packaging | Low | Stays Low under all ten; Financial Health falls by up to 13 points (revenue −30%) |
| Annapurna Home Kitchen | Low | Stays Low; no debt, so a rate rise changes nothing |
| Ananya Rao (freelancer) | Low | Stays Low; the supplier preset is not applicable |

## Limits (deliberate, for a prototype)

- Linear, deterministic projection from a 3-month average. No seasonality and no Monte Carlo.
- No second-order effects: a revenue fall does not change payment terms, and new debt does not
  change revenue.
- GST is excluded from revenue but included in cash flows as paid. Tax timing is not modelled.
- Results are not stored. They are recomputed per request in 5–40 ms.

## Adding a scenario

**A preset** (a new combination of existing shocks) is data. Add one entry to
`stress/presets.py`:

```python
"revenue_down_20_for_3_months": (
    "Revenue decreases by 20% for 3 months",
    [{"type": "revenue_decline", "decline_pct": "0.20", "duration_months": 3}],
),
```

Presets are validated through the same models as API requests (tests check every preset).

**A new shock type** is one class in `stress/shocks.py`, above the `ShockSpec` line:

```python
@register
class CustomerDefault(Shock):
    code = "customer_default"
    name = "Customer defaults"
    description = "A share of open receivables is never collected."

    class Params(TimedParams):
        type: Literal["customer_default"]
        share: Decimal = Field(gt=0, le=1, description="0.3 = 30% of receivables lost")

    def apply(self, params: Any, levers: Levers) -> None:  # adjust levers only
        levers.receivables_factor *= ONE - params.share
        levers.evidence.append(Evidence(id=f"shock.{self.code}", kind="shock", text=...))

    def describe(self, params: Any) -> str:
        return f"Customers default on {pct(params.share)} of receivables"
```

`@register` adds it to the registry; `ShockSpec`, the discriminated union the API validates
against, is built from the registry. The catalogue endpoint and its JSON Schema, the evidence,
and the comparisons all pick the new shock up with no other change. Override `resolve()` to fill
defaults from the baseline, or to raise `ScenarioNotApplicable`. `simulate()` does all the arithmetic. A shock only adjusts **levers** (factors and
per-month deltas), so new shocks cannot introduce inconsistent cash maths. Add a hand-checked case
to `tests/stress/test_projection.py`.
