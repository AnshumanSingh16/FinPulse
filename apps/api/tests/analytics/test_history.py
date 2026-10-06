"""Metric history: each point equals the report computed as of that date."""

from datetime import date

from finpulse.analytics import compute_report
from finpulse.analytics.history import metric_history
from tests.test_entities_api import SHARMA


def test_each_point_is_the_report_as_of_that_month_end() -> None:
    history = metric_history(SHARMA, date(2026, 9, 30), 12, ["liquidity.ratio", "receivables.days"])

    assert [p.as_of for p in history.points][-3:] == [
        date(2026, 7, 31),
        date(2026, 8, 31),
        date(2026, 9, 30),
    ]
    assert len(history.points) == 12
    assert [m.code for m in history.metrics] == ["liquidity.ratio", "receivables.days"]
    for p in history.points[::4]:
        report = {m.code: m.value for m in compute_report(SHARMA, p.as_of).metrics}
        assert p.values == {c: report[c] for c in ("liquidity.ratio", "receivables.days")}


def test_mid_month_as_of_is_the_last_point_and_history_stops_at_the_data() -> None:
    history = metric_history(SHARMA, date(2025, 6, 15), 12)

    assert history.points[-1].as_of == date(2025, 6, 15)
    assert history.points[0].as_of >= date(2025, 4, 1)  # Sharma's data starts in April 2025
    assert len(history.metrics) == 25
