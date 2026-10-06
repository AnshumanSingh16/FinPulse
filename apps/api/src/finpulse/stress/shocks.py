"""Shock types: each one changes the inputs of the cash-flow projection.

To add a scenario type: subclass ``Shock`` with a unique ``code`` and a ``Params`` model whose
``type`` is that code as a literal, implement ``apply`` (and ``resolve`` if a parameter has an
entity-dependent default),
and decorate it with ``@register``. The API, the catalogue endpoint and request validation pick
it up automatically.

Shocks only move levers; ``projection.simulate`` does all of the arithmetic, so every scenario is
calculated the same way. A shock may also record ``Evidence`` explaining what it changed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from finpulse.analytics.registry import inr
from finpulse.core.dates import month_end
from finpulse.core.errors import UnprocessableError
from finpulse.core.finance import amortize
from finpulse.core.money import format_inr, round_minor, rupees
from finpulse.stress.baseline import Baseline, PartyFlow
from finpulse.stress.schemas import Evidence

ONE = Decimal(1)
DAYS_PER_MONTH = Decimal(365) / 12


class ScenarioNotApplicable(UnprocessableError):
    code = "scenario_not_applicable"
    title = "Scenario not applicable"


@dataclass
class Levers:
    """Everything a shock may change, per projected month (index 0 = first projected month)."""

    horizon: int
    baseline: Baseline
    revenue_factor: list[Decimal] = field(init=False)
    receipts_factor: list[Decimal] = field(init=False)
    receipts_delta: list[int] = field(init=False)
    purchases_factor: list[Decimal] = field(init=False)  # purchases and supplier payments
    purchases_delta: list[int] = field(init=False)  # accrual, ex-GST
    supplier_payments_delta: list[int] = field(init=False)
    opex_factor: list[Decimal] = field(init=False)
    debt_service: list[int] = field(init=False)
    principal_repaid: list[int] = field(init=False)
    disbursements: list[int] = field(init=False)
    overdraft_rate: Decimal = field(init=False)
    receivables_factor: Decimal = ONE
    receivables_delta: int = 0
    new_debt_outstanding: int = 0
    new_loans: int = 0
    principal_due_12m_delta: int = 0
    evidence: list[Evidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        h = self.horizon
        self.revenue_factor = [ONE] * h
        self.receipts_factor = [ONE] * h
        self.receipts_delta = [0] * h
        self.purchases_factor = [ONE] * h
        self.purchases_delta = [0] * h
        self.supplier_payments_delta = [0] * h
        self.opex_factor = [ONE] * h
        self.debt_service = list(self.baseline.scheduled_debt)
        self.principal_repaid = list(self.baseline.scheduled_principal)
        self.disbursements = [0] * h
        self.overdraft_rate = self.baseline.overdraft_rate


class ShockParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str  # each shock narrows this to its own literal (the request discriminator)

    start_month: int = Field(
        1, ge=1, le=24, description="First projected month affected (1 = next)"
    )


class TimedParams(ShockParams):
    duration_months: int | None = Field(
        None, ge=1, le=24, description="How long it lasts; default: to the end of the horizon"
    )


class Shock:
    code: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    Params: ClassVar[type[ShockParams]]

    def resolve(self, params: Any, baseline: Baseline) -> Any:
        """Fill entity-dependent defaults; raise ScenarioNotApplicable if it cannot apply."""
        return params

    def apply(self, params: Any, levers: Levers) -> None:
        raise NotImplementedError

    def describe(self, params: Any) -> str:
        return self.name


SHOCKS: dict[str, Shock] = {}


def register(cls: type[Shock]) -> type[Shock]:
    if cls.code in SHOCKS:
        raise ValueError(f"shock type {cls.code!r} registered twice")
    SHOCKS[cls.code] = cls()
    return cls


def active_months(params: ShockParams, horizon: int) -> range:
    if params.start_month > horizon:
        raise ScenarioNotApplicable(
            f"start_month {params.start_month} is beyond the {horizon}-month horizon."
        )
    duration = getattr(params, "duration_months", None) or horizon
    return range(params.start_month - 1, min(horizon, params.start_month - 1 + duration))


def rs(minor: int) -> str:
    """Whole rupees from minor units: 123456700 → ₹12,34,567."""
    return format_inr(minor)[:-3]


def pct(value: Decimal) -> str:
    return f"{(value * 100).normalize():f}%"


def _largest(flows: list[PartyFlow], what: str) -> PartyFlow:
    candidates = [f for f in flows if f.monthly_cash > 0 or f.monthly_documents > 0]
    if not candidates:
        raise ScenarioNotApplicable(f"The entity has no {what} in the baseline months.")
    return candidates[0]


def _find(flows: list[PartyFlow], party_id: uuid.UUID, what: str) -> PartyFlow:
    for f in flows:
        if f.party_id == party_id:
            return f
    raise ScenarioNotApplicable(f"No {what} with id {party_id} in the baseline months.")


# --- 1–3: revenue decline ---------------------------------------------------------------------


@register
class RevenueDecline(Shock):
    code = "revenue_decline"
    name = "Revenue decline"
    description = (
        "Sales and the cash they bring in fall by a percentage. By default purchases fall in "
        "proportion (stock is bought to sell); other operating costs, staff and rent do not."
    )

    class Params(TimedParams):
        type: Literal["revenue_decline"]
        decline_pct: Decimal = Field(gt=0, lt=1, description="0.2 = revenue falls by 20%")
        costs_follow_revenue: bool = Field(
            True, description="Purchases fall with sales (variable costs)"
        )

    def apply(self, params: Any, levers: Levers) -> None:
        keep = ONE - params.decline_pct
        months = active_months(params, levers.horizon)
        for k in months:
            levers.revenue_factor[k] *= keep
            levers.receipts_factor[k] *= keep
            if params.costs_follow_revenue:
                levers.purchases_factor[k] *= keep
        if levers.horizon - 1 in months:
            levers.receivables_factor *= keep
        b = levers.baseline
        levers.evidence.append(
            Evidence(
                id=f"shock.{self.code}",
                kind="shock",
                text=(
                    f"Revenue falls {pct(params.decline_pct)} for {len(months)} month(s): about "
                    f"{rs(round_minor(b.revenue * params.decline_pct))} less sales and "
                    f"{rs(round_minor(b.operating_receipts * params.decline_pct))} less "
                    "cash received per month"
                    + (
                        ", with purchases falling in proportion."
                        if params.costs_follow_revenue
                        else "; costs unchanged."
                    )
                ),
                values={
                    "decline_pct": params.decline_pct,
                    "months_affected": len(months),
                    "monthly_revenue_lost": inr(round_minor(b.revenue * params.decline_pct)),
                    "monthly_receipts_lost": inr(
                        round_minor(b.operating_receipts * params.decline_pct)
                    ),
                },
                metric_codes=["revenue.monthly"],
                sources=[b.sources["receipts"]],
            )
        )

    def describe(self, params: Any) -> str:
        return f"Revenue decreases by {pct(params.decline_pct)}"


# --- 4–6: a major customer stops paying ---------------------------------------------------------


@register
class CustomerPaymentStop(Shock):
    code = "customer_payment_stop"
    name = "Major customer stops paying"
    description = (
        "A customer (by default the one paying the most) pays nothing for a number of days. "
        "Sales to them continue on credit, so receivables grow. If recovered, the withheld "
        "amount arrives the month after the stop ends."
    )

    class Params(ShockParams):
        type: Literal["customer_payment_stop"]
        days: int = Field(ge=1, le=365)
        customer_id: uuid.UUID | None = Field(None, description="Default: the largest payer")
        recovered: bool = Field(True, description="Withheld payments are eventually received")

    def resolve(self, params: Any, baseline: Baseline) -> Any:
        if params.customer_id is None:
            customer = _largest(baseline.customers, "invoiced customers")
            return params.model_copy(update={"customer_id": customer.party_id})
        _find(baseline.customers, params.customer_id, "customer")
        return params

    def apply(self, params: Any, levers: Levers) -> None:
        b = levers.baseline
        customer = _find(b.customers, params.customer_id, "customer")
        if params.start_month > levers.horizon:
            raise ScenarioNotApplicable("start_month is beyond the horizon.")
        daily = Decimal(customer.monthly_cash) / DAYS_PER_MONTH
        stop_start = b.projection_months[params.start_month - 1]
        stop_end = stop_start + timedelta(days=params.days - 1)
        withheld_total = 0
        for k, m in enumerate(b.projection_months):
            overlap = (min(month_end(m), stop_end) - max(m, stop_start)).days + 1
            if overlap > 0:
                withheld = round_minor(daily * overlap)
                levers.receipts_delta[k] -= withheld
                withheld_total += withheld
        released_in = None
        resume = stop_end + timedelta(days=1)
        if params.recovered:
            for k, m in enumerate(b.projection_months):
                if m <= resume <= month_end(m):
                    # Paid in the month after the stop: the month containing the first day after it.
                    k_release = k + 1 if resume.day > 1 else k
                    if k_release < levers.horizon:
                        levers.receipts_delta[k_release] += withheld_total
                        released_in = b.projection_months[k_release]
                    break
        if released_in is None:
            levers.receivables_delta += withheld_total
        share = pct(customer.share.quantize(Decimal("0.001")))
        levers.evidence.append(
            Evidence(
                id=f"shock.{self.code}",
                kind="shock",
                text=(
                    f"{customer.name} ({share} of operating "
                    f"receipts, about {rs(customer.monthly_cash)} a month) pays nothing "
                    f"for {params.days} days from {stop_start}: "
                    f"{rs(withheld_total)} withheld"
                    + (
                        f", received in {released_in:%b %Y}."
                        if released_in
                        else ", still owed at the end of the horizon."
                    )
                ),
                values={
                    "customer": customer.name,
                    "customer_share_of_receipts": customer.share.quantize(Decimal("0.0001")),
                    "customer_monthly_receipts": inr(customer.monthly_cash),
                    "days": params.days,
                    "withheld": inr(withheld_total),
                    "recovered_in": released_in.isoformat() if released_in else None,
                },
                metric_codes=["customers.concentration", "receivables.outstanding"],
                sources=[b.sources["receipts"]],
            )
        )

    def describe(self, params: Any) -> str:
        return f"Major customer stops paying for {params.days} days"


# --- 7: operating expenses rise -------------------------------------------------------------


@register
class OperatingExpenseIncrease(Shock):
    code = "operating_expense_increase"
    name = "Operating expenses increase"
    description = (
        "Operating costs other than supplier purchases — staff, rent, utilities, freight, "
        "services — rise by a percentage. (Use supplier_cost_increase for purchases.)"
    )

    class Params(TimedParams):
        type: Literal["operating_expense_increase"]
        increase_pct: Decimal = Field(gt=0, le=5, description="0.15 = costs rise by 15%")

    def apply(self, params: Any, levers: Levers) -> None:
        months = active_months(params, levers.horizon)
        for k in months:
            levers.opex_factor[k] *= ONE + params.increase_pct
        b = levers.baseline
        extra = round_minor(b.opex * params.increase_pct)
        levers.evidence.append(
            Evidence(
                id=f"shock.{self.code}",
                kind="shock",
                text=(
                    f"Operating expenses (baseline {rs(b.opex)} a month) rise "
                    f"{pct(params.increase_pct)}: {rs(extra)} more each month for "
                    f"{len(months)} month(s)."
                ),
                values={
                    "increase_pct": params.increase_pct,
                    "baseline_monthly_opex": inr(b.opex),
                    "extra_per_month": inr(extra),
                    "months_affected": len(months),
                },
                metric_codes=["expenses.monthly"],
                sources=[b.sources["opex"]],
            )
        )

    def describe(self, params: Any) -> str:
        return f"Operating expenses increase by {pct(params.increase_pct)}"


# --- 8: new debt -------------------------------------------------------------------------------


@register
class NewDebt(Shock):
    code = "new_debt"
    name = "New debt is added"
    description = (
        "A new term loan is disbursed in start_month and repaid by equal monthly instalments from "
        "the month after. The money is assumed to be held as cash (no extra revenue), which shows "
        "the pure cost of servicing it. Default: two months of operating receipts at 18% over "
        "24 months."
    )

    class Params(ShockParams):
        type: Literal["new_debt"]
        principal: Decimal | None = Field(
            None, gt=0, description="Rupees; default: 2 × monthly receipts"
        )
        annual_rate: Decimal = Field(Decimal("0.18"), gt=0, le=1)
        tenor_months: int = Field(24, ge=1, le=360)

    def resolve(self, params: Any, baseline: Baseline) -> Any:
        if params.principal is None:
            default = max(
                rupees(50_000), round_minor(baseline.operating_receipts * 2, step_major=10_000)
            )
            return params.model_copy(update={"principal": inr(default)})
        return params

    def apply(self, params: Any, levers: Levers) -> None:
        if params.start_month > levers.horizon:
            raise ScenarioNotApplicable("start_month is beyond the horizon.")
        principal = rupees(params.principal)
        k0 = params.start_month - 1
        levers.disbursements[k0] += principal
        schedule = amortize(principal, float(params.annual_rate), params.tenor_months)
        repaid = 0
        for s in schedule:
            k = k0 + s.seq
            if k < levers.horizon:
                levers.debt_service[k] += s.amount_minor
                levers.principal_repaid[k] += s.principal_minor
                repaid += s.principal_minor
            elif k < levers.horizon + 12:
                levers.principal_due_12m_delta += s.principal_minor
        levers.new_debt_outstanding += principal - repaid
        levers.new_loans += 1
        month = levers.baseline.projection_months[k0]
        levers.evidence.append(
            Evidence(
                id=f"shock.{self.code}",
                kind="shock",
                text=(
                    f"A new loan of {rs(principal)} at {pct(params.annual_rate)} over "
                    f"{params.tenor_months} months is disbursed in {month:%b %Y}; "
                    f"the EMI is {rs(schedule[0].amount_minor)} a month."
                ),
                values={
                    "principal": inr(principal),
                    "annual_rate": params.annual_rate,
                    "tenor_months": params.tenor_months,
                    "emi": inr(schedule[0].amount_minor),
                    "outstanding_at_horizon_end": inr(principal - repaid),
                },
                metric_codes=["debt.outstanding", "debt.service_burden", "debt.new_loans_6m"],
            )
        )

    def describe(self, params: Any) -> str:
        return f"New debt of ₹{params.principal:,.0f} is added"


# --- 9: interest rates rise --------------------------------------------------------------------


@register
class InterestRateIncrease(Shock):
    code = "interest_rate_increase"
    name = "Interest rate increase"
    description = (
        "Rates on existing loans rise (treated as floating): each loan's remaining instalments "
        "are re-amortised over the same remaining term at the higher rate. Overdraft interest "
        "rises by the same amount."
    )

    class Params(ShockParams):
        type: Literal["interest_rate_increase"]
        increase_bps: int = Field(ge=1, le=2000, description="200 = +2 percentage points")
        applies_to_overdraft: bool = True

    def apply(self, params: Any, levers: Levers) -> None:
        b = levers.baseline
        horizon_end = month_end(b.projection_months[-1])
        changes = []
        for loan in b.loans:
            future = [r for r in loan.remaining if r[0] > b.as_of]
            if not future:
                continue
            principal = sum(p for _, _, p in future)
            rate = Decimal(loan.annual_rate_bps + params.increase_bps) / 10_000
            repriced = amortize(principal, float(rate), len(future))
            for (due, amount, old_principal), new in zip(future, repriced, strict=True):
                if due > horizon_end or due < b.projection_months[params.start_month - 1]:
                    continue
                k = next(i for i, m in enumerate(b.projection_months) if due <= month_end(m))
                levers.debt_service[k] += new.amount_minor - amount
                levers.principal_repaid[k] += new.principal_minor - old_principal
            changes.append(
                (loan.lender, future[0][1], repriced[0].amount_minor, loan.annual_rate_bps)
            )
        if params.applies_to_overdraft and b.overdraft_limit > 0:
            levers.overdraft_rate += Decimal(params.increase_bps) / 10_000
        text = f"Interest rates rise by {params.increase_bps} basis points. " + (
            "; ".join(
                f"{lender}: EMI {rs(old)} → {rs(new)} "
                f"(rate {Decimal(bps) / 100}% → {Decimal(bps + params.increase_bps) / 100}%)"
                for lender, old, new, bps in changes
            )
            if changes
            else "No loans with remaining instalments."
        )
        if params.applies_to_overdraft and b.overdraft_limit > 0:
            text += (
                f" Overdraft interest: {pct(b.overdraft_rate)} → {pct(levers.overdraft_rate)}"
                " (assumed base rate)."
            )
        levers.evidence.append(
            Evidence(
                id=f"shock.{self.code}",
                kind="shock",
                text=text,
                values={
                    "increase_bps": params.increase_bps,
                    "loans_repriced": len(changes),
                    "overdraft_rate": levers.overdraft_rate,
                },
                metric_codes=["debt.service_burden"],
                sources=[b.sources["loans"]],
            )
        )

    def describe(self, params: Any) -> str:
        return f"Interest rates increase by {params.increase_bps} bps"


# --- 10: a major supplier raises prices ---------------------------------------------------------


@register
class SupplierCostIncrease(Shock):
    code = "supplier_cost_increase"
    name = "Major supplier cost increase"
    description = (
        "One supplier (by default the one paid the most) raises prices by a percentage; "
        "purchases from them and payments to them rise accordingly."
    )

    class Params(TimedParams):
        type: Literal["supplier_cost_increase"]
        increase_pct: Decimal = Field(gt=0, le=5, description="0.1 = prices rise by 10%")
        supplier_id: uuid.UUID | None = Field(None, description="Default: the largest supplier")

    def resolve(self, params: Any, baseline: Baseline) -> Any:
        if params.supplier_id is None:
            supplier = _largest(baseline.suppliers, "suppliers")
            return params.model_copy(update={"supplier_id": supplier.party_id})
        _find(baseline.suppliers, params.supplier_id, "supplier")
        return params

    def apply(self, params: Any, levers: Levers) -> None:
        b = levers.baseline
        supplier = _find(b.suppliers, params.supplier_id, "supplier")
        months = active_months(params, levers.horizon)
        extra_cash = round_minor(supplier.monthly_cash * params.increase_pct)
        extra_docs = round_minor(supplier.monthly_documents * params.increase_pct)
        share = pct(supplier.share.quantize(Decimal("0.001")))
        for k in months:
            levers.supplier_payments_delta[k] += extra_cash
            levers.purchases_delta[k] += extra_docs
        levers.evidence.append(
            Evidence(
                id=f"shock.{self.code}",
                kind="shock",
                text=(
                    f"{supplier.name} ({share} of supplier "
                    f"payments, about {rs(supplier.monthly_cash)} a month) raises prices "
                    f"{pct(params.increase_pct)}: {rs(extra_cash)} more paid each month."
                ),
                values={
                    "supplier": supplier.name,
                    "supplier_share_of_payments": supplier.share.quantize(Decimal("0.0001")),
                    "supplier_monthly_payments": inr(supplier.monthly_cash),
                    "increase_pct": params.increase_pct,
                    "extra_per_month": inr(extra_cash),
                },
                metric_codes=["suppliers.concentration", "expenses.monthly"],
                sources=[b.sources["supplier_payments"]],
            )
        )

    def describe(self, params: Any) -> str:
        return f"Major supplier raises prices by {pct(params.increase_pct)}"


def _params_union() -> Any:
    models = tuple(s.Params for s in SHOCKS.values())
    union: Any = models[0]
    for model in models[1:]:
        union = union | model
    return Annotated[union, Field(discriminator="type")]


# A request's shock: validated against the matching Params model by its "type".
ShockSpec = _params_union()
