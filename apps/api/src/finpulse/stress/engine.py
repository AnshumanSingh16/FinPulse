"""Run a stress test: baseline projection vs. scenario projection, compared and explained.

Pure and deterministic — same data, as_of and request ⇒ same result. No LLM is involved; the
``evidence`` list exists so that a later explanation layer can cite numbers instead of computing
them.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from finpulse.analytics import compute_report
from finpulse.analytics.context import Context, month_label
from finpulse.analytics.inputs import FinancialData
from finpulse.analytics.registry import inr
from finpulse.core.money import format_inr
from finpulse.scoring import ScoringModel, explain_change, score_passport
from finpulse.scoring.schemas import Passport
from finpulse.stress import risk
from finpulse.stress.baseline import Baseline, build_baseline
from finpulse.stress.health import projected_passport
from finpulse.stress.presets import PRESETS
from finpulse.stress.projection import Simulation, simulate
from finpulse.stress.schemas import (
    AppliedShock,
    Comparison,
    Evidence,
    FailurePoint,
    HealthImpact,
    ProjectedMonth,
    Projection,
    RiskChange,
    ScenarioInfo,
    StressTestResult,
)
from finpulse.stress.shocks import SHOCKS, Levers, ShockParams, ShockSpec

ENGINE_VERSION = "1.0.0"
MAX_HORIZON = 24
DISCLAIMER = (
    "Hypothetical scenario projected from the last three complete months of actual data with "
    "simple, documented assumptions. It is not a forecast and not a credit assessment. The "
    "Financial Health figures use the prototype FinPulse Financial Passport, which is not a "
    "credit score."
)


class StressTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: str | None = Field(None, description="A named scenario; see /meta/stress-scenarios")
    shocks: list[ShockSpec] | None = Field(
        None, min_length=1, max_length=10, description="Shocks applied together, in order"
    )
    horizon_months: int = Field(6, ge=1, le=MAX_HORIZON)
    as_of: date | None = None
    name: str | None = Field(None, max_length=120, description="Label for a custom scenario")

    @model_validator(mode="after")
    def _one_source(self) -> StressTestRequest:
        if (self.preset is None) == (self.shocks is None):
            raise ValueError("give exactly one of 'preset' or 'shocks'")
        if self.preset is not None and self.preset not in PRESETS:
            raise ValueError(f"unknown preset {self.preset!r}; known: {', '.join(PRESETS)}")
        return self


_SHOCK_LIST = TypeAdapter(list[ShockSpec])


def resolve_shocks(request: StressTestRequest) -> tuple[str | None, list[ShockParams]]:
    """The shocks to apply and the scenario's name, if it has one before defaults resolve."""
    if request.preset is not None:
        name, raw = PRESETS[request.preset]
        return name, list(_SHOCK_LIST.validate_python(raw))
    return request.name, list(request.shocks or [])


# --- helpers ------------------------------------------------------------------------------------


