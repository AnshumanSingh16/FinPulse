"""
What-if simulators on a monthly baseline from the last full months:

  sales S, variable costs V (stock, packaging, freight — they move with volume), fixed costs F.
  monthly profit = S − V − F  (the same estimated operating profit as everywhere else)

Every simulator states its baseline and assumptions and returns the arithmetic, not a forecast.
"""

from __future__ import annotations

import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.common import last_full_month, money, prepare_ledger, ts
from finpilot.engine.decision import default_buffer, emi
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow

VARIABLE = {"raw materials", "packaging", "logistics", "purchases"}


def baseline(ledger: pd.DataFrame, as_of, months: int = 3) -> dict:
    df = prepare_ledger(ledger)
    _, end = last_full_month(as_of)
    start = (end - pd.DateOffset(months=months - 1)).replace(day=1)
    w = df[(df["date"] >= start) & (df["date"] <= end)]
    sales = float(w.loc[w["cls"] == "revenue", "amount"].sum()) / months
    cost_rows = w[w["cls"].isin(["operating", "unclassified_out"])]
    signed = cost_rows["amount"].where(cost_rows["direction"] == "out", -cost_rows["amount"])
    var = float(signed[cost_rows["category"].str.lower().isin(VARIABLE)].sum()) / months
    total = float(signed.sum()) / months
    fixed = total - var
    return {"months": months, "period": [str(start.date()), str(end.date())], "sales": money(sales), "variable": money(var), "fixed": money(fixed),
            "profit": money(sales - total), "contribution_pct": round((sales - var) / sales * 100, 1) if sales else None}


def _ev(method: str, b: dict, *assume: str) -> dict:
    return Evidence(
        method=method,
        assumptions=(f"Baseline: monthly averages for {b['period'][0]} to {b['period'][1]} — sales {b['sales']:,.0f}, "
                     f"stock & delivery costs {b['variable']:,.0f}, other running costs {b['fixed']:,.0f}.",) + assume,
        limitations=("A what-if calculation on your past averages, not a prediction. Customers' real response may differ.",),
        period=tuple(b["period"]),
    ).to_dict()


def price_change(ledger, as_of, price_pct: float, volume_pct: float) -> dict:
    b = baseline(ledger, as_of)
    S, V, F = b["sales"], b["variable"], b["fixed"]
    if not S:
        return {"status": "insufficient_data", "message": "Needs a few months of sales to compare against."}
    p, v = price_pct / 100, volume_pct / 100
    new_sales = S * (1 + p) * (1 + v)
    new_var = V * (1 + v)
    new_profit = new_sales - new_var - F
    denom = S * (1 + p) - V
    breakeven = ((S - V) / denom - 1) * 100 if denom > 0 else None
    return {"status": "ok", "baseline": b, "new_sales": money(new_sales), "new_profit": money(new_profit),
            "monthly_change": money(new_profit - b["profit"]), "yearly_change": money((new_profit - b["profit"]) * 12),
            "breakeven_volume_pct": round(breakeven, 1) if breakeven is not None else None,
            "evidence": _ev("New sales = sales × (1 + price change) × (1 + volume change). Stock & delivery costs move with volume; other costs stay the same. "
                            "Break-even volume = the drop in units sold at which profit is unchanged.", b,
                            f"Prices change by {price_pct:g}% and units sold change by {volume_pct:g}%.")}


def discount(ledger, as_of, discount_pct: float, uplift_pct: float, weeks: int) -> dict:
    b = baseline(ledger, as_of)
    S, V = b["sales"], b["variable"]
    if not S:
        return {"status": "insufficient_data", "message": "Needs a few months of sales to compare against."}
    frac = weeks * 7 / 30.4
    d, u = discount_pct / 100, uplift_pct / 100
    extra_sales = S * frac * ((1 - d) * (1 + u) - 1)
    extra_var = V * frac * u
    change = extra_sales - extra_var
    need = None
    if (1 - d) * S - V > 0:
        need = ((S - V) / ((1 - d) * S - V) - 1) * 100
    return {"status": "ok", "baseline": b, "period_sales_change": money(extra_sales), "profit_change": money(change),
            "uplift_needed_pct": round(need, 1) if need is not None else None,
            "evidence": _ev("During the offer: sales × (1 − discount) × (1 + extra customers); stock costs grow with the extra volume. "
                            "Uplift needed = extra volume at which profit is unchanged.", b,
                            f"A {discount_pct:g}% discount for {weeks} weeks brings {uplift_pct:g}% more volume.")}


