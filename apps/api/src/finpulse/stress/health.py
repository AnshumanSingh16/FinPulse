"""Financial Health impact: re-score the passport on projected metrics.

Both the baseline projection and the scenario are scored the same way — the passport's metrics
that a projection can speak to are replaced by their projected values, the rest keep today's
values — so the difference between the two isolates the effect of the shock.
"""

from __future__ import annotations

from decimal import Decimal

from finpulse.analytics.registry import CATALOGUE, available, coefficient_of_variation, unavailable
from finpulse.analytics.schemas import FinancialMetricsReport, Metric, Period
from finpulse.core.dates import month_end
from finpulse.scoring import ScoringModel, score_passport
from finpulse.scoring.schemas import Passport
from finpulse.stress.projection import Simulation

PROJECTED_METRICS = (
    "cashflow.net_margin",
    "cashflow.positive_months",
    "income.stability",
    "revenue.growth",
    "revenue.volatility",
    "buffer.months",
    "cash.runway",
    "liquidity.ratio",
    "debt.service_burden",
    "debt.leverage",
    "debt.new_loans_6m",
    "liquidity.overdraft_utilisation",
)


def projected_metrics(sim: Simulation, label: str) -> dict[str, Metric]:
    b, months = sim.baseline, sim.months
    period = Period(start=months[0].month, end=month_end(months[-1].month), label=label)
    note = [f"Projected: {label}."]

    def ok(code: str, value: Decimal) -> Metric:
        return available(CATALOGUE[code], value, period, notes=note)

    def na(code: str, reason: str) -> Metric:
        return unavailable(CATALOGUE[code], period, "not_applicable", reason)

    out: dict[str, Metric] = {}
    received = sum(m.money_in - m.borrowed for m in months)
    net = sum(m.net_before_borrowing for m in months)
    if received > 0:
        out["cashflow.net_margin"] = ok("cashflow.net_margin", Decimal(net) / received)
    out["cashflow.positive_months"] = ok(
        "cashflow.positive_months",
        Decimal(sum(1 for m in months if m.net_before_borrowing >= 0)) / len(months),
    )
    receipts = [m.receipts for m in months]
    cv = coefficient_of_variation(receipts)
    with_receipts = sum(1 for r in receipts if r > 0)
    stability = (
        Decimal(0)
        if cv is None
        else (100 * (1 - min(cv, Decimal(1))) * Decimal(with_receipts) / len(receipts))
    )
    out["income.stability"] = ok("income.stability", stability)
    revenue = [m.revenue for m in months]
    if b.revenue > 0:
        avg = Decimal(sum(revenue)) / len(revenue)
        out["revenue.growth"] = ok("revenue.growth", avg / b.revenue - 1)
    rev_cv = coefficient_of_variation(revenue)
    if rev_cv is not None:
        out["revenue.volatility"] = ok("revenue.volatility", rev_cv)
    outflows = sim.average_outflows()
    if outflows > 0:
        out["buffer.months"] = ok("buffer.months", max(0, sim.closing_balance) / outflows)
    runway = sim.runway_months()
    out["cash.runway"] = (
        ok("cash.runway", runway)
        if runway is not None
        else na("cash.runway", "Not burning cash over the projection.")
    )
    ratio, _ = sim.liquidity()
    out["liquidity.ratio"] = (
        ok("liquidity.ratio", ratio)
        if ratio is not None
        else na("liquidity.ratio", "No current liabilities at the end of the projection.")
    )
    total_receipts = sum(receipts)
    if total_receipts > 0:
        out["debt.service_burden"] = ok(
            "debt.service_burden", Decimal(sum(m.debt_service for m in months)) / total_receipts
        )
    annual_revenue = Decimal(sum(revenue)) * 12 / len(revenue)
    if annual_revenue > 0:
        out["debt.leverage"] = ok(
            "debt.leverage", Decimal(max(0, sim.debt_at_end())) / annual_revenue
        )
    current_new = next(m for m in b.report.metrics if m.code == "debt.new_loans_6m").value or 0
    out["debt.new_loans_6m"] = ok("debt.new_loans_6m", Decimal(current_new) + sim.levers.new_loans)
    if b.overdraft_limit > 0:
        drawn = Decimal(sum(max(0, -m.closing_balance) for m in months)) / len(months)
        out["liquidity.overdraft_utilisation"] = ok(
            "liquidity.overdraft_utilisation", drawn / b.overdraft_limit
        )
    else:
        out["liquidity.overdraft_utilisation"] = na(
            "liquidity.overdraft_utilisation", "No overdraft facility."
        )
    return out


def stressed_report(
    report: FinancialMetricsReport, sim: Simulation, label: str
) -> FinancialMetricsReport:
    replacements = projected_metrics(sim, label)
    return report.model_copy(
        update={"metrics": [replacements.get(m.code, m) for m in report.metrics]}
    )


def projected_passport(
    report: FinancialMetricsReport, sim: Simulation, label: str, model: ScoringModel
) -> Passport:
    return score_passport(stressed_report(report, sim, label), model)
