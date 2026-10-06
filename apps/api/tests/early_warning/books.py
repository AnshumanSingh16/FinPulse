"""Small hand-checkable trading histories for early-warning rule tests. Amounts in rupees."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, timedelta

from finpulse.analytics.inputs import FinancialData
from finpulse.core.dates import add_months, month_end
from tests.analytics.builders import Book

START = date(2025, 1, 1)
Event = tuple[date, Callable[[], object]]


def trading(
    revenue: Sequence[float],
    *,
    late_days: Callable[[int], int] = lambda month: 0,
    rent: float = 20_000,
    opening: float = 300_000,
    overdraft: float = 0,
    extra: Callable[[Book], list[Event]] | None = None,
) -> tuple[Book, FinancialData]:
    """One invoice a month to each of two customers (60% / 40% of that month's revenue, issued on
    the 5th, 30-day terms, paid ``late_days(month)`` after the due date) and rent on the 1st.
    The data runs to the end of the last month."""
    book = Book(opening=opening, overdraft=overdraft)
    alpha, beta = book.party("Alpha Ltd"), book.party("Beta Ltd")
    end = month_end(add_months(START, len(revenue) - 1))
    events: list[Event] = []
    for i, amount in enumerate(revenue):
        month = add_months(START, i)
        events.append((month, lambda m=month: book.txn(m, -rent, "expense.rent")))
        for customer, share in ((alpha, 0.6), (beta, 0.4)):
            inv = book.invoice(customer, month + timedelta(days=4), amount * share)
            paid = inv.due_on + timedelta(days=late_days(i))
            events.append(
                (
                    paid,
                    lambda inv=inv, c=customer, d=paid: book.receive(
                        inv, d, inv.total_minor / 100, c
                    ),
                )
            )
    events += extra(book) if extra else []
    for day, post in sorted(events, key=lambda e: e[0]):  # stable: same-day order kept
        if day <= end:
            post()
    book.data_through = end
    return book, book.data()
