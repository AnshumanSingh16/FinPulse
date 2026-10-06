"""Month-by-month cash projection. The only place scenario arithmetic happens.

For each projected month (shocks only change the levers):

    revenue   = baseline revenue × revenue factor
    expenses  = purchases × purchases factor + purchases delta + opex × opex factor
    money in  = operating receipts × receipts factor + receipts delta + other inflows + new loans
    money out = supplier payments × purchases factor + supplier delta + opex × opex factor
                + other outflows + debt service + overdraft interest
    balance   = previous balance + money in − money out

Flows are rounded to whole rupees; overdraft interest (overdrawn amount at the start of the month
× rate ÷ 12) to the paisa. Funds are exhausted
when the balance falls below −(overdraft limit); the failure date assumes the month's flows are
spread evenly over its days.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from finpulse.core.money import round_minor
from finpulse.stress.baseline import Baseline
from finpulse.stress.shocks import Levers


@dataclass(frozen=True)
class SimMonth:
    month: date
    revenue: int
    expenses: int
    receipts: int
    money_in: int
    money_out: int
    borrowed: int
    debt_service: int
    principal_repaid: int
    overdraft_interest: int
    net: int
    opening_balance: int
    closing_balance: int

    @property
    def net_before_borrowing(self) -> int:
        return self.net - self.borrowed


@dataclass(frozen=True)
class FailureInfo:
    day: date
    month_index: int
    fraction: Decimal  # how far into the month funds ran out
    shortfall: int


@dataclass(frozen=True)
class Simulation:
    baseline: Baseline
    levers: Levers
    months: list[SimMonth]
    failure: FailureInfo | None

    @property
    def closing_balance(self) -> int:
        return self.months[-1].closing_balance

    @property
    def minimum(self) -> SimMonth:
        return min(self.months, key=lambda m: (m.closing_balance, m.month))

    def runway_months(self) -> Decimal | None:
        """Available funds at as_of ÷ average monthly net outflow before borrowing."""
        burn = -Decimal(sum(m.net_before_borrowing for m in self.months)) / len(self.months)
        if burn <= 0:
            return None
        funds = self.baseline.opening_balance + self.baseline.overdraft_limit
        return max(Decimal(0), Decimal(funds) / burn)

    def peak_overdraft_utilisation(self) -> Decimal | None:
        limit = self.baseline.overdraft_limit
        if limit <= 0:
            return None
        return max(Decimal(max(0, -m.closing_balance)) / limit for m in self.months)

    def average_outflows(self) -> Decimal:
        return Decimal(sum(m.money_out for m in self.months)) / len(self.months)

    def liquidity(self) -> tuple[Decimal | None, dict[str, int]]:
        """Current assets ÷ current liabilities at the end of the horizon."""
        b, lv = self.baseline, self.levers
        balance = self.closing_balance
        receivables = (
            round_minor(b.liquidity["receivables"] * lv.receivables_factor) + lv.receivables_delta
        )
        payables = round_minor(b.liquidity["payables"] * lv.purchases_factor[-1])
        debt_12m = b.principal_due_12m_after_horizon + lv.principal_due_12m_delta
        parts = {
            "cash": max(0, balance),
            "receivables": receivables,
            "payables": payables,
            "overdraft_drawn": max(0, -balance),
            "loan_principal_due_12_months": debt_12m,
        }
        liabilities = payables + parts["overdraft_drawn"] + debt_12m
        if liabilities <= 0:
            return None, parts
        return Decimal(parts["cash"] + receivables) / liabilities, parts

    def debt_at_end(self) -> int:
        """Principal outstanding at the end of the horizon: today's debt + new borrowing −
        principal repaid (scheduled, re-priced or new)."""
        return (
            self.baseline.debt_outstanding
            + sum(self.levers.disbursements)
            - sum(self.levers.principal_repaid)
        )


def simulate(levers: Levers) -> Simulation:
    b = levers.baseline
    balance = b.opening_balance
    months: list[SimMonth] = []
    failure: FailureInfo | None = None
    for k, m in enumerate(b.projection_months):
        revenue = round_minor(b.revenue * levers.revenue_factor[k])
        purchases = (
            round_minor(b.purchases * levers.purchases_factor[k]) + levers.purchases_delta[k]
        )
        opex = round_minor(b.opex * levers.opex_factor[k])
        receipts = (
            round_minor(b.operating_receipts * levers.receipts_factor[k]) + levers.receipts_delta[k]
        )
        supplier = (
            round_minor(b.supplier_payments * levers.purchases_factor[k])
            + levers.supplier_payments_delta[k]
        )
        od_interest = int(
            (Decimal(max(0, -balance)) * levers.overdraft_rate / 12).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            )
        )  # to the paisa
        money_in = receipts + b.other_inflows + levers.disbursements[k]
        money_out = supplier + opex + b.other_outflows + levers.debt_service[k] + od_interest
        net = money_in - money_out
        opening = balance
        balance += net
        months.append(
            SimMonth(
                month=m,
                revenue=revenue,
                expenses=purchases + opex,
                receipts=receipts,
                money_in=money_in,
                money_out=money_out,
                borrowed=levers.disbursements[k],
                debt_service=levers.debt_service[k],
                principal_repaid=levers.principal_repaid[k],
                overdraft_interest=od_interest,
                net=net,
                opening_balance=opening,
                closing_balance=balance,
            )
        )
        if failure is None and balance < -b.overdraft_limit:
            headroom = opening + b.overdraft_limit
            fraction = Decimal(0) if headroom <= 0 or net >= 0 else Decimal(headroom) / -net
            days = calendar.monthrange(m.year, m.month)[1]
            failure = FailureInfo(
                day=m + timedelta(days=min(days - 1, int(fraction * days))),
                month_index=k,
                fraction=fraction,
                shortfall=-(balance + b.overdraft_limit),
            )
    return Simulation(baseline=b, levers=levers, months=months, failure=failure)
