"""
Decision Lab: what a purchase does to cash, under base, optimistic and downside scenarios.

Each scenario is the forecast (forecast.py) run twice — without and with the purchase — so the
difference is attributable to the purchase alone. The scenario settings are explicit assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.common import money, prepare_ledger, ts, last_full_month
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow
from finpilot.engine.summary import OPEX_CLASSES


def emi(principal: float, annual_rate_pct: float, months: int) -> float:
    """Standard reducing-balance EMI: P·r·(1+r)^n / ((1+r)^n − 1); P/n at 0%."""
    if principal <= 0:
        return 0.0
    if months < 1:
        raise ValueError("Tenure must be at least one month")
    r = annual_rate_pct / 12 / 100
    if r == 0:
        return money(principal / months)
    g = (1 + r) ** months
    return money(principal * r * g / (g - 1))


def default_buffer(ledger: pd.DataFrame, as_of, months: int = 3) -> float:
    """One month of typical operating expenses (average of the last `months` full months)."""
    df = prepare_ledger(ledger)
    _, end = last_full_month(as_of)
    start = (end - pd.DateOffset(months=months - 1)).replace(day=1)
    win = df[(df["date"] >= start) & (df["date"] <= end) & (df["direction"] == "out") & df["cls"].isin(OPEX_CLASSES)]
    return money(win["amount"].sum() / months) if len(win) else 0.0


@dataclass(frozen=True)
class Purchase:
    name: str
    cost: float
    purchase_date: str
    financing: str = "cash"  # "cash" | "loan"
    down_payment_pct: float = 100.0
    loan_rate_pct: float = 0.0
    tenure_months: int = 12
    monthly_benefit: float = 0.0
    benefit_start_months: int = 1
    monthly_running_cost: float = 0.0
    one_time_costs: float = 0.0


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    benefit_multiplier: float
    benefit_delay_months: int
    receivable_delay_days: int
    receivable_collection_pct: float
    include_overdue_receivables: bool


SCENARIOS = (
    Scenario("optimistic", "Optimistic", 1.25, 0, 0, 100.0, True),
    Scenario("base", "Base", 1.0, 0, 0, 100.0, False),
    Scenario("downside", "Downside", 0.5, 2, 30, 90.0, False),
)


def purchase_flows(p: Purchase, scenario: Scenario, horizon_end: pd.Timestamp) -> list[dict]:
    flows = []
    d0 = ts(p.purchase_date)
    upfront = p.cost if p.financing == "cash" else p.cost * p.down_payment_pct / 100
    flows.append({"date": d0, "amount": -upfront, "label": f"{p.name}: {'payment' if p.financing == 'cash' else 'down payment'}", "category": "Purchase"})
    if p.one_time_costs:
        flows.append({"date": d0, "amount": -p.one_time_costs, "label": f"{p.name}: installation / one-time costs", "category": "Purchase"})
    if p.financing == "loan":
        principal = p.cost - upfront
        instalment = emi(principal, p.loan_rate_pct, p.tenure_months)
        for k in range(1, p.tenure_months + 1):
            d = d0 + pd.DateOffset(months=k)
            if d > horizon_end:
                break
            flows.append({"date": d, "amount": -instalment, "label": f"{p.name}: EMI {k}", "category": "Purchase loan"})
    start_m = p.benefit_start_months + scenario.benefit_delay_months
    k = 0
    while True:
        d = d0 + pd.DateOffset(months=start_m + k)
        if d > horizon_end:
            break
        if p.monthly_benefit:
            flows.append({"date": d, "amount": p.monthly_benefit * scenario.benefit_multiplier, "label": f"{p.name}: expected benefit", "category": "Purchase benefit"})
        k += 1
    k = 1
    while p.monthly_running_cost:
        d = d0 + pd.DateOffset(months=k)
        if d > horizon_end:
            break
        flows.append({"date": d, "amount": -p.monthly_running_cost, "label": f"{p.name}: running cost", "category": "Purchase running cost"})
        k += 1
    return flows


def simulate_purchase(
    ledger: pd.DataFrame,
    balances: pd.DataFrame | None,
    obligations: pd.DataFrame | None,
    as_of,
    purchase: Purchase,
    horizon_days: int = 180,
    min_buffer: float | None = None,
    include_run_rate: bool = True,
    scenarios: tuple[Scenario, ...] = SCENARIOS,
) -> dict:
    if purchase.cost <= 0:
        return {"status": "invalid", "message": "The purchase cost must be more than zero."}
    if purchase.financing not in ("cash", "loan"):
        return {"status": "invalid", "message": "Financing must be 'cash' or 'loan'."}
    if purchase.financing == "loan" and not (0 <= purchase.down_payment_pct < 100):
        return {"status": "invalid", "message": "A loan needs a down payment below 100%."}
    if ts(purchase.purchase_date) < ts(as_of):
        return {"status": "invalid", "message": "The purchase date must be on or after the as-of date."}
    buffer = default_buffer(ledger, as_of) if min_buffer is None else float(min_buffer)
    end = ts(as_of) + pd.Timedelta(days=horizon_days)
    results = []
    for sc in scenarios:
        base_opt = ForecastOptions(
            horizon_days=horizon_days,
            receivable_delay_days=sc.receivable_delay_days,
            receivable_collection_pct=sc.receivable_collection_pct,
            include_overdue_receivables=sc.include_overdue_receivables,
            include_run_rate=include_run_rate,
            min_buffer=buffer,
        )
        without = forecast_cash_flow(ledger, balances, obligations, as_of, base_opt)
        if without["status"] != "ok":
            return without
        flows = purchase_flows(purchase, sc, end)
        with_p = forecast_cash_flow(ledger, balances, obligations, as_of, replace(base_opt, extra_flows=flows))
        results.append(
            {
                "scenario": sc.key,
                "label": sc.label,
                "settings": {
                    "benefit_multiplier": sc.benefit_multiplier,
                    "benefit_delay_months": sc.benefit_delay_months,
                    "receivable_delay_days": sc.receivable_delay_days,
                    "receivable_collection_pct": sc.receivable_collection_pct,
                    "overdue_receivables_counted": sc.include_overdue_receivables,
                },
                "without_purchase": {
                    "end_balance": without["checkpoints"][-1]["balance"],
                    "lowest_balance": without["lowest_balance"],
                    "lowest_balance_date": without["lowest_balance_date"],
                },
                "with_purchase": {
                    "end_balance": with_p["checkpoints"][-1]["balance"],
                    "lowest_balance": with_p["lowest_balance"],
                    "lowest_balance_date": with_p["lowest_balance_date"],
                    "first_date_below_buffer": with_p["first_date_below_buffer"],
                    "first_negative_date": with_p["first_negative_date"],
                },
                "purchase_cash_impact": money(sum(f["amount"] for f in flows)),
                "daily_with": [{"date": r["date"], "balance": r["balance"]} for r in with_p["daily"]],
                "daily_without": [{"date": r["date"], "balance": r["balance"]} for r in without["daily"]],
            }
        )
    by = {r["scenario"]: r for r in results}
    base, down = by.get("base"), by.get("downside")
    if down and down["with_purchase"]["lowest_balance"] >= buffer:
        verdict, tone = "Affordable — cash stays above your buffer even in the downside case.", "good"
    elif base and base["with_purchase"]["lowest_balance"] >= buffer:
        verdict, tone = "Affordable in the base case, but the downside case breaches your cash buffer.", "caution"
    elif base and base["with_purchase"]["lowest_balance"] >= 0:
        verdict, tone = "Tight — cash stays positive in the base case but falls below your buffer.", "caution"
    else:
        verdict, tone = "Not affordable on current numbers — cash goes negative in the base case.", "bad"

    instalment = emi(purchase.cost * (1 - purchase.down_payment_pct / 100), purchase.loan_rate_pct, purchase.tenure_months) if purchase.financing == "loan" else 0.0
    net_monthly = purchase.monthly_benefit - purchase.monthly_running_cost
    payback = money((purchase.cost + purchase.one_time_costs) / net_monthly) if net_monthly > 0 else None
    loan_interest = money(instalment * purchase.tenure_months - purchase.cost * (1 - purchase.down_payment_pct / 100)) if instalment else 0.0
    return {
        "status": "ok",
        "purchase": purchase.__dict__,
        "as_of": str(ts(as_of).date()),
        "horizon_days": horizon_days,
        "buffer": buffer,
        "buffer_basis": "your setting" if min_buffer is not None else "one month of typical operating expenses (last 3 full months)",
        "upfront_cash": money((purchase.cost if purchase.financing == "cash" else purchase.cost * purchase.down_payment_pct / 100) + purchase.one_time_costs),
        "emi": instalment,
        "total_loan_interest": loan_interest,
        "payback_months": payback,
        "verdict": verdict,
        "verdict_tone": tone,
        "scenarios": results,
        "evidence": Evidence(
            method=(
                "For each scenario the cash forecast is run without and with the purchase's cash flows "
                "(payment or down payment, EMIs, one-time and running costs, expected benefit). The verdict "
                "compares the lowest balance with the buffer. Payback = (cost + one-time costs) ÷ (monthly "
                "benefit − running cost), ignoring financing."
            ),
            assumptions=tuple(
                f"{s.label}: benefit ×{s.benefit_multiplier:g}"
                + (f", starting {s.benefit_delay_months} months late" if s.benefit_delay_months else "")
                + (f"; receivables {s.receivable_delay_days} days late, {s.receivable_collection_pct:g}% collected" if s.receivable_delay_days or s.receivable_collection_pct != 100 else "")
                + ("; overdue receivables collected in 30 days" if s.include_overdue_receivables else "; overdue receivables not counted")
                for s in scenarios
            )
            + ("The expected benefit is your estimate, not something FinPilot has verified.",),
            limitations=(
                "Taxes, depreciation and the effect of the purchase on other costs are not modelled.",
                "Scenarios are illustrations under the stated settings, not probabilities.",
            ),
        ).to_dict(),
    }
