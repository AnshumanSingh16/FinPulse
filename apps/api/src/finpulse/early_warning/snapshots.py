"""The data as it stood on given dates, so rules can compare "now" with "then".

Each snapshot is an analytics ``Context`` built for its own date, so a past value never sees
later records (the analytics engine's no-look-ahead guarantee carries over). Snapshots and their
metrics are memoised: a 12-month risk timeline re-reads the same month-ends many times.
"""

from __future__ import annotations

import statistics
from datetime import date
from decimal import Decimal

from finpulse.analytics.context import Context
from finpulse.analytics.inputs import FinancialData
from finpulse.analytics.metrics import ALL_METRICS
from finpulse.analytics.schemas import Metric
from finpulse.core.dates import add_months, month_end


class Snapshot:
    def __init__(self, data: FinancialData, as_of: date) -> None:
        self.as_of = as_of
        self.ctx = Context(data, as_of)
        self._metrics: dict[str, Metric] | None = None

    def metric(self, code: str) -> Metric:
        if self._metrics is None:
            self._metrics = {m.code: m for m in (fn(self.ctx) for fn in ALL_METRICS)}
        return self._metrics[code]

    def value(self, code: str) -> Decimal | None:
        m = self.metric(code)
        return m.value if m.availability == "available" else None


def months_back(as_of: date, months: int) -> date:
    """``as_of`` shifted back by whole months; month-ends map to month-ends."""
    if as_of == month_end(as_of):
        return month_end(add_months(as_of, -months))
    return add_months(as_of, -months)


class History:
    def __init__(self, data: FinancialData) -> None:
        self.data = data
        self.first_date: date | None = data.transactions[0].posted_on if data.transactions else None
        self._snapshots: dict[date, Snapshot] = {}

    def at(self, day: date) -> Snapshot:
        if day not in self._snapshots:
            self._snapshots[day] = Snapshot(self.data, day)
        return self._snapshots[day]

    def baseline(
        self, as_of: date, code: str, lookback_months: int, points: int
    ) -> tuple[Decimal | None, list[tuple[date, Decimal]]]:
        """Median of a metric over ``points`` month-ends, the latest ``lookback_months`` before
        ``as_of``. A median of several points resists one-off spikes in point-in-time values.
        Needs at least half the points to be available."""
        values = []
        for i in range(points):
            day = months_back(as_of, lookback_months + i)
            if self.first_date is None or day < self.first_date:
                break
            v = self.at(day).value(code)
            if v is not None:
                values.append((day, v))
        if not values or len(values) < (points + 1) // 2:
            return None, values
        return Decimal(statistics.median(v for _, v in values)), values
