"""The bank ledger is internally consistent."""

from finpulse.synthetic import Dataset
from finpulse.synthetic.categories import Category, CounterpartyKind


def test_running_balance_is_the_sum_of_postings(ds: Dataset) -> None:
    (account,) = ds.accounts
    balance = account.opening_balance_minor
    for tx in ds.transactions:
        balance += tx.amount_minor
        assert tx.balance_after_minor == balance, tx


def test_postings_are_ordered_and_inside_the_window(ds: Dataset) -> None:
    seqs = [t.seq for t in ds.transactions]
    dates = [t.posted_on for t in ds.transactions]

    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    assert dates == sorted(dates)
    assert ds.start_date <= dates[0] and dates[-1] <= ds.as_of


def test_balance_never_breaches_the_overdraft_limit(ds: Dataset) -> None:
    (account,) = ds.accounts

    assert min(t.balance_after_minor for t in ds.transactions) >= -account.overdraft_limit_minor


def test_every_posting_is_labelled_and_non_zero(ds: Dataset) -> None:
    parties = {c.id: c for c in ds.counterparties}
    for tx in ds.transactions:
        assert tx.amount_minor != 0
        assert Category(tx.category)
        assert tx.counterparty_id is None or tx.counterparty_id in parties
        if tx.counterparty_id is None:
            assert tx.category == Category.SALES_CASH_DEPOSIT


def test_external_refs_are_unique(ds: Dataset) -> None:
    refs = [t.external_ref for t in ds.transactions]

    assert len(refs) == len(set(refs))


def test_income_comes_from_customers_and_spend_goes_to_payees(ds: Dataset) -> None:
    kinds = {c.id: c.kind for c in ds.counterparties}
    for tx in ds.transactions:
        if tx.category in {Category.CUSTOMER_PAYMENT, Category.CLIENT_PAYMENT}:
            assert tx.amount_minor > 0 and kinds[tx.counterparty_id] == CounterpartyKind.CUSTOMER
        if tx.category == Category.PLATFORM_PAYOUT:
            assert tx.amount_minor > 0 and kinds[tx.counterparty_id] == CounterpartyKind.PLATFORM
        if tx.category == Category.SUPPLIER_PAYMENT:
            assert tx.amount_minor < 0 and kinds[tx.counterparty_id] == CounterpartyKind.SUPPLIER
        if tx.category == Category.SALARY:
            assert tx.amount_minor < 0 and kinds[tx.counterparty_id] == CounterpartyKind.EMPLOYEE


def test_history_covers_the_requested_period(ds: Dataset) -> None:
    months = (ds.as_of.year - ds.start_date.year) * 12 + ds.as_of.month - ds.start_date.month + 1

    assert 12 <= months <= 18
    assert ds.params["months"] == months