def q(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _projection(sim: Simulation, passport: Passport) -> Projection:
    ratio, _ = sim.liquidity()
    runway = sim.runway_months()
    peak = sim.peak_overdraft_utilisation()
    low = sim.minimum
    failure = sim.failure
    as_of = sim.baseline.as_of
    return Projection(
        revenue=inr(sum(m.revenue for m in sim.months)),
        expenses=inr(sum(m.expenses for m in sim.months)),
        net_cash_flow=inr(sum(m.net for m in sim.months)),
        closing_balance=inr(sim.closing_balance),
        minimum_balance=inr(low.closing_balance),
        minimum_balance_month=month_label(low.month),
        liquidity_ratio=None if ratio is None else q(ratio, "0.0001"),
        cash_runway_months=None if runway is None else q(runway, "0.1"),
        peak_overdraft_utilisation=None if peak is None else q(peak, "0.0001"),
        financial_health_score=passport.financial_health.score,
        financial_health_band=passport.financial_health.band.code
        if passport.financial_health.band
        else None,
        risk=risk.assess(sim),
        failure_point=None
        if failure is None
        else FailurePoint(
            date=failure.day,
            month=month_label(sim.months[failure.month_index].month),
            months_from_as_of=q(Decimal((failure.day - as_of).days) / Decimal("30.4375"), "0.1"),
            shortfall_at_month_end=inr(failure.shortfall),
        ),
        months=[
            ProjectedMonth(
                month=m.month,
                label=month_label(m.month),
                revenue=inr(m.revenue),
                expenses=inr(m.expenses),
                money_in=inr(m.money_in),
                money_out=inr(m.money_out),
                debt_service=inr(m.debt_service),
                overdraft_interest=inr(m.overdraft_interest),
                net_cash_flow=inr(m.net),
                closing_balance=inr(m.closing_balance),
                available_funds=inr(m.closing_balance + sim.baseline.overdraft_limit),
                funds_exhausted=m.closing_balance < -sim.baseline.overdraft_limit,
            )
            for m in sim.months
        ],
    )


Better = Literal["higher", "lower"]


def _compare(
    key: str,
    label: str,
    unit: Any,
    a: Decimal | None,
    b: Decimal | None,
    better: Better,
    none_means: Literal["best", "missing"] = "missing",
) -> Comparison:
    if a is None or b is None:
        if none_means == "best" and (a is None) != (b is None):
            direction = "worse" if a is None else "better"
        else:
            direction = "unchanged" if a is None and b is None else "n/a"
        return Comparison(
            key=key,
            label=label,
            unit=unit,
            baseline=a,
            scenario=b,
            absolute_change=None,
            percentage_change=None,
            direction=direction,
        )
    change = b - a
    pct = None if a == 0 else q(change / abs(a), "0.0001")
    if change == 0:
        direction = "unchanged"
    elif (change > 0) == (better == "higher"):
        direction = "better"
    else:
        direction = "worse"
    return Comparison(
        key=key,
        label=label,
        unit=unit,
        baseline=a,
        scenario=b,
        absolute_change=change,
        percentage_change=pct,
        direction=direction,
    )


def _comparisons(base: Projection, scen: Projection) -> list[Comparison]:
    return [
        _compare(
            "revenue", "Projected revenue (total)", "INR", base.revenue, scen.revenue, "higher"
        ),
        _compare(
            "expenses", "Projected expenses (total)", "INR", base.expenses, scen.expenses, "lower"
        ),
        _compare(
            "net_cash_flow",
            "Projected net cash flow (total)",
            "INR",
            base.net_cash_flow,
            scen.net_cash_flow,
            "higher",
        ),
        _compare(
            "closing_balance",
            "Projected cash balance at horizon end",
            "INR",
            base.closing_balance,
            scen.closing_balance,
            "higher",
        ),
        _compare(
            "minimum_balance",
            "Lowest projected cash balance",
            "INR",
            base.minimum_balance,
            scen.minimum_balance,
            "higher",
        ),
        _compare(
            "liquidity_ratio",
            "Liquidity ratio at horizon end",
            "ratio",
            base.liquidity_ratio,
            scen.liquidity_ratio,
            "higher",
            "best",
        ),
        _compare(
            "cash_runway_months",
            "Cash runway",
            "months",
            base.cash_runway_months,
            scen.cash_runway_months,
            "higher",
            "best",
        ),
        _compare(
            "peak_overdraft_utilisation",
            "Peak overdraft utilisation",
            "ratio",
            base.peak_overdraft_utilisation,
            scen.peak_overdraft_utilisation,
            "lower",
        ),
        _compare(
            "financial_health_score",
            "Financial Health score (projected)",
            "score",
            base.financial_health_score,
            scen.financial_health_score,
            "higher",
        ),
    ]


def rs(minor: int) -> str:
    """Whole rupees from minor units: 123456700 → ₹12,34,567."""
    return format_inr(minor)[:-3]


def rd(rupees_value: Decimal) -> str:
    return rs(int(rupees_value * 100))


def _baseline_evidence(b: Baseline, horizon: int) -> list[Evidence]:
    debt_total = sum(b.scheduled_debt)
    return [
        Evidence(
            id="baseline.period",
            kind="baseline",
            text=(
                f"Baseline months are {b.period_label} ({len(b.months)} complete month(s) before "
                f"{b.as_of}); the projection covers the next {horizon} month(s) from "
                f"{b.projection_months[0]:%b %Y}."
            ),
            values={
                "baseline_months": len(b.months),
                "horizon_months": horizon,
                "projection_start": b.projection_months[0].isoformat(),
            },
        ),
        Evidence(
            id="baseline.revenue_expenses",
            kind="baseline",
            text=(
                f"A typical month: revenue {rs(b.revenue)} (excluding GST), purchases "
                f"{rs(b.purchases)} and other operating costs {rs(b.opex)}."
            ),
            values={
                "monthly_revenue": inr(b.revenue),
                "monthly_purchases": inr(b.purchases),
                "monthly_operating_costs": inr(b.opex),
            },
            metric_codes=["revenue.monthly", "expenses.monthly"],
        ),
        Evidence(
            id="baseline.cash",
            kind="baseline",
            text=(
                f"A typical month's cash: {rs(b.operating_receipts)} received from customers, "
                f"{rs(b.supplier_payments)} paid to suppliers, {rs(b.opex)} other operating "
                f"costs, {rs(b.other_outflows)} drawings, taxes and other payments, "
                f"{rs(b.other_inflows)} other receipts."
            ),
            values={
                "monthly_operating_receipts": inr(b.operating_receipts),
                "monthly_supplier_payments": inr(b.supplier_payments),
                "monthly_operating_costs": inr(b.opex),
                "monthly_other_outflows": inr(b.other_outflows),
                "monthly_other_inflows": inr(b.other_inflows),
            },
            sources=[
                b.sources[k] for k in ("receipts", "supplier_payments", "opex", "other_outflows")
            ],
        ),
        Evidence(
            id="baseline.debt",
            kind="baseline",
            text=(
                f"{len(b.loans)} loan(s) with {rs(b.debt_outstanding)} principal outstanding; "
                f"{rs(debt_total)} of instalments fall due in the horizon (from the actual "
                "schedules, overdue instalments assumed paid in the first month)."
            ),
            values={
                "loans": len(b.loans),
                "debt_outstanding": inr(b.debt_outstanding),
                "instalments_due_in_horizon": inr(debt_total),
            },
            metric_codes=["debt.outstanding"],
            sources=[b.sources["loans"]],
        ),
        Evidence(
            id="baseline.balance",
            kind="baseline",
            text=(
                f"Opening balance {rs(b.opening_balance)} at {b.as_of}, overdraft limit "
                f"{rs(b.overdraft_limit)}; overdraft interest assumed at "
                f"{(b.overdraft_rate * 100).normalize():f}% a year."
            ),
            values={
                "opening_balance": inr(b.opening_balance),
                "overdraft_limit": inr(b.overdraft_limit),
                "overdraft_rate": b.overdraft_rate,
            },
            metric_codes=["cash.balance"],
        ),
    ]


def _outcome_evidence(
    base: Projection, scen: Projection, change: RiskChange, health: HealthImpact
) -> list[Evidence]:
    out = [
        Evidence(
            id="outcome.cash",
            kind="outcome",
            text=(
                f"Cash at the end of the horizon: {rd(base.closing_balance)} in the baseline vs "
                f"{rd(scen.closing_balance)} under the scenario; the lowest point is "
                f"{rd(scen.minimum_balance)} in {scen.minimum_balance_month}."
            ),
            values={
                "baseline_closing": base.closing_balance,
                "scenario_closing": scen.closing_balance,
                "scenario_minimum": scen.minimum_balance,
                "scenario_minimum_month": scen.minimum_balance_month,
            },
        ),
        Evidence(
            id="outcome.risk",
            kind="outcome",
            text=change.summary + " " + " ".join(scen.risk.reasons),
            values={
                "baseline": change.baseline,
                "scenario": change.scenario,
                "steps": change.steps,
            },
        ),
        Evidence(
            id="outcome.health",
            kind="outcome",
            text=health.summary,
            values={
                "baseline_projected": health.baseline_projected_score,
                "scenario": health.scenario_score,
                "change": health.change,
            },
        ),
    ]
    if scen.failure_point is not None:
        f = scen.failure_point
        out.insert(
            1,
            Evidence(
                id="outcome.failure_point",
                kind="outcome",
                text=(
                    f"Available funds, including the overdraft, run out around {f.date} "
                    f"({f.months_from_as_of} months after as_of); by the end of {f.month} the "
                    f"shortfall beyond the overdraft limit is {rd(f.shortfall_at_month_end)}."
                ),
                values={
                    "date": f.date.isoformat(),
                    "months_from_as_of": f.months_from_as_of,
                    "shortfall_at_month_end": f.shortfall_at_month_end,
                },
                metric_codes=["cash.runway"],
            ),
        )
    return out


# --- entry point --------------------------------------------------------------------------------


def run_stress_test(
    data: FinancialData, as_of: date, request: StressTestRequest, model: ScoringModel
) -> StressTestResult:
    report = compute_report(data, as_of)
    baseline = build_baseline(Context(data, as_of), report, request.horizon_months)
    name, raw_shocks = resolve_shocks(request)

    base_sim = simulate(Levers(request.horizon_months, baseline))
    levers = Levers(request.horizon_months, baseline)
    applied: list[AppliedShock] = []
    for params in raw_shocks:
        shock = SHOCKS[params.type]
        resolved = shock.resolve(params, baseline)
        shock.apply(resolved, levers)
        applied.append(
            AppliedShock(
                type=shock.code,
                name=shock.name,
                parameters=resolved.model_dump(mode="json"),
                description=shock.describe(resolved),
            )
        )
    scen_sim = simulate(levers)
    name = name or " + ".join(s.description for s in applied)

    first, last = baseline.projection_months[0], baseline.projection_months[-1]
    window = f"{month_label(first)} to {month_label(last)}"
    base_passport = projected_passport(report, base_sim, f"baseline projection, {window}", model)
    scen_passport = projected_passport(report, scen_sim, f"scenario '{name}', {window}", model)
    current = score_passport(report, model)
    base = _projection(base_sim, base_passport)
    scen = _projection(scen_sim, scen_passport)

    moved = risk.steps(base.risk.level, scen.risk.level)
    risk_change = RiskChange(
        baseline=base.risk.level,
        scenario=scen.risk.level,
        steps=moved,
        escalated=moved > 0,
        summary=(
            f"Risk {'rises' if moved > 0 else 'falls' if moved < 0 else 'stays'} "
            f"{'from ' + base.risk.label + ' to ' if moved else 'at '}{scen.risk.label}."
        ),
    )
    change = explain_change(base_passport, scen_passport)
    health = HealthImpact(
        current_score=current.financial_health.score,
        baseline_projected_score=base_passport.financial_health.score,
        scenario_score=scen_passport.financial_health.score,
        change=change.delta if change else None,
        baseline_band=base.financial_health_band,
        scenario_band=scen.financial_health_band,
        dimensions=change.dimensions if change else [],
        drivers=change.drivers if change else [],
        summary=(
            change.summary.replace("Financial health", "Projected Financial Health", 1)
            if change
            else "Financial Health could not be scored for this projection."
        ),
    )
    return StressTestResult(
        entity=report.entity,
        as_of=as_of,
        horizon_months=request.horizon_months,
        projection_start=baseline.projection_months[0],
        scenario=ScenarioInfo(preset=request.preset, name=name, shocks=applied),
        baseline=base,
        stressed=scen,
        comparisons=_comparisons(base, scen),
        risk_change=risk_change,
        health_impact=health,
        evidence=_baseline_evidence(baseline, request.horizon_months)
        + levers.evidence
        + _outcome_evidence(base, scen, risk_change, health),
        engine_version=ENGINE_VERSION,
        disclaimer=DISCLAIMER,
    )
