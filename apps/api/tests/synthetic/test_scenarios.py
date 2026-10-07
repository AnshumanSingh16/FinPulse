"""Each scenario behaves like the archetype it claims to be."""

import statistics
from datetime import date

import pytest

from finpulse.synthetic import PRIMARY_DEMO, SCENARIOS, Dataset
from finpulse.synthetic import calendar as cal
from finpulse.synthetic.categories import Category
from finpulse.synthetic.spec import CustomerVolumeShock, ScenarioSpec
from finpulse.synthetic.summary import monthly_summary
from tests.synthetic.conftest import dataset_for

REQUIRED = {"healthy_msme", "thin_file_msme", "deteriorating_msme", "high_risk_msme", "freelancer"}


def by_archetype(archetype: str) -> Dataset:
    (code,) = [c for c, s in SCENARIOS.items() if s.archetype == archetype]
    return dataset_for(code)


def sales(ds: Dataset, first: date, last: date) -> int:
    return sum(
        m.invoiced_minor + m.counter_sales_minor
        for m in monthly_summary(ds)
        if first <= m.month <= last
    )


def bounces(ds: Dataset) -> int:
    return sum(1 for t in ds.transactions if t.category == Category.BOUNCE_CHARGE)


def test_all_required_archetypes_exist() -> None:
    assert {s.archetype for s in SCENARIOS.values()} >= REQUIRED


def test_primary_demo_is_sharma_electricals_with_18_months() -> None:
    ds = dataset_for(PRIMARY_DEMO)

    assert ds.subject.display_name == "Sharma Electricals"
    assert len(monthly_summary(ds)) == 18
    assert ds.invoices and ds.bills and ds.loans and ds.counter_sales


def test_healthy_msme() -> None:
    ds = by_archetype("healthy_msme")
    (account,) = ds.accounts

    assert not ds.ground_truth.deteriorates
    assert bounces(ds) == 0
    assert all(i.status in {"paid_on_time", "scheduled"} for i in ds.installments)
    assert min(t.balance_after_minor for t in ds.transactions) > 0  # never in overdraft
    assert ds.transactions[-1].balance_after_minor > account.opening_balance_minor


def test_thin_file_msme_is_invisible_to_the_bureau_but_healthy() -> None:
    ds = by_archetype("thin_file_msme")

    assert not ds.loans and not ds.bureau_events  # no credit history at all
    assert min(t.balance_after_minor for t in ds.transactions) > 0
    first, last = monthly_summary(ds)[:3], monthly_summary(ds)[-3:]
    assert sum(m.invoiced_minor + m.counter_sales_minor for m in last) > 1.15 * sum(
        m.invoiced_minor + m.counter_sales_minor for m in first
    )


def test_deteriorating_msme_declines_before_the_bureau_notices() -> None:
    ds = by_archetype("deteriorating_msme")
    gt = ds.ground_truth
    assert gt.deteriorates and gt.onset_date is not None
    onset = gt.onset_date

    before = sales(ds, ds.start_date, cal.add_months(onset, -1)) / cal.month_index(
        ds.start_date, onset
    )
    late_start = cal.add_months(onset, 4)
    after = sales(ds, late_start, ds.as_of) / (cal.month_index(late_start, ds.as_of) + 1)
    assert after < 0.75 * before

    # Cash stress shows in the bank data only after onset…
    charges = [t.posted_on for t in ds.transactions if t.category == Category.BOUNCE_CHARGE]
    assert charges and min(charges) > onset
    unreported = [loan for loan in ds.loans if not loan.reports_to_bureau]
    assert len(unreported) >= 2 and all(loan.disbursed_on > onset for loan in unreported)
    assert min(t.balance_after_minor for t in ds.transactions if t.posted_on < onset) > 0
    assert min(t.balance_after_minor for t in ds.transactions if t.posted_on >= onset) < 0
    # …while a traditional bureau still has nothing adverse on file.
    assert not [e for e in ds.bureau_events if e.event_type.startswith("dpd_")]


def test_deteriorating_msme_loses_its_largest_customer() -> None:
    spec = SCENARIOS["mehra_lighting"]
    ds = dataset_for("mehra_lighting")
    (shock,) = [s for s in spec.shocks if isinstance(s, CustomerVolumeShock)]
    customer = next(c.id for c in ds.counterparties if c.name == "Shree Ganesh Builders")
    onset = ds.ground_truth.onset_date
    assert onset is not None

    def share(first: date, last: date) -> float:
        docs = [i for i in ds.invoices if first <= i.issued_on <= last]
        return sum(i.total_minor for i in docs if i.customer_id == customer) / sum(
            i.total_minor for i in docs
        )

    assert shock.customer == "shree_ganesh"
    assert share(ds.start_date, onset) > 0.4
    assert share(cal.add_months(onset, 5), ds.as_of) < 0.15


def test_high_risk_msme() -> None:
    ds = by_archetype("high_risk_msme")
    days_overdrawn = {t.posted_on for t in ds.transactions if t.balance_after_minor < 0}

    assert len(days_overdrawn) > 0.3 * len({t.posted_on for t in ds.transactions})
    assert bounces(ds) >= 3
    assert len({loan.lender_id for loan in ds.loans}) >= 3
    assert any(t.category == Category.BETTING for t in ds.transactions)
    assert any(t.category == Category.CASH_WITHDRAWAL for t in ds.transactions)


def test_freelancer() -> None:
    ds = by_archetype("freelancer")
    income = [m.collections_minor for m in monthly_summary(ds)]

    assert ds.subject.kind == "individual"
    assert not ds.bills and not ds.counter_sales
    assert not any(t.category == Category.SALARY for t in ds.transactions)
    assert statistics.pstdev(income) / statistics.mean(income) > 0.3  # lumpy income
    assert any(t.category == Category.ADVANCE_TAX for t in ds.transactions)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"months": 0}, "months"),
        ({"start": date(2025, 4, 2)}, "first day"),
        ({"seasonality": (1.0,) * 11}, "seasonality"),
        ({"shocks": (CustomerVolumeShock("nobody", 1, 0.5),)}, "unknown customer"),
    ],
)
def test_invalid_specs_are_rejected(change: dict[str, object], message: str) -> None:
    from dataclasses import replace

    with pytest.raises(ValueError, match=message):
        replace(SCENARIOS[PRIMARY_DEMO], **change)  # type: ignore[arg-type]


def test_scenario_specs_are_frozen() -> None:
    spec: ScenarioSpec = SCENARIOS[PRIMARY_DEMO]

    with pytest.raises(AttributeError):
        spec.seed = 1  # type: ignore[misc]
