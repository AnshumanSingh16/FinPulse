# FinPulse Early Warning Engine — methodology

> **Prototype on synthetic data.** Warnings flag changes worth investigating. They are not
> predictions, not a credit assessment, and must not be used for lending or any other regulated
> decision. Every response carries this disclaimer.

## What it does

The engine looks for **deterioration before a crisis**: revenue falling, customers paying later,
cash and liquidity draining, debt stacking up, unusual payments. It uses **deterministic rules
and historical comparisons**. Each rule compares the entity *now* with the same entity *earlier*,
recomputed from the data as it stood on that earlier date. Whether a warning exists is decided
here, in Python, by configured thresholds. **No language model decides, scores or words a
warning.** The AI layer (later) will explain and investigate warnings. It cannot create or
dismiss them.

```
records ─▶ snapshots (now, 2 / 3 / 6 months ago, month-end medians) ─▶ 18 rules ─▶ measure
                                                                                     │
          config/early_warning_v1.toml: tiers · windows · minimum changes ──────▶ grading
                                                                                     │
                       warnings (with evidence) ─▶ risk summary (level, index, trend, timeline)
```

## Grading — the same for every rule

1. **Measure.** The rule computes one measure, such as "receivables growth over 61 days" or
   "liquidity ratio".
2. **Tiers.** The measure is compared with the rule's configured tiers, from `low` to `critical`.
   An *above* rule warns when the measure is at or above a tier; a *below* rule warns at or
   below one. The warning takes the highest tier crossed.
3. **Trend.** The rule also decides whether the condition is **deteriorating**: it got worse by a
   configured minimum, or it is a change by nature, such as a fall. If it is present but not
   getting worse, the warning is reported **one severity lower**, with `trend: "persistent"`.
   Early warning is about change; a stable weakness is the Financial Passport's job.
4. **Clear.** Below the lowest tier, after step 3, the rule is clear.
5. **Volatility scaling.** Rules whose figures are naturally noisy for some earners can scale
   their tiers by the entity's **own normal volatility**: revenue volatility in the 12 months
   *before* the judged period ÷ a configured norm, between 1 and a maximum. These are
   `revenue_decline`, `major_customer_loss`, `expense_acceleration` and `receivables_growth`.
   A freelancer whose monthly revenue normally swings ±40% needs a bigger fall to raise the same
   warning as a steady shop. Scaling never lowers a threshold.
6. **Severity floor.** A watch-listed transaction category, such as betting, makes
   `unusual_transactions` at least `watch_severity`.

The thresholds are judgement-based starting points, chosen so that the healthy synthetic
entities stay quiet and the deteriorating one is flagged early. They are not calibrated against
real outcomes.

## The rules

All thresholds are in `apps/api/src/finpulse/early_warning/config/early_warning_v1.toml`, and the
same values are served by `GET /api/v1/meta/early-warning-rules`.

