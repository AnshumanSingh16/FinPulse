"""Loan arithmetic: equated monthly instalments on a reducing balance."""

from __future__ import annotations

from dataclasses import dataclass

from finpulse.core.money import round_minor


@dataclass(frozen=True, slots=True)
class ScheduledInstallment:
    seq: int
    amount_minor: int
    principal_minor: int
    interest_minor: int
    outstanding_after_minor: int


def emi(principal_minor: int, annual_rate: float, tenor_months: int) -> int:
    """Standard EMI formula, rounded to the rupee."""
    if tenor_months <= 0:
        raise ValueError("tenor must be positive")
    r = annual_rate / 12
    if r == 0:
        return round_minor(principal_minor / tenor_months)
    growth = (1 + r) ** tenor_months
    return round_minor(principal_minor * r * growth / (growth - 1))


def amortize(
    principal_minor: int, annual_rate: float, tenor_months: int
) -> list[ScheduledInstallment]:
    """Instalment schedule. Interest is charged monthly on the outstanding principal; the last
    instalment absorbs rounding so principal repaid equals the amount borrowed exactly."""
    payment = emi(principal_minor, annual_rate, tenor_months)
    r = annual_rate / 12
    outstanding = principal_minor
    schedule: list[ScheduledInstallment] = []
    for seq in range(1, tenor_months + 1):
        interest = round(outstanding * r)
        principal = outstanding if seq == tenor_months else min(payment - interest, outstanding)
        outstanding -= principal
        schedule.append(
            ScheduledInstallment(
                seq=seq,
                amount_minor=principal + interest,
                principal_minor=principal,
                interest_minor=interest,
                outstanding_after_minor=outstanding,
            )
        )
    return schedule
