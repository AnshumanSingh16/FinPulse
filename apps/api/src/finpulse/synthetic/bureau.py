"""A deliberately simple model of what a traditional credit bureau sees.

Lenders that report send a monthly snapshot of each loan. The bureau therefore only learns about
trouble when an instalment is still unpaid at a month-end, classifies it by days past due (DPD),
and receives the report some weeks later. Lenders that do not report (many digital lenders and
all informal credit) are invisible to it, as are a business's suppliers, customers and cash flow.

This exists only to *evaluate* FinPulse: early warnings are scored on how far ahead of these
events they fire. No analytics engine may read it.
"""

from __future__ import annotations

from datetime import date, timedelta

from finpulse.synthetic.calendar import add_months, month_end
from finpulse.synthetic.ids import IdFactory
from finpulse.synthetic.model import BureauEvent, BureauEventType, Installment, Loan

REPORTING_LAG_DAYS = 20
DPD_THRESHOLDS: tuple[tuple[int, BureauEventType], ...] = (
    (30, "dpd_30"),
    (60, "dpd_60"),
    (90, "dpd_90"),
)


def days_past_due(installments: list[Installment], on: date) -> int:
    """Age of the oldest instalment that was due by ``on`` and still unpaid at ``on``."""
    overdue = [
        (on - i.due_on).days
        for i in installments
        if i.due_on <= on and (i.paid_on is None or i.paid_on > on)
    ]
    return max(overdue, default=0)


def derive_bureau_events(
    loans: list[Loan], installments: list[Installment], as_of: date, ids: IdFactory
) -> list[BureauEvent]:
    events: list[BureauEvent] = []

    def emit(loan: Loan, event_type: BureauEventType, event_on: date) -> None:
        if event_on <= as_of:
            events.append(
                BureauEvent(
                    id=ids("bureau_event", f"{loan.id}/{event_type}/{event_on.isoformat()}"),
                    loan_id=loan.id,
                    event_type=event_type,
                    event_on=event_on,
                    reported_on=event_on + timedelta(days=REPORTING_LAG_DAYS),
                )
            )

    for loan in loans:
        if not loan.reports_to_bureau:
            continue
        schedule = sorted((i for i in installments if i.loan_id == loan.id), key=lambda i: i.seq)
        emit(loan, "account_opened", month_end(loan.disbursed_on))

        reported_level = 0  # highest DPD threshold reported in the current delinquency episode
        snapshot = month_end(loan.disbursed_on)
        while snapshot <= as_of:
            dpd = days_past_due(schedule, snapshot)
            if dpd == 0:
                reported_level = 0
            for threshold, event_type in DPD_THRESHOLDS:
                if dpd >= threshold > reported_level:
                    emit(loan, event_type, snapshot)
                    reported_level = threshold
            snapshot = month_end(add_months(snapshot, 1))

        if schedule and all(i.paid_on is not None for i in schedule):
            last_paid = max(i.paid_on for i in schedule if i.paid_on is not None)
            emit(loan, "closed", month_end(last_paid))

    return sorted(events, key=lambda e: (e.event_on, str(e.loan_id), e.event_type))