| Rule | Category | Measure (tiers low / medium / high / critical) | Deteriorating when |
|---|---|---|---|
| `revenue_decline` | revenue | Revenue, last 3 months vs the 3 before (−10% / −20% / −30% / −45%) | Always, unless revenue is up year-on-year (seasonal), which needs 15+ months. Volatility-scaled |
| `expense_acceleration` | expenses | Expense growth − revenue growth, 3 vs 3 months (5 / 10 / 20 / 35 points), only if expenses grew ≥ 10% | Expense growth is higher than 3 months earlier. Volatility-scaled |
| `cash_decline` | cash | Fall in the 30-day average balance vs 3 months earlier, ÷ average monthly outgoings (0.25 / 0.5 / 1 / 1.5 months) | Always (it is a fall) |
| `overdraft_reliance` | cash | Average overdraft utilisation over 90 days (25 / 50 / 75 / 90%) | Up ≥ 10 points in 3 months |
| `liquidity_decline` | liquidity | Liquidity ratio, below (1.0 / 0.8 / 0.6 / 0.4) | Down ≥ 10% in 3 months |
| `runway_shrinking` | liquidity | Cash runway in months, below (9 / 6 / 3 / 1) | Down ≥ 20% in 3 months, or the business was not burning cash before |
| `receivables_growth` | receivables | Receivables vs the median of 3 month-ends 2–4 months earlier (+20 / 30 / 50 / 80%). Ignored if DSO < 30 days | Receivable days also rose ≥ 5 (receivables outgrew sales). Volatility-scaled |
| `receivable_days_increase` | receivables | DSO minus its median over 6 earlier month-ends (+7 / 10 / 20 / 30 days). Ignored if DSO < 30 | Always (it is a rise) |
| `delayed_collections` | receivables | Rise in amount-weighted days late on customer payments, last 90 days vs 90 days to 3 months ago (+5 / 10 / 15 / 25 days) | Always |
| `debt_service_burden` | debt | Instalments due ÷ operating receipts (15 / 25 / 35 / 50%) | Up ≥ 2 points in 3 months |
| `new_borrowing` | debt | Loans disbursed in 6 months (– / 2 / 3 / 4) | Debt outstanding is higher than 6 months ago |
| `repayment_slippage` | debt | Instalments due in 90 days that bounced, were paid late or are unpaid (1 / 2 / 3 / 5) | More than in the previous 90 days |
| `customer_concentration` | concentration | Largest customer's share of revenue (30 / 45 / 60 / 75%) | Up ≥ 5 points in 6 months |
| `major_customer_loss` | concentration | Customer-specific lost sales from customers that were ≥ 10% of revenue ÷ monthly revenue (5 / 10 / 20 / 30%) | Always. Only the fall *beyond* the rest of the business's own fall counts, so a business-wide decline is left to `revenue_decline`. Volatility-scaled |
| `supplier_concentration` | concentration | Largest supplier's share of purchases (50 / 70 / 85 / 95%) | Up ≥ 5 points in 6 months |
| `unusual_transactions` | transactions | Unusual outgoing payments in 30 days ÷ monthly outgoings (5 / 15 / 30 / 50%) | More than in the previous 30 days |
| `revenue_volatility` | volatility | CV of monthly revenue, last 6 months (15 / 25 / 40 / 60%) | ≥ 1.25× the previous 6 months |
| `cash_flow_volatility` | volatility | Std of monthly net cash flow ÷ average receipts, 6 months (15 / 25 / 40 / 60%) | ≥ 1.25× the previous 6 months |

A payment counts as **unusual** in any of these cases:

- it is at least ₹25,000 and more than 2× the largest payment in the same category in the
  previous 180 days;
- it is at least ₹25,000 and its category had no payments at all in those 180 days;
- its category is on the watch list (`personal.betting`, `bank.bounce_charge`).

EMIs and tax payments are excluded.

## A warning

```json
{
  "id": "EW-233FAE5A17",
  "rule": "receivables_growth",
  "category": "receivables",
  "severity": "high",
  "title": "Receivables growing faster than sales",
  "description": "Receivables increased +59% against their typical level (₹6,89,747, the median of 3 month-ends to 31 Oct 2025) to ₹10,97,992, while invoiced sales changed 0%. Average collection time: 31 → 48 days. 38% of receivables are overdue.",
  "affected_metric": { "code": "receivables.outstanding", "name": "Receivables outstanding", "unit": "INR", "derived": false },
  "current_value": "1097992.00",
  "previous_value": "689747.00",
  "change": "408245.00",
  "change_pct": "0.5919",
  "threshold": {
    "measure": "Growth in receivables over 61 days", "observed": "0.5919", "operator": ">=",
    "value": "0.5000", "unit": "ratio", "tier": "high",
    "tiers": { "low": "0.20", "medium": "0.30", "high": "0.50", "critical": "0.80" },
    "scale": "1.00", "direction": "above"
  },
  "trend": "deteriorating",
  "status": "escalated",
  "first_detected_on": "2025-10-31",
  "detected_at": "2025-12-31T23:59:59+05:30",
  "evidence": [ { "id": "receivables_now", "text": "Receivables at 31 Dec 2025, aged.", "values": { "…": "…" }, "metric_codes": ["receivables.outstanding"], "sources": [ { "table": "invoices", "record_count": 21, "sample_ids": ["…"] } ] }, "…" ]
}
```

(Sharma Electricals, as of 31 Dec 2025.)

| Field | Meaning |
|---|---|
| `id` | `EW-` + a hash of entity, rule and `first_detected_on`. It stays the **same while the condition lasts**, so later alert tracking can follow it. |
| `affected_metric` | The metric the warning is about. `derived: true` means the rule computed it itself (e.g. average days late) rather than reading the metrics catalogue. |
| `current_value` / `previous_value` | In the metric's unit. "Previous" is the rule's comparison point (an earlier date, an earlier period, or a median of earlier month-ends; see `previous_period`). |
| `threshold` | The measure compared, the tier crossed (after scaling) and all configured tiers. |
| `status` | Compared with the previous month-end: `new`, `ongoing`, `escalated` or `easing`. |
| `first_detected_on` | Start of the current unbroken run of month-ends with this warning (up to 12 months back). |
| `detected_at` | **Data time**: the end of the `as_of` day (IST). It is deterministic, so the same data always gives the same timestamp and a replay of a past date gives that date. Not wall-clock time. |
| `evidence` | The numbers behind the warning, with metric codes, periods and source record ids, ready for the AI layer to cite. |

