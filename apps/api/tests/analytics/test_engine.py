"""Engine-level properties, checked on every synthetic entity."""

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from finpulse.analytics import CATALOGUE, compute_report, default_as_of
from finpulse.analytics.inputs import FinancialData
from finpulse.analytics.metrics import ALL_METRICS
from finpulse.analytics.schemas import FinancialMetricsReport, Metric
from finpulse.synthetic import SCENARIOS, Dataset, generate
from finpulse.synthetic.summary import monthly_summary
from tests.analytics.synthetic_adapter import to_financial_data

REQUIRED = {
    "revenue.monthly",
    "expenses.monthly",
    "cashflow.net_monthly",
    "revenue.growth",
    "revenue.volatility",
    "expenses.growth",
    "cash.balance",
    "cash.runway",
    "receivables.outstanding",
    "receivables.days",
    "payables.days",
    "debt.outstanding",
    "debt.service_burden",
    "customers.concentration",
    "suppliers.concentration",
    "income.stability",
    "payments.consistency",
    "liquidity.ratio",
    "buffer.months",
    "transactions.consistency",
}

_datasets: dict[str, Dataset] = {}


def dataset(code: str) -> Dataset:
    if code not in _datasets:
        _datasets[code] = generate(SCENARIOS[code])
    return _datasets[code]


def report(code: str, as_of: date | None = None) -> FinancialMetricsReport:
    data = to_financial_data(dataset(code))
    return compute_report(data, as_of or default_as_of(data))  # type: ignore[arg-type]


def m(r: FinancialMetricsReport, code: str) -> Metric:
    (found,) = [x for x in r.metrics if x.code == code]
    return found


def v(r: FinancialMetricsReport, code: str) -> Decimal:
    value = m(r, code).value
    assert value is not None, (code, m(r, code).notes)
    return value


def inr(minor: int) -> Decimal:
    return (Decimal(minor) / 100).quantize(Decimal("0.01"))


codes = pytest.mark.parametrize("code", sorted(SCENARIOS))


# --- shape ------------------------------------------------------------------------------------


def test_catalogue_covers_every_required_metric_once() -> None:
    assert set(CATALOGUE) >= REQUIRED
    assert len(ALL_METRICS) == len(CATALOGUE)


@codes
def test_every_metric_is_reported_once_with_consistent_availability(code: str) -> None:
    r = report(code)

    assert [x.code for x in r.metrics] == list(CATALOGUE)
    for x in r.metrics:
        assert x.method and x.unit and x.version >= 1
        assert x.period.start <= x.period.end <= r.as_of
        if x.availability == "available":
            assert x.value is not None and x.confidence is not None
        else:
            assert x.value is None and x.confidence is None and x.notes


@codes
def test_report_is_deterministic_and_json_round_trips(code: str) -> None:
    first, second = report(code), report(code)

    assert first == second
    payload = first.model_dump_json()
    assert FinancialMetricsReport.model_validate_json(payload) == first
    assert json.loads(payload)["metrics"][0]["value"] is None or isinstance(
        json.loads(payload)["metrics"][0]["value"],
        str,  # decimals travel as exact strings
    )


@codes
def test_source_references_point_at_real_records(code: str) -> None:
    ds = dataset(code)
    known = {
        "transactions": {t.id for t in ds.transactions},
        "invoices": {i.id for i in ds.invoices},
        "invoice_payments": {p.id for p in ds.invoice_payments},
        "bills": {b.id for b in ds.bills},
        "bill_payments": {p.id for p in ds.bill_payments},
        "loans": {loan.id for loan in ds.loans},
        "loan_installments": {i.id for i in ds.installments},
        "counter_sales": {s.id for s in ds.counter_sales},
        "accounts": {a.id for a in ds.accounts},
    }
    for x in report(code).metrics:
        for ref in x.sources:
            assert len(ref.sample_ids) <= min(5, ref.record_count)
            assert set(ref.sample_ids) <= known[ref.table], (x.code, ref.table)


# --- no look-ahead ----------------------------------------------------------------------------


def truncate(data: FinancialData, as_of: date) -> FinancialData:
    """What the data would have looked like on ``as_of``."""
    loans = tuple(loan for loan in data.loans if loan.disbursed_on <= as_of)
    loan_ids = {loan.id for loan in loans}
    instalments = tuple(
        i if i.paid_on is not None and i.paid_on <= as_of else replace(i, paid_on=None, bounces=0)
        for i in data.installments
        if i.loan_id in loan_ids
    )
    return replace(
        data,
        transactions=tuple(t for t in data.transactions if t.posted_on <= as_of),
        invoices=tuple(i for i in data.invoices if i.issued_on <= as_of),
        invoice_payments=tuple(p for p in data.invoice_payments if p.paid_on <= as_of),
        bills=tuple(b for b in data.bills if b.issued_on <= as_of),
        bill_payments=tuple(p for p in data.bill_payments if p.paid_on <= as_of),
        loans=loans,
        installments=instalments,
        counter_sales=tuple(s for s in data.counter_sales if s.sold_on <= as_of),
        data_through=as_of,
    )


