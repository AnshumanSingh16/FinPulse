"""The early-warning rules. Each rule reads the data (through snapshots at the dates it compares),
computes one measure, and the shared grading turns that measure into a severity using the tiers
in the configuration. No thresholds live here — only logic — and no language model is involved.

Grading, the same for every rule:
  1. the measure is compared with the rule's configured tiers (low → critical);
  2. if the rule finds the condition present but **not getting worse** (``deteriorating`` is
     False), the warning is reported one severity lower, as ``persistent`` — early warning is
     about change, and a stable weakness is the passport's business;
  3. below the lowest tier (after that step) the rule is clear.

Adding a rule: subclass ``Rule`` (or ``LevelRule`` for "metric level + adverse change" rules),
decorate it with ``@register``, and add its section to the configuration file.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, ClassVar, Literal

from finpulse.analytics.context import Context, month_label
from finpulse.analytics.inputs import Document, Installment, Txn
from finpulse.analytics.registry import CATALOGUE, inr, source
from finpulse.analytics.schemas import Period, Unit
from finpulse.core.dates import add_months, month_end
from finpulse.early_warning.config import (
    SEVERITIES,
    Direction,
    RuleParams,
    Severity,
)
from finpulse.early_warning.schemas import Category, MetricRef, RuleState, WarningEvidence
from finpulse.early_warning.snapshots import History, months_back
from finpulse.scoring.format import format_value

ZERO, ONE = Decimal(0), Decimal(1)
Values = dict[str, Decimal | int | str | None]

# --- formatting -----------------------------------------------------------------------------------


def q(value: Decimal, places: str = "0.0001") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def fmt(value: Decimal | None, unit: Unit, *, multiple: bool = False) -> str:
    """``multiple`` shows a ratio as "0.95×" (for ratios that are not shares, such as liquidity)."""
    if multiple and value is not None:
        return f"{q(value, '0.01')}×"
    return format_value(value, unit)


def signed_pct(value: Decimal) -> str:
    n = q(value * 100, "1")
    return f"+{n}%" if n > 0 else f"{n}%".replace("-", "−")


def day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def months_text(months: list[date]) -> str:
    return f"{months[0]:%b}–{months[-1]:%b %Y}" if len(months) > 1 else f"{months[0]:%b %Y}"


def metric_ref(code: str) -> MetricRef:
    d = CATALOGUE[code]
    return MetricRef(code=code, name=d.name, unit=d.unit, derived=False)


def as_of_period(d: date) -> Period:
    return Period(start=d, end=d, label="as_of")


def days_period(end: date, days: int) -> Period:
    return Period(start=end - timedelta(days=days - 1), end=end, label=f"trailing_{days}_days")


# --- results -------------------------------------------------------------------------------------


@dataclass
class Skip:
    """The rule did not produce a finding: ``clear`` or why it could not be evaluated."""

    state: RuleState
    reason: str


@dataclass
class Finding:
    measure: Decimal
    measure_label: str
    measure_unit: Unit
    deteriorating: bool
    title: str
    description: str
    current: Decimal | None
    previous: Decimal | None
    current_period: Period
    previous_period: Period | None
    evidence: list[WarningEvidence]
    metric: MetricRef | None = None  # defaults to the rule's metric
    severity_floor: Severity | None = None
    persistent_title: str | None = None
    # Tiers are multiplied by this (≥ 1) for entities whose figures normally vary more.
    scale: Decimal = ONE


@dataclass
class Outcome:
    rule: str
    state: RuleState
    reason: str | None = None
    finding: Finding | None = None
    severity: Severity | None = None
    tier: Severity | None = None
    tier_value: Decimal | None = None


def rank(severity: Severity) -> int:
    return SEVERITIES.index(severity)


# --- the rule base ------------------------------------------------------------------------------


class Rule:
    code: ClassVar[str]
    about: ClassVar[str]
    category: ClassVar[Category]
    metric: ClassVar[str]
    direction: ClassVar[Direction]
    Params: ClassVar[type[RuleParams]] = RuleParams

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        raise NotImplementedError

    def metric_ref(self) -> MetricRef:
        return metric_ref(self.metric)

    def run(self, h: History, as_of: date, p: RuleParams) -> Outcome:
        if not p.enabled:
            return Outcome(self.code, "disabled", "Disabled in the configuration.")
        result = self.evaluate(h, as_of, p)
        if isinstance(result, Skip):
            return Outcome(self.code, result.state, result.reason)
        tier = p.tiers.grade(result.measure / result.scale, self.direction)
        if result.severity_floor is not None and (
            tier is None or rank(result.severity_floor) > rank(tier)
        ):
            tier = result.severity_floor
        if tier is None:
            return Outcome(self.code, "clear", "No threshold crossed.", finding=result)
        severity: Severity | None = tier
        if not result.deteriorating:
            severity = SEVERITIES[rank(tier) - 1] if rank(tier) > 0 else None
        if severity is None:
            return Outcome(
                self.code,
                "clear",
                "The condition is at the lowest tier but is not getting worse.",
                finding=result,
            )
        return Outcome(
            self.code,
            "triggered",
            finding=result,
            severity=severity,
            tier=tier,
            tier_value=getattr(p.tiers, tier) * result.scale,
        )


RULES: dict[str, Rule] = {}


def register[R: type[Rule]](cls: R) -> R:
    if cls.code in RULES:
        raise ValueError(f"rule {cls.code} registered twice")
    RULES[cls.code] = cls()
    return cls


def metric_evidence(
    h: History, at: date, code: str, eid: str, text: str, keys: tuple[str, ...] = ()
) -> WarningEvidence:
    m = h.at(at).metric(code)
    values: Values = {"value": m.value}
    for k in keys:
        if k in m.components:
            values[k] = m.components[k]
    return WarningEvidence(
        id=eid, text=text, values=values, metric_codes=[code], period=m.period, sources=m.sources
    )


# --- level rules: a metric's level, graded, with a check that it is getting worse -----------------


class LevelParams(RuleParams):
    lookback_months: int
    min_change: Decimal
    change_basis: Literal["absolute", "relative"]


class LevelRule(Rule):
    """Grades a catalogue metric's current level. Deteriorating = moved the wrong way by at least
    ``min_change`` since ``lookback_months`` ago."""

    Params = LevelParams
    title: ClassVar[str]
    persistent_title: ClassVar[str]
    context: ClassVar[str] = ""
    evidence_keys: ClassVar[tuple[str, ...]] = ()
    # When the earlier value is missing because the metric did not apply then (e.g. cash runway
    # while the business was not burning cash), the change itself is the deterioration.
    missing_previous_is_worse: ClassVar[bool] = False
    missing_previous_text: ClassVar[str] = "There is no earlier value ({day}) to show a trend."
    multiple: ClassVar[bool] = False  # show the ratio as "0.95×" rather than a percentage

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        now = h.at(as_of).metric(self.metric)
        if now.availability != "available" or now.value is None:
            state: RuleState = (
                "not_applicable" if now.availability == "not_applicable" else "insufficient_data"
            )
            return Skip(state, now.notes[0] if now.notes else "Metric unavailable.")
        cur = now.value
        then = months_back(as_of, p.lookback_months)
        prev = h.at(then).value(self.metric) if h.first_date and then >= h.first_date else None
        unit = CATALOGUE[self.metric].unit
        name = CATALOGUE[self.metric].name
        if prev is None:
            deteriorating = self.missing_previous_is_worse and (
                h.first_date is not None and then >= h.first_date
            )
            change_text = self.missing_previous_text.format(day=day(then))
        else:
            adverse = (cur - prev) if self.direction == "above" else (prev - cur)
            if p.change_basis == "relative":
                adverse = adverse / abs(prev) if prev else (ONE if adverse > 0 else ZERO)
            deteriorating = adverse >= p.min_change
            moved = "up" if cur > prev else "down" if cur < prev else "unchanged"
            change_text = f"It was {fmt(prev, unit, multiple=self.multiple)} on {day(then)}" + (
                "." if moved == "unchanged" else f" ({moved})."
            )
        tail = "" if deteriorating else " It is not getting materially worse."
        cur_text = fmt(cur, unit, multiple=self.multiple)
        prev_text = fmt(prev, unit, multiple=self.multiple)
        evidence = [
            metric_evidence(
                h,
                as_of,
                self.metric,
                "current",
                f"{name} at {day(as_of)}: {cur_text}.",
                self.evidence_keys,
            ),
        ]
        if prev is not None:
            evidence.append(
                metric_evidence(
                    h,
                    then,
                    self.metric,
                    "previous",
                    f"{name} at {day(then)}: {prev_text}.",
                    self.evidence_keys,
                )
            )
        return Finding(
            measure=cur,
            measure_label=name,
            measure_unit=unit,
            deteriorating=deteriorating,
            title=self.title,
            persistent_title=self.persistent_title,
            description=f"{name} is {cur_text}. {change_text}{tail} {self.context}".strip(),
            current=cur,
            previous=prev,
            current_period=now.period,
            previous_period=as_of_period(then) if prev is not None else None,
            evidence=evidence,
        )


@register
class DebtServiceBurden(LevelRule):
    code = "debt_service_burden"
    about = "Loan instalments as a share of money received, and whether that share is rising."
    category = "debt"
    metric = "debt.service_burden"
    direction = "above"
    title = "Debt repayments taking a growing share of income"
    persistent_title = "High debt-service burden"
    context = "This is the share of money received that goes on loan instalments."
    evidence_keys = ("instalments_due", "operating_receipts")


@register
class LiquidityDecline(LevelRule):
    code = "liquidity_decline"
    about = "Liquidity ratio (current assets ÷ current liabilities): how low, and whether falling."
    category = "liquidity"
    metric = "liquidity.ratio"
    direction = "below"
    title = "Liquidity declining"
    persistent_title = "Low liquidity"
    context = "Below 1×, short-term obligations exceed cash plus receivables."
    multiple = True
    evidence_keys = ("cash", "receivables", "payables", "overdraft_drawn")


@register
class RunwayShrinking(LevelRule):
    code = "runway_shrinking"
    about = (
        "Months until available funds (incl. undrawn overdraft) run out at the recent burn rate."
    )
    category = "liquidity"
    metric = "cash.runway"
    direction = "below"
    title = "Cash runway shrinking"
    persistent_title = "Short cash runway"
    context = "Runway = available funds incl. undrawn overdraft ÷ average monthly cash burn."
    evidence_keys = ("available_funds", "average_monthly_net_cash_flow")
    missing_previous_is_worse = True
    missing_previous_text = "On {day} the business was not burning cash."

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        result = super().evaluate(h, as_of, p)
        if isinstance(result, Skip) and result.state == "not_applicable":
            return Skip("clear", "Not burning cash: money in covers money out.")
        return result


@register
class OverdraftReliance(LevelRule):
    code = "overdraft_reliance"
    about = "Average share of the overdraft limit in use over 90 days, and whether rising."
    category = "cash"
    metric = "liquidity.overdraft_utilisation"
    direction = "above"
    title = "Growing reliance on the overdraft"
    persistent_title = "Heavy overdraft use"
    context = "Average share of the overdraft limit drawn over the last 90 days."
    evidence_keys = ("average_drawn", "overdraft_limit", "days_overdrawn")


@register
class CustomerConcentration(LevelRule):
    code = "customer_concentration"
    about = "Largest customer's share of revenue, and whether it is rising."
    category = "concentration"
    metric = "customers.concentration"
    direction = "above"
    title = "Customer concentration rising"
    persistent_title = "High customer concentration"
    context = "Share of revenue from the largest customer over 6 months."
    evidence_keys = ("largest", "top_3_share", "hhi")


@register
class SupplierConcentration(LevelRule):
    code = "supplier_concentration"
    about = "Largest supplier's share of purchases, and whether it is rising."
    category = "concentration"
    metric = "suppliers.concentration"
    direction = "above"
    title = "Supplier concentration rising"
    persistent_title = "High supplier concentration"
    context = "Share of purchases from the largest supplier over 6 months."
    evidence_keys = ("largest", "top_3_share", "hhi")


# --- revenue & expenses ----------------------------------------------------------------------


def three_and_three(ctx: Context) -> tuple[list[date], list[date]] | None:
    months = ctx.window(6)
    if len(months) < 6:
        return None
    return months[3:], months[:3]


def growth(
    ctx: Context, of: Callable[[date], int], recent: list[date], prior: list[date]
) -> Decimal | None:
    before = sum(of(m) for m in prior)
    return Decimal(sum(of(m) for m in recent)) / before - 1 if before > 0 else None


def series_evidence(
    eid: str, text: str, ctx: Context, of: Callable[[date], int], months: list[date], code: str
) -> WarningEvidence:
    return WarningEvidence(
        id=eid,
        text=text,
        values={month_label(m): inr(of(m)) for m in months},
        metric_codes=[code],
        period=Context.months_period(months, f"{len(months)}_months"),
    )


class VolatilityScaled(RuleParams):
    scale_by_volatility: bool
    normal_volatility: Decimal
    max_scale: Decimal


def volatility_scale(h: History, before: date, p: Any) -> tuple[Decimal, WarningEvidence | None]:
    """How much more than "normal" the entity's monthly revenue varied in the 12 months to
    ``before`` (the start of the period being judged, so a fall cannot inflate its own
    allowance). Thresholds are widened by this factor, between 1 and ``max_scale``."""
    if not p.scale_by_volatility or h.first_date is None or before < h.first_date:
        return ONE, None
    cv = h.at(before).value("revenue.volatility")
    if cv is None:
        return ONE, None
    scale = min(p.max_scale, max(ONE, cv / p.normal_volatility)).quantize(Decimal("0.01"))
    note = WarningEvidence(
        id="normal_volatility",
        text=f"Revenue volatility in the 12 months to {day(before)} was {fmt(cv, 'ratio')} "
        f"(normal: {fmt(p.normal_volatility, 'ratio')}), so thresholds are scaled by {scale}.",
        values={"revenue_volatility": cv, "scale": scale},
        metric_codes=["revenue.volatility"],
    )
    return scale, note


class RevenueDeclineParams(VolatilityScaled):
    seasonal_check: bool
    seasonal_tolerance: Decimal


@register
class RevenueDecline(Rule):
    code = "revenue_decline"
    about = "Revenue in the last 3 months vs the 3 before, checked against last year."
    category = "revenue"
    metric = "revenue.growth"
    direction = "below"
    Params = RevenueDeclineParams

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        ctx = h.at(as_of).ctx
        split = three_and_three(ctx)
        if split is None:
            return Skip("insufficient_data", "Needs 6 complete months.")
        recent, prior = split
        g = growth(ctx, ctx.revenue, recent, prior)
        if g is None:
            return Skip("insufficient_data", "No revenue in the earlier 3 months.")
        r_avg = inr(sum(ctx.revenue(m) for m in recent) // 3)
        p_avg = inr(sum(ctx.revenue(m) for m in prior) // 3)
        evidence = [
            series_evidence(
                "monthly_revenue",
                "Monthly revenue (excluding GST) for the last 6 complete months.",
                ctx,
                ctx.revenue,
                prior + recent,
                "revenue.monthly",
            ),
            metric_evidence(
                h,
                as_of,
                "revenue.growth",
                "growth",
                f"Revenue growth (last 3 months vs the 3 before): {signed_pct(g)}.",
            ),
        ]
        yoy = None
        last_year = [add_months(m, -12) for m in recent]
        if p.seasonal_check and ctx.months and last_year[0] >= ctx.months[0]:
            yoy = growth(ctx, ctx.revenue, recent, last_year)
            if yoy is not None:
                evidence.append(
                    series_evidence(
                        "same_months_last_year",
                        f"The same months last year; change since: {signed_pct(yoy)}.",
                        ctx,
                        ctx.revenue,
                        last_year,
                        "revenue.monthly",
                    )
                )
        seasonal = yoy is not None and yoy > p.seasonal_tolerance
        scale, note = volatility_scale(h, month_end(prior[-1]), p)
        if note:
            evidence.append(note)
        text = (
            f"Revenue fell {signed_pct(g)} : {fmt(r_avg, 'INR')} a month in {months_text(recent)} "
            f"against {fmt(p_avg, 'INR')} in {months_text(prior)}."
        ).replace(" :", ":")
        if yoy is not None:
            text += f" Against the same months last year: {signed_pct(yoy)}" + (
                ", so the fall may be seasonal." if seasonal else "."
            )
        return Finding(
            measure=q(g),
            measure_label="Revenue change, last 3 months vs the 3 before",
            measure_unit="ratio",
            deteriorating=not seasonal,
            title="Revenue declining",
            persistent_title="Revenue dip (possibly seasonal)",
            description=text,
            current=r_avg,
            previous=p_avg,
            current_period=Context.months_period(recent, "trailing_3_months"),
            previous_period=Context.months_period(prior, "previous_3_months"),
            evidence=evidence,
            metric=metric_ref("revenue.monthly"),
            scale=scale,
        )


class ExpenseParams(VolatilityScaled):
    min_expense_growth: Decimal
    lookback_months: int


@register
class ExpenseAcceleration(Rule):
    code = "expense_acceleration"
    about = "Expenses growing faster than revenue, and expense growth speeding up."
    category = "expenses"
    metric = "expenses.growth"
    direction = "above"
    Params = ExpenseParams

    @staticmethod
    def growths(ctx: Context) -> tuple[Decimal, Decimal] | None:
        split = three_and_three(ctx)
        if split is None:
            return None
        eg = growth(ctx, ctx.expenses, *split)
        rg = growth(ctx, ctx.revenue, *split)
        return (eg, rg if rg is not None else ZERO) if eg is not None else None

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        ctx = h.at(as_of).ctx
        now = self.growths(ctx)
        if now is None:
            return Skip("insufficient_data", "Needs 6 complete months with expenses.")
        eg, rg = now
        if eg < p.min_expense_growth:
            return Skip("clear", f"Expenses grew {signed_pct(eg)}, under the configured minimum.")
        then = months_back(as_of, p.lookback_months)
        before = self.growths(h.at(then).ctx) if h.first_date and then >= h.first_date else None
        eg_prev = before[0] if before else None
        gap = eg - rg
        recent, prior = three_and_three(ctx) or ([], [])
        scale, note = volatility_scale(h, month_end(prior[-1]), p)
        text = (
            f"Expenses rose {signed_pct(eg)} in {months_text(recent)} against the 3 months "
            f"before, while revenue changed {signed_pct(rg)}: costs are outpacing sales by "
            f"{q(gap * 100, '1')} percentage points."
        )
        if eg_prev is not None:
            text += f" Three months earlier expense growth was {signed_pct(eg_prev)}."
        return Finding(
            measure=q(gap),
            measure_label="Expense growth minus revenue growth (3 months vs the 3 before)",
            measure_unit="ratio",
            deteriorating=eg_prev is None or eg > eg_prev,
            title="Expenses growing faster than revenue",
            persistent_title="Expenses outpacing revenue",
            description=text,
            current=q(eg),
            previous=q(eg_prev) if eg_prev is not None else None,
            current_period=Context.months_period(recent, "trailing_3_months"),
            previous_period=as_of_period(then) if eg_prev is not None else None,
            evidence=[
                series_evidence(
                    "monthly_expenses",
                    "Monthly operating expenses (excluding GST).",
                    ctx,
                    ctx.expenses,
                    prior + recent,
                    "expenses.monthly",
                ),
                series_evidence(
                    "monthly_revenue",
                    "Monthly revenue (excluding GST).",
                    ctx,
                    ctx.revenue,
                    prior + recent,
                    "revenue.monthly",
                ),
                *([note] if note else []),
            ],
            scale=scale,
        )


# --- cash --------------------------------------------------------------------------------------


class CashParams(RuleParams):
    lookback_months: int
    average_days: int
    outflow_months: int


@register
class CashDecline(Rule):
    code = "cash_decline"
    about = "Fall in the average daily bank balance, measured in months of typical outgoings."
    category = "cash"
    metric = "cash.balance"
    direction = "above"
    Params = CashParams

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        ctx = h.at(as_of).ctx
        then = months_back(as_of, p.lookback_months)
        start = then - timedelta(days=p.average_days - 1)
        if ctx.first_date is None or ctx.first_date > start:
            return Skip("insufficient_data", f"Needs history from {day(start)}.")
        months = ctx.window(p.outflow_months)
        if not months:
            return Skip("insufficient_data", "No complete month of data.")
        outflows = Decimal(sum(ctx.debits[m] for m in months)) / len(months)
        if outflows <= 0:
            return Skip("insufficient_data", "No outgoings to compare with.")

        def average(end: date) -> Decimal:
            days = [end - timedelta(days=i) for i in range(p.average_days)]
            return Decimal(sum(ctx.balance_at(d) for d in days)) / len(days)

        cur, prev = average(as_of), average(then)
        drop = prev - cur
        if drop <= 0:
            return Skip("clear", "The average cash balance has not fallen.")
        cur_r, prev_r, out_r = inr(int(cur)), inr(int(prev)), inr(int(outflows))
        cover = q(drop / outflows, "0.01")
        text = (
            f"The average cash balance over the last {p.average_days} days fell from "
            f"{fmt(prev_r, 'INR')} (to {day(then)}) to {fmt(cur_r, 'INR')}, a drop of "
            f"{fmt(inr(int(drop)), 'INR')} — {cover} months of typical outgoings "
            f"({fmt(out_r, 'INR')} a month)."
        )
        if cur < 0:
            text += " The account is now overdrawn on average."
        return Finding(
            measure=q(drop / outflows),
            measure_label="Fall in average balance ÷ average monthly outgoings",
            measure_unit="months",
            deteriorating=True,
            title="Cash balance declining",
            description=text,
            current=cur_r,
            previous=prev_r,
            current_period=days_period(as_of, p.average_days),
            previous_period=days_period(then, p.average_days),
            metric=MetricRef(
                code="cash.average_balance",
                name=f"Average daily cash balance ({p.average_days} days)",
                unit="INR",
                derived=True,
            ),
            evidence=[
                metric_evidence(
                    h, as_of, "cash.balance", "balance_now", f"Cash balance at {day(as_of)}."
                ),
                metric_evidence(
                    h, then, "cash.balance", "balance_then", f"Cash balance at {day(then)}."
                ),
                WarningEvidence(
                    id="outgoings",
                    text=f"Average monthly outgoings over {months_text(months)}.",
                    values={
                        "average_monthly_outgoings": out_r,
                        "overdraft_limit": inr(ctx.overdraft_limit),
                    },
                    period=Context.months_period(months, f"trailing_{len(months)}_months"),
                ),
            ],
        )


class LiquidityDeteriorationParams(RuleParams):
    lookback_months: int
    average_days: int
    revenue_months: int
    min_days_increase: Decimal
    min_overdue_share: Decimal


@register
class LiquidityDeterioration(Rule):
    """Cash draining into unpaid invoices: the bank balance falls while receivables rise.

    The liquidity ratio counts receivables as liquid, so it can hold steady (or even improve)
    while the cash a business can actually spend drains away. This rule measures that shift
    directly: the fall in cash plus the rise in receivables over the lookback, in months of
    revenue. It stays clear unless a meaningful share of receivables is overdue (invoices not yet
    due are not a liquidity problem), and it is reported as worsening only if collection time also
    lengthened, so receivables rising with healthy sales growth alone is not deterioration."""

    code = "liquidity_deterioration"
    about = "Cash falling while receivables rise: liquidity moving into unpaid invoices."
    category = "liquidity"
    metric = "receivables.outstanding"
    direction = "above"
    Params = LiquidityDeteriorationParams

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        then = months_back(as_of, p.lookback_months)
        ctx = h.at(as_of).ctx
        start = then - timedelta(days=p.average_days - 1)
        if ctx.first_date is None or ctx.first_date > start:
            return Skip("insufficient_data", f"Needs history from {day(start)}.")
        now_rec = h.at(as_of).metric(self.metric)
        if now_rec.availability == "not_applicable":
            return Skip("not_applicable", now_rec.notes[0])
        rec_now, rec_then = now_rec.value, h.at(then).value(self.metric)
        if rec_now is None or rec_then is None:
            return Skip("insufficient_data", "Receivables are not available at both dates.")
        revenue_ends = [months_back(as_of, i) for i in range(p.revenue_months)]
        revenues = [h.at(d).value("revenue.monthly") for d in revenue_ends]
        if any(r is None for r in revenues):
            return Skip("insufficient_data", "Monthly revenue is not available.")
        revenue = sum((r for r in revenues if r is not None), Decimal(0)) / len(revenues)
        if revenue <= 0:
            return Skip("insufficient_data", "No revenue to compare with.")

        def average(end: date) -> Decimal:
            """The 30-day average balance in whole rupees, so the figure reads the same in the
            text, in the evidence values and wherever the UI shows it."""
            days = [end - timedelta(days=i) for i in range(p.average_days)]
            paise = Decimal(sum(ctx.balance_at(d) for d in days)) / len(days)
            return inr(int(q(paise / 100, "1")) * 100)

        cash_now, cash_then = average(as_of), average(then)
        cash_fall, rec_rise = cash_then - cash_now, rec_now - rec_then
        if cash_fall <= 0:
            return Skip("clear", "The average cash balance has not fallen.")
        if rec_rise <= 0:
            return Skip("clear", "Receivables have not risen.")
        overdue = now_rec.components.get("overdue_share")
        if isinstance(overdue, Decimal) and overdue < p.min_overdue_share:
            return Skip(
                "clear",
                f"Receivables rose, but only {q(overdue * 100, '1')}% are overdue: invoices "
                "not yet due are not a liquidity problem.",
            )
        shift = cash_fall + rec_rise
        dso_now = h.at(as_of).value("receivables.days")
        dso_then = h.at(then).value("receivables.days")
        months = q(shift / revenue, "0.01")
        text = (
            f"Over {p.lookback_months} months the average cash balance fell from "
            f"{fmt(cash_then, 'INR')} to {fmt(cash_now, 'INR')} while receivables rose from "
            f"{fmt(rec_then, 'INR')} to {fmt(rec_now, 'INR')}: {fmt(shift, 'INR')} "
            f"({months} months of revenue) has moved out of the bank into unpaid invoices."
        )
        if dso_now is not None and dso_then is not None:
            text += f" Collection time went from {q(dso_then, '1')} to {q(dso_now, '1')} days."
        if isinstance(overdue, Decimal):
            text += f" {q(overdue * 100, '1')}% of receivables are overdue."
        ratio = h.at(as_of).value("liquidity.ratio")
        if ratio is not None:
            text += (
                f" The liquidity ratio ({q(ratio, '0.01')}×) counts receivables as liquid, so it "
                "does not show this."
            )
        return Finding(
            measure=q(shift / revenue),
            measure_label="(Fall in cash + rise in receivables) ÷ average monthly revenue",
            measure_unit="months",
            deteriorating=dso_now is None
            or dso_then is None
            or dso_now - dso_then >= p.min_days_increase,
            title="Liquidity deterioration",
            persistent_title="Cash tied up in growing receivables",
            description=text,
            current=rec_now,
            previous=rec_then,
            current_period=as_of_period(as_of),
            previous_period=as_of_period(then),
            evidence=[
                metric_evidence(
                    h,
                    as_of,
                    self.metric,
                    "receivables_now",
                    f"Receivables at {day(as_of)}, aged.",
                    ("overdue_share", "overdue_31_60_days", "overdue_61_90_days"),
                ),
                metric_evidence(
                    h, then, self.metric, "receivables_then", f"Receivables at {day(then)}."
                ),
                WarningEvidence(
                    id="cash_average",
                    text=f"Average daily cash balance over the {p.average_days} days to each date.",
                    values={"now": cash_now, "then": cash_then},
                    metric_codes=["cash.balance"],
                ),
                WarningEvidence(
                    id="revenue",
                    text=f"Average monthly revenue over {months_text(sorted(revenue_ends))}.",
                    values={"average_monthly_revenue": q(revenue, "0.01")},
                    metric_codes=["revenue.monthly"],
                ),
                WarningEvidence(
                    id="collection_days",
                    text="Receivable days (DSO) at each date.",
                    values={"now": dso_now, "then": dso_then},
                    metric_codes=["receivables.days"],
                ),
                metric_evidence(
                    h,
                    as_of,
                    "liquidity.ratio",
                    "liquidity_ratio",
                    "Liquidity ratio (receivables counted as liquid).",
                ),
            ],
        )


# --- receivables ---------------------------------------------------------------------------------


class ReceivablesParams(VolatilityScaled):
    lookback_months: int
    baseline_months: int
    min_previous: Decimal
    min_receivable_days: Decimal
    min_days_increase: Decimal


@register
class ReceivablesGrowth(Rule):
    code = "receivables_growth"
    about = "Unpaid customer invoices growing faster than sales."
    category = "receivables"
    metric = "receivables.outstanding"
    direction = "above"
    Params = ReceivablesParams

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        now = h.at(as_of).metric(self.metric)
        if now.availability == "not_applicable":
            return Skip("not_applicable", now.notes[0])
        prev, points = h.baseline(as_of, self.metric, p.lookback_months, p.baseline_months)
        cur = now.value
        if cur is None or prev is None or prev < p.min_previous:
            return Skip("insufficient_data", "No meaningful earlier receivables balance.")
        g = cur / prev - 1
        if g <= 0:
            return Skip("clear", "Receivables have not grown.")
        dso_now = h.at(as_of).value("receivables.days")
        if dso_now is not None and dso_now < p.min_receivable_days:
            return Skip("clear", f"Customers pay quickly ({q(dso_now, '1')} receivable days).")
        then = points[0][0]
        scale, note = volatility_scale(h, then, p)
        span = (as_of - then).days
        ctx = h.at(as_of).ctx

        def invoiced(start: date, end: date) -> int:
            return sum(i.total_minor for i in ctx.invoices if start < i.issued_on <= end)

        s_now, s_before = invoiced(then, as_of), invoiced(then - timedelta(days=span), then)
        sg = Decimal(s_now) / s_before - 1 if s_before > 0 else None
        # Collection time on the same footing as the receivables baseline.
        dso_then, _ = h.baseline(as_of, "receivables.days", p.lookback_months, p.baseline_months)
        against = (
            f"over the previous {span} days ({fmt(prev, 'INR')} → {fmt(cur, 'INR')})"
            if len(points) == 1
            else f"against their typical level ({fmt(prev, 'INR')}, the median of {len(points)} "
            f"month-ends to {day(then)}) to {fmt(cur, 'INR')}"
        )
        text = f"Receivables increased {signed_pct(g)} {against}" + (
            f", while invoiced sales changed {signed_pct(sg)}." if sg is not None else "."
        )
        if dso_now is not None and dso_then is not None:
            text += f" Average collection time: {q(dso_then, '1')} → {q(dso_now, '1')} days."
        overdue = now.components.get("overdue_share")
        if isinstance(overdue, Decimal):
            text += f" {q(overdue * 100, '1')}% of receivables are overdue."
        return Finding(
            measure=q(g),
            measure_label=f"Growth in receivables over {span} days",
            measure_unit="ratio",
            # Receivables outgrowing sales is the same thing as collection days rising.
            deteriorating=dso_now is None
            or dso_then is None
            or dso_now - dso_then >= p.min_days_increase,
            title="Receivables growing faster than sales",
            persistent_title="Receivables growing in line with sales",
            description=text,
            current=cur,
            previous=prev,
            current_period=as_of_period(as_of),
            previous_period=as_of_period(then)
            if len(points) == 1
            else Period(start=points[-1][0], end=then, label=f"median_of_{len(points)}_month_ends"),
            evidence=[
                metric_evidence(
                    h,
                    as_of,
                    self.metric,
                    "receivables_now",
                    f"Receivables at {day(as_of)}, aged.",
                    (
                        "overdue_share",
                        "overdue_31_60_days",
                        "overdue_61_90_days",
                        "overdue_over_90_days",
                    ),
                ),
                WarningEvidence(
                    id="receivables_then",
                    text="Receivables at the earlier month-end(s) compared with.",
                    values={d.isoformat(): v for d, v in points},
                    metric_codes=[self.metric],
                ),
                WarningEvidence(
                    id="sales",
                    text=f"Invoiced sales (incl. GST) in the {span} days to each date.",
                    values={"now": inr(s_now), "before": inr(s_before)},
                    metric_codes=["revenue.monthly"],
                ),
                WarningEvidence(
                    id="collection_days",
                    text="Receivable days (DSO) at each date.",
                    values={"now": dso_now, "then": dso_then},
                    metric_codes=["receivables.days"],
                ),
                *([note] if note else []),
            ],
            scale=scale,
        )


class BaselineParams(RuleParams):
    lookback_months: int
    baseline_months: int
    min_current: Decimal


@register
class ReceivableDaysIncrease(Rule):
    code = "receivable_days_increase"
    about = "Receivable days (DSO) rising above their own recent median."
    category = "receivables"
    metric = "receivables.days"
    direction = "above"
    Params = BaselineParams

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        now = h.at(as_of).metric(self.metric)
        if now.availability == "not_applicable":
            return Skip("not_applicable", now.notes[0])
        if now.value is None:
            return Skip("insufficient_data", now.notes[0] if now.notes else "Unavailable.")
        cur = now.value
        base, points = h.baseline(as_of, self.metric, p.lookback_months, p.baseline_months)
        if base is None:
            return Skip("insufficient_data", "Not enough earlier month-ends to compare with.")
        if cur < p.min_current:
            return Skip("clear", f"Receivable days ({q(cur, '0.1')}) are below the minimum.")
        rise = cur - base
        overdue = h.at(as_of).metric("receivables.outstanding").components.get("overdue_share")
        text = (
            f"Customers are taking longer to pay: receivable days are {q(cur, '0.1')}, up from a "
            f"typical {q(base, '0.1')} (median of {len(points)} month-ends to "
            f"{day(points[0][0])})."
        )
        if isinstance(overdue, Decimal):
            text += f" {q(overdue * 100, '1')}% of receivables are overdue."
        return Finding(
            measure=q(rise, "0.1"),
            measure_label="Rise in receivable days against the earlier median",
            measure_unit="days",
            deteriorating=True,
            title="Collection period lengthening",
            description=text,
            current=cur,
            previous=q(base, "0.1"),
            current_period=now.period,
            previous_period=Period(
                start=points[-1][0], end=points[0][0], label=f"median_of_{len(points)}_month_ends"
            ),
            evidence=[
                metric_evidence(
                    h,
                    as_of,
                    self.metric,
                    "current",
                    f"Receivable days at {day(as_of)}.",
                    ("outstanding", "issued_in_period"),
                ),
                WarningEvidence(
                    id="history",
                    text="Receivable days at the earlier month-ends used as the baseline.",
                    values={d.isoformat(): v for d, v in points},
                    metric_codes=[self.metric],
                ),
            ],
        )


class CollectionsParams(RuleParams):
    window_days: int
    lookback_months: int
    min_current: Decimal


def days_late(ctx: Context, start: date, end: date) -> tuple[Decimal | None, list[Any]]:
    """Amount-weighted average days past due of customer payments received in [start, end]."""
    docs: dict[Any, Document] = {d.id: d for d in ctx.invoices}
    paid = [x for x in ctx.invoice_payments if start <= x.paid_on <= end and x.document_id in docs]
    total = sum(x.amount_minor for x in paid)
    if not total:
        return None, paid
    weighted = sum(
        max(0, (x.paid_on - docs[x.document_id].due_on).days) * x.amount_minor for x in paid
    )
    return Decimal(weighted) / total, paid


@register
class DelayedCollections(Rule):
    code = "delayed_collections"
    about = "Customers paying further past the due date than before."
    category = "receivables"
    metric = "receivables.outstanding"
    direction = "above"
    Params = CollectionsParams

    def metric_ref(self) -> MetricRef:
        return MetricRef(
            code="collections.days_late",
            name="Average days late on customer payments",
            unit="days",
            derived=True,
        )

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        ctx = h.at(as_of).ctx
        if not ctx.invoices:
            return Skip("not_applicable", "No sales invoices: sales are settled immediately.")
        then = months_back(as_of, p.lookback_months)
        w = p.window_days
        cur, paid = days_late(ctx, as_of - timedelta(days=w - 1), as_of)
        prev, _ = days_late(ctx, then - timedelta(days=w - 1), then)
        if (
            cur is None
            or prev is None
            or (ctx.first_date and ctx.first_date > then - timedelta(days=w - 1))
        ):
            return Skip("insufficient_data", "Needs customer payments in both periods.")
        if cur < p.min_current:
            return Skip("clear", f"Customers pay {q(cur, '0.1')} days late on average.")
        overdue = h.at(as_of).metric("receivables.outstanding").components
        text = (
            f"Customers paid on average {q(cur, '0.1')} days after the due date in the last {w} "
            f"days, against {q(prev, '0.1')} days in the {w} days to {day(then)}."
        )
        share = overdue.get("overdue_share")
        if isinstance(share, Decimal):
            text += f" {q(share * 100, '1')}% of receivables are now overdue."
        return Finding(
            measure=q(cur - prev, "0.1"),
            measure_label="Increase in average days late",
            measure_unit="days",
            deteriorating=True,
            title="Collections slowing down",
            description=text,
            current=q(cur, "0.1"),
            previous=q(prev, "0.1"),
            current_period=days_period(as_of, w),
            previous_period=days_period(then, w),
            evidence=[
                WarningEvidence(
                    id="payments",
                    text=f"Customer payments received in the last {w} days.",
                    values={"count": len(paid), "average_days_late": q(cur, "0.1")},
                    period=days_period(as_of, w),
                    sources=[source("invoice_payments", paid, "Payments in the window")],
                ),
                metric_evidence(
                    h,
                    as_of,
                    "receivables.outstanding",
                    "aging",
                    "Receivables by days past due.",
                    (
                        "overdue_share",
                        "overdue_1_30_days",
                        "overdue_31_60_days",
                        "overdue_61_90_days",
                        "overdue_over_90_days",
                    ),
                ),
            ],
        )


# --- debt ----------------------------------------------------------------------------------------


class BorrowingParams(RuleParams):
    lookback_months: int


@register
class NewBorrowing(Rule):
    code = "new_borrowing"
    about = "Several new loans in six months while total debt rises (loan stacking)."
    category = "debt"
    metric = "debt.new_loans_6m"
    direction = "above"
    Params = BorrowingParams

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        count = h.at(as_of).value(self.metric)
        if count is None:
            return Skip("insufficient_data", "Unavailable.")
        if count == 0:
            return Skip("clear", "No new loans in the last 6 months.")
        then = months_back(as_of, p.lookback_months)
        before = h.at(then)
        debt_now = h.at(as_of).value("debt.outstanding") or ZERO
        debt_then = before.value("debt.outstanding") or ZERO
        lev_now, lev_then = h.at(as_of).value("debt.leverage"), before.value("debt.leverage")
        text = (
            f"{count} loan(s) were taken in the last 6 months. Debt outstanding went from "
            f"{fmt(debt_then, 'INR')} on {day(then)} to {fmt(debt_now, 'INR')}."
        )
        if lev_now is not None and lev_then is not None:
            text += f" Debt ÷ annual revenue: {fmt(lev_then, 'ratio')} → {fmt(lev_now, 'ratio')}."
        return Finding(
            measure=count,
            measure_label="Loans disbursed in the last 6 months",
            measure_unit="count",
            deteriorating=debt_now > debt_then,
            title="Debt increasing: several new loans",
            persistent_title="Several new loans (debt not rising)",
            description=text,
            current=debt_now,
            previous=debt_then,
            current_period=as_of_period(as_of),
            previous_period=as_of_period(then),
            metric=metric_ref("debt.outstanding"),
            evidence=[
                metric_evidence(
                    h, as_of, self.metric, "new_loans", "Loans disbursed in the last 183 days."
                ),
                metric_evidence(
                    h, as_of, "debt.outstanding", "debt_now", f"Debt outstanding at {day(as_of)}."
                ),
                metric_evidence(
                    h, then, "debt.outstanding", "debt_then", f"Debt outstanding at {day(then)}."
                ),
            ],
        )


class SlippageParams(RuleParams):
    window_days: int


def repayment_issues(instalments: list[Installment], end: date, days: int) -> list[Installment]:
    """Instalments due in the window ending ``end`` that were paid late, bounced, or are still
    unpaid, judged with what was known on ``end``."""
    start = end - timedelta(days=days - 1)
    out = []
    for i in instalments:
        if not start <= i.due_on <= end:
            continue
        paid = i.paid_on is not None and i.paid_on <= end
        if (paid and (i.paid_on > i.due_on or i.bounces > 0)) or (  # type: ignore[operator]
            not paid and i.due_on < end
        ):
            out.append(i)
    return out


@register
class RepaymentSlippage(Rule):
    code = "repayment_slippage"
    about = "Loan instalments bounced, paid late or missed, more than before."
    category = "debt"
    metric = "payments.consistency"
    direction = "above"
    Params = SlippageParams

    def metric_ref(self) -> MetricRef:
        return MetricRef(
            code="debt.repayment_issues",
            name="Loan instalments paid late, bounced or missed",
            unit="count",
            derived=True,
        )

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        ctx = h.at(as_of).ctx
        if not ctx.installments:
            return Skip("not_applicable", "No loans.")
        w = p.window_days
        now = repayment_issues(ctx.installments, as_of, w)
        if not now:
            return Skip("clear", f"Every instalment due in the last {w} days was paid on time.")
        prev_end = as_of - timedelta(days=w)
        before = repayment_issues(h.at(prev_end).ctx.installments, prev_end, w)
        bounced = sum(1 for i in now if i.bounces)
        unpaid = sum(1 for i in now if i.paid_on is None or i.paid_on > as_of)
        text = (
            f"{len(now)} loan instalment(s) due in the last {w} days were not paid cleanly "
            f"({bounced} bounced, {unpaid} unpaid, the rest late), against {len(before)} in the "
            f"{w} days before."
        )
        consistency = h.at(as_of).value("payments.consistency")
        if consistency is not None:
            text += f" Obligations paid on time over 12 months: {fmt(consistency, 'ratio')}."
        return Finding(
            measure=Decimal(len(now)),
            measure_label=f"Instalments with problems in the last {w} days",
            measure_unit="count",
            deteriorating=len(now) > len(before),
            title="Loan repayments slipping",
            persistent_title="Recurring loan repayment problems",
            description=text,
            current=Decimal(len(now)),
            previous=Decimal(len(before)),
            current_period=days_period(as_of, w),
            previous_period=days_period(prev_end, w),
            evidence=[
                WarningEvidence(
                    id="instalments",
                    text="Instalments due in the window that bounced, were paid late or are "
                    "unpaid.",
                    values={"count": len(now), "bounced": bounced, "unpaid": unpaid},
                    period=days_period(as_of, w),
                    sources=[source("loan_installments", now, "Problem instalments")],
                ),
                metric_evidence(
                    h,
                    as_of,
                    "payments.consistency",
                    "consistency",
                    "Share of obligations paid on time over 12 months.",
                ),
            ],
        )


# --- concentration -------------------------------------------------------------------------------


class CustomerLossParams(VolatilityScaled):
    recent_months: int
    baseline_months: int
    min_share: Decimal


@register
class MajorCustomerLoss(Rule):
    code = "major_customer_loss"
    about = "Customers that were a large share of revenue buying much less."
    category = "concentration"
    metric = "customers.concentration"
    direction = "above"
    Params = CustomerLossParams

    def metric_ref(self) -> MetricRef:
        return MetricRef(
            code="customers.major_customer_revenue",
            name="Monthly revenue from major customers",
            unit="INR",
            derived=True,
        )

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        ctx = h.at(as_of).ctx
        if not ctx.invoices:
            return Skip("not_applicable", "No sales invoices to attribute revenue to customers.")
        months = ctx.window(p.recent_months + p.baseline_months)
        if len(months) < p.recent_months + p.baseline_months:
            need = p.recent_months + p.baseline_months
            return Skip("insufficient_data", f"Needs {need} complete months.")
        base_m, recent_m = months[: p.baseline_months], months[p.baseline_months :]
        by_party: dict[Any, list[int]] = defaultdict(lambda: [0, 0])
        docs: dict[Any, list[Document]] = defaultdict(list)
        b0, r0 = base_m[0], recent_m[0]
        end = month_end(months[-1])
        for inv in ctx.invoices:
            if b0 <= inv.issued_on < r0:
                by_party[inv.party_id][0] += inv.taxable_minor
            elif r0 <= inv.issued_on <= end:
                by_party[inv.party_id][1] += inv.taxable_minor
                docs[inv.party_id].append(inv)
        base_total = Decimal(sum(ctx.revenue(m) for m in base_m)) / len(base_m)
        if base_total <= 0:
            return Skip("insufficient_data", "No revenue in the baseline months.")
        recent_total = Decimal(sum(ctx.revenue(m) for m in recent_m)) / len(recent_m)
        lost, before, after, lines, values = ZERO, ZERO, ZERO, [], {}
        for party_id, (b, r) in sorted(by_party.items(), key=lambda kv: -kv[1][0]):
            b_avg, r_avg = Decimal(b) / len(base_m), Decimal(r) / len(recent_m)
            if b_avg / base_total < p.min_share:
                continue
            before, after = before + b_avg, after + r_avg
            name = ctx.parties[party_id].name if party_id in ctx.parties else "Unknown customer"
            # Only the fall beyond the rest of the business's own fall is customer-specific; a
            # business-wide decline is the revenue_decline rule's job.
            rest_base, rest_recent = base_total - b_avg, recent_total - r_avg
            rest_growth = rest_recent / rest_base - 1 if rest_base > 0 else ZERO
            expected = b_avg * (1 + min(ZERO, rest_growth))
            values[name] = f"{inr(int(b_avg))} → {inr(int(r_avg))}"
            if r_avg < expected:
                lost += expected - r_avg
                lines.append(
                    f"{name}: {fmt(inr(int(b_avg)), 'INR')} → {fmt(inr(int(r_avg)), 'INR')} a "
                    f"month ({signed_pct(r_avg / b_avg - 1)}; the rest of sales "
                    f"{signed_pct(rest_growth)})"
                )
        if not values:
            return Skip("clear", "No customer accounts for the minimum share of revenue.")
        if lost <= 0:
            return Skip("clear", "No major customer has fallen away more than the rest of sales.")
        share = lost / base_total
        scale, note = volatility_scale(h, month_end(base_m[-1]), p)
        text = (
            f"Sales to major customers (each ≥{q(p.min_share * 100, '1')}% of revenue in "
            f"{months_text(base_m)}) have fallen in {months_text(recent_m)}: "
            + "; ".join(lines)
            + f". The customer-specific loss equals {q(share * 100, '1')}% of monthly revenue."
        )
        return Finding(
            measure=q(share),
            measure_label="Customer-specific lost sales ÷ baseline monthly revenue",
            measure_unit="ratio",
            deteriorating=True,
            title="Major customer buying less",
            description=text,
            current=inr(int(after)),
            previous=inr(int(before)),
            current_period=Context.months_period(recent_m, f"trailing_{len(recent_m)}_months"),
            previous_period=Context.months_period(base_m, f"previous_{len(base_m)}_months"),
            evidence=[
                WarningEvidence(
                    id="customers",
                    text="Average monthly sales (excluding GST) per major customer, baseline → "
                    "recent.",
                    values=values,
                    metric_codes=["customers.concentration"],
                    sources=[
                        source(
                            "invoices",
                            [d for ds in docs.values() for d in ds],
                            "Recent invoices to these customers",
                        )
                    ],
                ),
                *([note] if note else []),
            ],
            scale=scale,
        )


# --- transactions ------------------------------------------------------------------------------


class UnusualParams(RuleParams):
    recent_days: int
    reference_days: int
    outlier_multiple: Decimal
    min_amount: Decimal
    outflow_months: int
    exclude_categories: list[str]
    watch_categories: list[str]
    watch_severity: Severity


@dataclass
class Unusual:
    txn: Txn
    reason: str


def scan_unusual(ctx: Context, end: date, p: Any) -> list[Unusual]:
    recent_start = end - timedelta(days=p.recent_days - 1)
    ref_start = recent_start - timedelta(days=p.reference_days)
    largest: dict[str, int] = defaultdict(int)
    out: list[Unusual] = []
    min_minor = int(p.min_amount * 100)
    for t in ctx.txns:
        if t.amount_minor >= 0 or t.posted_on < ref_start or t.posted_on > end:
            continue
        cat = t.category or "uncategorised"
        amount = -t.amount_minor
        if t.posted_on < recent_start:
            largest[cat] = max(largest[cat], amount)
            continue
        if cat in p.exclude_categories:
            continue
        if cat in p.watch_categories:
            out.append(Unusual(t, f"watch-listed category {cat}"))
        elif amount >= min_minor and cat not in largest:
            out.append(Unusual(t, f"first {cat} payment in {p.reference_days} days"))
        elif amount >= min_minor and amount > p.outlier_multiple * largest[cat]:
            out.append(
                Unusual(
                    t,
                    f"{q(Decimal(amount) / largest[cat], '0.1')}× the largest {cat} "
                    f"payment in the previous {p.reference_days} days",
                )
            )
    return out


@register
class UnusualTransactions(Rule):
    code = "unusual_transactions"
    about = "Unusually large or new kinds of outgoing payments, and watch-listed categories."
    category = "transactions"
    metric = "transactions.consistency"
    direction = "above"
    Params = UnusualParams

    def metric_ref(self) -> MetricRef:
        return MetricRef(
            code="transactions.unusual_outflows",
            name="Unusual outgoing payments",
            unit="INR",
            derived=True,
        )

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        ctx = h.at(as_of).ctx
        recent_start = as_of - timedelta(days=p.recent_days - 1)
        prev_end = recent_start - timedelta(days=1)
        earliest = prev_end - timedelta(days=p.recent_days + p.reference_days)
        if ctx.first_date is None or ctx.first_date > earliest:
            return Skip("insufficient_data", f"Needs history from {day(earliest)}.")
        months = ctx.window(p.outflow_months)
        outflows = Decimal(sum(ctx.debits[m] for m in months)) / max(1, len(months))
        if outflows <= 0:
            return Skip("insufficient_data", "No outgoings to compare with.")
        found = scan_unusual(ctx, as_of, p)
        if not found:
            return Skip("clear", "No unusual outgoing payments in the recent window.")
        before = scan_unusual(ctx, prev_end, p)
        amount = sum(-u.txn.amount_minor for u in found)
        amount_before = sum(-u.txn.amount_minor for u in before)
        watch = [u for u in found if u.reason.startswith("watch-listed")]
        top = sorted(found, key=lambda u: u.txn.amount_minor)[:5]
        text = (
            f"{len(found)} unusual outgoing payment(s) in the last {p.recent_days} days, "
            f"{fmt(inr(amount), 'INR')} in total ({q(Decimal(amount) / outflows * 100, '1')}% of "
            f"a typical month's outgoings), against {fmt(inr(amount_before), 'INR')} in the "
            f"{p.recent_days} days before. Largest: "
            + "; ".join(
                f"{fmt(inr(-u.txn.amount_minor), 'INR')} on {day(u.txn.posted_on)} ({u.reason})"
                for u in top[:3]
            )
            + "."
        )
        return Finding(
            measure=q(Decimal(amount) / outflows),
            measure_label="Unusual outgoings ÷ average monthly outgoings",
            measure_unit="ratio",
            deteriorating=amount > amount_before,
            title="Unusual transaction activity",
            persistent_title="Recurring unusual transactions",
            description=text,
            current=inr(amount),
            previous=inr(amount_before),
            current_period=days_period(as_of, p.recent_days),
            previous_period=days_period(prev_end, p.recent_days),
            severity_floor=p.watch_severity if watch else None,
            evidence=[
                WarningEvidence(
                    id=f"txn_{i + 1}",
                    text=f"{fmt(inr(-u.txn.amount_minor), 'INR')} on {day(u.txn.posted_on)}: "
                    f"{u.reason}.",
                    values={"amount": inr(-u.txn.amount_minor), "category": u.txn.category},
                    sources=[source("transactions", [u.txn], "The transaction")],
                )
                for i, u in enumerate(top)
            ],
        )


# --- volatility -----------------------------------------------------------------------------


class VolatilityParams(RuleParams):
    months: int
    min_change_ratio: Decimal


def cv(values: list[Decimal]) -> Decimal | None:
    mean = Decimal(sum(values)) / len(values)
    return Decimal(statistics.pstdev(values)) / mean if mean > 0 else None


def cash_flow_swing(ctx: Context, months: list[date]) -> Decimal | None:
    receipts = Decimal(sum(ctx.operating_inflows[m] for m in months)) / len(months)
    if receipts <= 0:
        return None
    flows = [Decimal(ctx.net_cash_flow_before_borrowing(m)) for m in months]
    return Decimal(statistics.pstdev(flows)) / receipts


class VolatilityRule(Rule):
    """Volatility over the last ``months`` complete months against the ``months`` before, on
    windows of equal length. Deteriorating = at least ``min_change_ratio`` × the earlier value."""

    Params = VolatilityParams
    direction = "above"
    series_code: ClassVar[str]
    title: ClassVar[str]
    persistent_title: ClassVar[str]
    measure_name: ClassVar[str]

    def series(self, ctx: Context) -> Callable[[date], int]:
        raise NotImplementedError

    def measure(self, ctx: Context, months: list[date]) -> Decimal | None:
        raise NotImplementedError

    def evaluate(self, h: History, as_of: date, p: Any) -> Finding | Skip:
        ctx = h.at(as_of).ctx
        months = ctx.window(p.months)
        if len(months) < p.months:
            return Skip("insufficient_data", f"Needs {p.months} complete months.")
        cur = self.measure(ctx, months)
        if cur is None:
            return Skip("insufficient_data", "Nothing to measure volatility against.")
        all_months = ctx.window(2 * p.months)
        prior = all_months[: -p.months] if len(all_months) == 2 * p.months else []
        prev = self.measure(ctx, prior) if prior else None
        deteriorating = prev is not None and cur >= prev * p.min_change_ratio
        text = f"{self.measure_name} was {fmt(q(cur), 'ratio')} in {months_text(months)}" + (
            f", against {fmt(q(prev), 'ratio')} in the {p.months} months before."
            if prev is not None
            else f"; there is no earlier {p.months}-month period to compare with."
        )
        if not deteriorating:
            text += " It is not rising materially."
        return Finding(
            measure=q(cur),
            measure_label=self.measure_name,
            measure_unit="ratio",
            deteriorating=deteriorating,
            title=self.title,
            persistent_title=self.persistent_title,
            description=text,
            current=q(cur),
            previous=q(prev) if prev is not None else None,
            current_period=Context.months_period(months, f"trailing_{p.months}_months"),
            previous_period=(
                Context.months_period(prior, f"previous_{p.months}_months") if prior else None
            ),
            evidence=[
                series_evidence(
                    "monthly_series",
                    f"The monthly figures behind the measure "
                    f"({CATALOGUE[self.series_code].name.lower()}).",
                    ctx,
                    self.series(ctx),
                    all_months,
                    self.series_code,
                ),
            ],
        )


@register
class RevenueVolatility(VolatilityRule):
    code = "revenue_volatility"
    about = "Month-to-month variation in revenue, against the previous period of equal length."
    category = "volatility"
    metric = "revenue.volatility"
    series_code = "revenue.monthly"
    title = "Revenue becoming more volatile"
    persistent_title = "Volatile revenue"
    measure_name = "Revenue volatility (coefficient of variation of monthly revenue)"

    def metric_ref(self) -> MetricRef:
        return MetricRef(
            code="revenue.volatility_window",
            name="Revenue volatility over the window",
            unit="ratio",
            derived=True,
        )

    def series(self, ctx: Context) -> Callable[[date], int]:
        return ctx.revenue

    def measure(self, ctx: Context, months: list[date]) -> Decimal | None:
        return cv([Decimal(ctx.revenue(m)) for m in months])


@register
class CashFlowVolatility(VolatilityRule):
    code = "cash_flow_volatility"
    about = (
        "Month-to-month swings in net cash flow relative to receipts, against the previous period."
    )
    category = "volatility"
    metric = "cashflow.net_monthly"
    series_code = "cashflow.net_monthly"
    title = "Cash flow becoming more volatile"
    persistent_title = "Volatile cash flow"
    measure_name = "Cash-flow volatility (std of monthly net cash flow ÷ average receipts)"

    def metric_ref(self) -> MetricRef:
        return MetricRef(
            code="cashflow.volatility",
            name="Cash-flow volatility (std of monthly net flow ÷ average receipts)",
            unit="ratio",
            derived=True,
        )

    def series(self, ctx: Context) -> Callable[[date], int]:
        return ctx.net_cash_flow_before_borrowing

    def measure(self, ctx: Context, months: list[date]) -> Decimal | None:
        return cash_flow_swing(ctx, months)