## Risk summary

`GET /entities/{id}/risk-summary` aggregates the warnings:

- **Early-warning index** (0–100): configured points per warning (low 2, medium 8, high 20,
  critical 40), summed and capped at 100.
- **Risk level**: `none`, `low`, `medium`, `high` or `critical`. It comes from the index
  (`low` ≥ 1, `medium` ≥ 15, `high` ≥ 40, `critical` ≥ 75) and is **never lower than the worst
  single warning**.
- **Categories** affected, their worst severity, and the **top warnings**.
- **Trend** against 3 months earlier: direction, plus new, resolved, escalated and eased rules.
- **Timeline**: level, index and rules at each of the last 12 month-ends. `first_warning_on`
  marks the start of the current unbroken run with any warning.

## Results on the synthetic entities

Risk level at each month-end, Oct 2025 – Sep 2026:

| Entity | O | N | D | J | F | M | A | M | J | J | A | S |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Sharma Electricals** (deteriorates from Nov 2025) | med | med | **high** | crit | high | high | high | med | high | high | crit | crit |
| Rapid Mobile Hub (chronic high risk) | low | med | crit | crit | crit | crit | crit | high | crit | high | crit | high |
| Kaveri Packaging (healthy) | low | – | – | low | low | low | med | – | low | low | low | low |
| Annapurna Home Kitchen (thin-file, healthy) | – | – | low | – | low | low | low | low | low | low | low | low |
| Ananya Rao (freelancer, lumpy income) | med | crit | crit | med | high | med | med | med | med | high | med | med |

- **Sharma Electricals.**
  - December 2025, a month after the hidden onset: receivables up 59% with flat sales, collection
    time from 31 to 48 days, expenses outpacing revenue, and a 1.7-month runway.
  - By March 2026: "Shree Ganesh Builders: ₹2,72,265 → ₹71,529 a month (−74%; the rest of sales
    −8%)".
  - All of this comes **8–9 months before** its loan auto-debits bounce (Aug–Sep 2026), while
    the simulated credit bureau shows a clean record throughout.
- **Kaveri and Annapurna** never go above medium, and finish low.
- **Ananya.**
  - Her slow-paying UK client causes receivables spikes in Nov–Dec 2025. At that point her history
    is too short to measure her normal volatility, so no scaling applies. This is a false alarm on
    an entity the ground truth says is fine.
  - From 2026 the scaling recognises her lumpy income, and she sits at medium for genuinely
    volatile revenue and concentrated clients. It is exactly the kind of warning the AI
    investigation layer should be able to explain away.
- **Rapid Mobile Hub** is high or critical throughout, as a chronically risky business should be.

The tests in `tests/early_warning/` pin these stories.

## Guarantees

- **No look-ahead.** A warning for a past date is identical whether or not later data exists
  (tested on two entities at three dates).
- **Deterministic.** Same data, date and configuration give identical warnings, IDs and
  timestamps.
- **Configuration is strict.** Every rule must be configured. Unknown or missing keys are
  rejected, and tiers must be ordered. The config file's SHA-256 is returned with every result.
- **Transparent coverage.** Every response lists each rule's state: `triggered`, `clear`,
  `insufficient_data` (with the reason), `not_applicable` or `disabled`.

## Adding a rule

1. In `early_warning/rules.py`, subclass `Rule`, or `LevelRule` for "grade a catalogue metric and
   check whether it is getting worse". Set `code`, `about`, `category`, `metric` and `direction`,
   and a `Params` model listing its settings. Implement `evaluate()`, which returns a `Finding`
   (the measure, `deteriorating`, the text, current and previous values, and evidence) or a
   `Skip` (why there is nothing to report). Decorate the class with `@register`.
2. Add a `[rules.<code>]` section to the TOML with `enabled`, `tiers` and the parameters. Loading
   fails until you do.
3. Add a hand-checked test in `tests/early_warning/test_rules.py`.

Grading, persistence, scaling, IDs, streaks, the API and the risk summary need no changes.

Changing a threshold means editing the TOML and bumping `version`. Results carry the config hash.

## Limits

- Not stored: warnings and timelines are recomputed per request (40–120 ms per entity, including
  the 12-month timeline).
- No alert lifecycle (acknowledge or resolve) yet. Stable IDs are in place for it.
- No backtest harness yet (lead time, precision, false-alarm rate across a cohort).
- Seasonality is only checked year-on-year, which needs 15 months of data.