def hire(ledger, balances, obligations, as_of, salary: float, extra_sales: float, start_months: int = 0, one_time: float = 0.0, horizon_days: int = 180) -> dict:
    b = baseline(ledger, as_of)
    cpct = (b["contribution_pct"] or 0) / 100
    change = extra_sales * cpct - salary
    breakeven = salary / cpct if cpct > 0 else None
    a = ts(as_of)
    flows = []
    if one_time:
        flows.append({"date": a + pd.Timedelta(days=1), "amount": -one_time, "label": "Hiring: one-time cost"})
    for k in range(1, horizon_days // 30 + 1):
        d = a + pd.DateOffset(months=k)
        flows.append({"date": d, "amount": -salary, "label": "New staff salary"})
        if k > start_months and extra_sales:
            flows.append({"date": d, "amount": extra_sales * cpct, "label": "Extra sales margin from new staff"})
    cash = _cash_effect(ledger, balances, obligations, a, flows, horizon_days)
    return {"status": "ok", "baseline": b, "monthly_change": money(change), "yearly_change": money(change * 12),
            "breakeven_sales": money(breakeven) if breakeven else None, "cash": cash,
            "evidence": _ev("Monthly effect = extra sales × your margin after stock costs − salary. Break-even = salary ÷ that margin. "
                            "Cash effect re-runs your forecast with the salary and extra margin added.", b,
                            f"Salary {salary:,.0f}/month; extra sales {extra_sales:,.0f}/month starting after {start_months} month(s).")}


def loan(ledger, balances, obligations, as_of, amount: float, rate_pct: float, years: float, horizon_days: int = 180) -> dict:
    months = int(round(years * 12))
    if amount <= 0 or months <= 0:
        return {"status": "invalid", "message": "Enter a loan amount and tenure."}
    inst = emi(amount, rate_pct, months)
    a = ts(as_of)
    flows = [{"date": a + pd.Timedelta(days=1), "amount": amount, "label": "Loan received"}]
    for k in range(1, horizon_days // 30 + 1):
        flows.append({"date": a + pd.DateOffset(months=k), "amount": -inst, "label": f"EMI {k}"})
    b = baseline(ledger, as_of)
    cover = round(b["profit"] / inst, 2) if inst and b["profit"] else None
    return {"status": "ok", "emi": inst, "months": months, "total_interest": money(inst * months - amount), "total_repaid": money(inst * months),
            "emi_share_of_profit_pct": round(inst / b["profit"] * 100, 1) if b["profit"] > 0 else None, "profit_cover": cover,
            "baseline": b, "cash": _cash_effect(ledger, balances, obligations, a, flows, horizon_days),
            "evidence": _ev("EMI from the standard reducing-balance formula. Profit cover = average monthly profit ÷ EMI (lenders often look for 1.25 or more).", b,
                            f"Loan of {amount:,.0f} at {rate_pct:g}% for {months} months, received tomorrow.")}


def _cash_effect(ledger, balances, obligations, a, flows, horizon_days) -> dict | None:
    buf = default_buffer(ledger, a)
    base = forecast_cash_flow(ledger, balances, obligations, a, ForecastOptions(horizon_days=horizon_days, include_run_rate=True, min_buffer=buf))
    if base["status"] != "ok":
        return None
    with_ = forecast_cash_flow(ledger, balances, obligations, a, ForecastOptions(horizon_days=horizon_days, include_run_rate=True, min_buffer=buf, extra_flows=flows))
    return {"lowest_without": base["lowest_balance"], "lowest_with": with_["lowest_balance"], "lowest_date": with_["lowest_balance_date"],
            "end_without": base["checkpoints"][-1]["balance"], "end_with": with_["checkpoints"][-1]["balance"], "cushion": buf,
            "below_cushion": with_["first_date_below_buffer"], "negative": with_["first_negative_date"],
            "series": [{"date": x["date"], "with": x["balance"], "without": y["balance"]} for x, y in zip(with_["daily"], base["daily"])]}