@codes
@pytest.mark.parametrize("as_of", [date(2026, 1, 15), date(2026, 5, 31), date(2026, 8, 20)])
def test_a_past_report_never_sees_later_data(code: str, as_of: date) -> None:
    full = to_financial_data(dataset(code))

    assert compute_report(full, as_of) == compute_report(truncate(full, as_of), as_of)


# --- reconciliation with the synthetic books --------------------------------------------------


@codes
def test_point_in_time_metrics_match_the_books(code: str) -> None:
    ds, r = dataset(code), report(code)
    last = monthly_summary(ds)[-1]

    assert v(r, "cash.balance") == inr(last.closing_balance_minor)
    assert v(r, "debt.outstanding") == inr(last.debt_outstanding_minor)
    assert v(r, "cashflow.net_monthly") == inr(last.net_cash_flow_minor)
    if ds.invoices:
        assert v(r, "receivables.outstanding") == inr(last.receivables_minor)


@codes
def test_monthly_revenue_matches_sales_documents(code: str) -> None:
    ds, r = dataset(code), report(code)
    month = r.metrics[0].period
    expected = sum(
        i.taxable_minor for i in ds.invoices if month.start <= i.issued_on <= month.end
    ) + sum(
        s.gross_minor - s.tax_minor
        for s in ds.counter_sales
        if month.start <= s.sold_on <= month.end
    )

    assert v(r, "revenue.monthly") == inr(expected)
    series = {p.period.label: p.value for p in r.series[0].points}
    assert series[month.label] == v(r, "revenue.monthly")


# --- the metrics tell each archetype's story --------------------------------------------------


def test_mehra_lighting_deterioration_is_visible() -> None:
    before = report("mehra_lighting", date(2025, 10, 31))  # last month before onset
    after = report("mehra_lighting")

    assert v(after, "revenue.growth") < Decimal("-0.1")
    assert v(after, "cash.balance") < 0 < v(before, "cash.balance")
    # A retailer on supplier credit runs below 1 even when healthy; the decline is what matters.
    assert v(after, "liquidity.ratio") < Decimal("0.6") * v(before, "liquidity.ratio")
    assert v(after, "cash.runway") < Decimal(1)
    assert v(after, "debt.outstanding") > v(before, "debt.outstanding")  # new digital loans
    assert v(after, "buffer.months") < v(before, "buffer.months")
    assert m(after, "payments.consistency").components["bounce_charges"] == 3
    assert m(before, "payments.consistency").components["bounce_charges"] == 0


def test_healthy_msme_looks_healthy() -> None:
    r = report("kaveri_packaging")

    assert v(r, "payments.consistency") == Decimal("1.0000")
    assert v(r, "liquidity.ratio") > Decimal("1.5")
    assert v(r, "debt.service_burden") < Decimal("0.05")
    assert v(r, "customers.concentration") < Decimal("0.25")


def test_thin_file_msme_has_no_debt_but_is_sound() -> None:
    r = report("annapurna_kitchen")

    assert v(r, "debt.outstanding") == 0 and v(r, "debt.service_burden") == 0
    assert m(r, "cash.runway").availability == "not_applicable"  # not burning cash
    assert v(r, "revenue.growth") > 0
    assert v(r, "buffer.months") > Decimal(1)


def test_high_risk_msme_shows_stress() -> None:
    r = report("rapid_mobile_hub")

    assert v(r, "cash.balance") < 0
    assert v(r, "liquidity.ratio") < Decimal("0.3")
    assert v(r, "payments.consistency") < Decimal("0.8")
    assert v(r, "buffer.months") == 0


def test_freelancer_metrics_fit_an_individual() -> None:
    r = report("ananya_rao_design")

    assert r.entity.kind == "individual"
    assert m(r, "payables.days").availability == "not_applicable"
    assert m(r, "suppliers.concentration").availability == "not_applicable"
    assert v(r, "revenue.volatility") > Decimal("0.3")  # lumpy project income
    assert v(r, "buffer.months") > Decimal(6)


def test_as_of_defaults_to_the_end_of_the_data() -> None:
    data = to_financial_data(dataset("kaveri_packaging"))

    assert default_as_of(data) == dataset("kaveri_packaging").as_of
    assert default_as_of(replace(data, data_through=None)) == data.transactions[-1].posted_on
