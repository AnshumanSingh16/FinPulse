"""Historical passports: the score at each month-end, recomputed from the data as it stood then.

Recomputing (rather than storing) keeps history consistent with the current methodology and
data, and is cheap. Each point only sees data up to its own date: the analytics engine
guarantees no look-ahead.
"""

from __future__ import annotations

from datetime import date
from itertools import pairwise

from finpulse.analytics import compute_report
from finpulse.analytics.inputs import FinancialData
from finpulse.core.dates import add_months, month_end
from finpulse.scoring.config import ScoringModel
from finpulse.scoring.engine import explain_change, model_ref, score_passport
from finpulse.scoring.format import signed
from finpulse.scoring.schemas import HistoryPoint, Passport, PassportHistory

MAX_MONTHS = 24


def previous_month_end(as_of: date) -> date:
    """The latest month-end strictly before ``as_of``."""
    return month_end(add_months(as_of, -1))


def history_dates(as_of: date, months: int, first: date) -> list[date]:
    """Month-ends before ``as_of`` (at most ``months``), then ``as_of`` itself; never before the
    first transaction."""
    dates = [as_of]
    current = previous_month_end(as_of)
    while len(dates) < months and current >= first:
        dates.append(current)
        current = previous_month_end(current)
    return sorted(dates)


def passport_at(data: FinancialData, as_of: date, model: ScoringModel) -> Passport:
    return score_passport(compute_report(data, as_of), model)


def with_monthly_change(data: FinancialData, as_of: date, model: ScoringModel) -> Passport:
    """The passport at ``as_of``, with the change since the previous month-end explained."""
    current = passport_at(data, as_of, model)
    first = data.transactions[0].posted_on if data.transactions else as_of
    previous_date = previous_month_end(as_of)
    if previous_date < first:
        return current
    change = explain_change(passport_at(data, previous_date, model), current)
    return current.model_copy(update={"change_from_previous_month": change})


def passport_history(
    data: FinancialData, as_of: date, months: int, model: ScoringModel
) -> PassportHistory:
    first = data.transactions[0].posted_on if data.transactions else as_of
    passports = [passport_at(data, d, model) for d in history_dates(as_of, months, first)]
    changes = [
        change
        for before, after in pairwise(passports)
        if (change := explain_change(before, after, limit=3)) is not None
    ]
    scored = [p for p in passports if p.financial_health.score is not None]
    if len(scored) >= 2:
        a, b = scored[0], scored[-1]
        delta = b.financial_health.score - a.financial_health.score  # type: ignore[operator]
        summary = (
            f"From {a.as_of} to {b.as_of} the Financial Health score moved from "
            f"{a.financial_health.score} to {b.financial_health.score} ({signed(delta)})."
        )
    else:
        summary = "Not enough history to show a trend."
    return PassportHistory(
        entity=passports[-1].entity,
        model=model_ref(model),
        points=[
            HistoryPoint(
                as_of=p.as_of,
                score=p.financial_health.score,
                band=p.financial_health.band.code if p.financial_health.band else None,
                confidence=p.financial_health.confidence,
                provisional=p.financial_health.provisional,
                dimensions={d.code: d.score for d in p.dimensions},
            )
            for p in passports
        ],
        changes=changes,
        summary=summary,
        disclaimer=model.model.disclaimer,
    )
