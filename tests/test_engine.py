"""Financial engine: every expected figure below is worked out by hand from the fixtures."""

import pandas as pd
import pytest

from finpilot.engine.cash import cash_position, obligations_status, upcoming_payments
from finpilot.engine.expenses import compare_expenses, default_periods, find_duplicates, unusual_transactions
from finpilot.engine.summary import financial_summary


class TestSummary:
    def test_revenue_expenses_profit_are_separate_from_cash(self, tiny):
        s = financial_summary(tiny["ledger"])
        # Revenue: sales only (T1 + T7). The loan (T4) is not revenue.
        assert s["revenue"] == 220_000
        # Operating: rent 40k + raw materials 75k + unknown 5k. Laptop (capex), drawings, GST excluded.
        assert s["operating_expenses"] == 120_000
        assert s["estimated_operating_profit"] == 100_000
        assert "Estimated" in s["profit_label"]
        assert s["other_flows"]["capex"] == 40_000
        assert s["other_flows"]["financing_in"] == 50_000
        assert s["other_flows"]["owner_drawings"] == 10_000
        assert s["other_flows"]["tax_remitted"] == 8_000
        # Cash movement counts everything: in 270k − out 178k.
        assert s["total_inflows"] == 270_000
        assert s["total_outflows"] == 178_000
        assert s["net_cash_movement"] == 92_000
        assert s["net_cash_movement"] != s["estimated_operating_profit"]

    def test_unrecognised_category_is_flagged(self, tiny):
        s = financial_summary(tiny["ledger"])
        assert s["unclassified_categories"] == ["Misc stuff"]
        assert any("Misc stuff" in l for l in s["evidence"]["limitations"])

    def test_period_filter_and_monthly(self, tiny):
        s = financial_summary(tiny["ledger"], "2026-04-01", "2026-04-30")
        assert s["revenue"] == 120_000
        assert s["operating_expenses"] == 70_000
        m = financial_summary(tiny["ledger"])["monthly"]
        assert [r["month"] for r in m] == ["2026-03", "2026-04"]
        assert m[0]["estimated_operating_profit"] == 50_000
        assert m[1]["estimated_operating_profit"] == 50_000

    def test_empty_period_is_insufficient(self, tiny):
        s = financial_summary(tiny["ledger"], "2025-01-01", "2025-01-31")
        assert s["status"] == "insufficient_data"

    def test_pending_bills_are_disclosed(self, tiny):
        s = financial_summary(tiny["ledger"], obligations=tiny["obligations"], as_of=tiny["as_of"])
        assert any("unpaid" in l for l in s["evidence"]["limitations"])

    def test_demo_totals_match_an_independent_sum(self, demo):
        led = demo["ledger"]
        s = financial_summary(led)
        revenue = sum(r.amount for r in led.itertuples() if r.direction == "in" and r.category.startswith("Sales"))
        assert s["revenue"] == pytest.approx(revenue, abs=0.01)
        total_in = sum(r.amount for r in led.itertuples() if r.direction == "in")
        total_out = sum(r.amount for r in led.itertuples() if r.direction == "out")
        assert s["net_cash_movement"] == pytest.approx(total_in - total_out, abs=0.01)


class TestExpenses:
    def test_compare_months(self, tiny):
        c = compare_expenses(tiny["ledger"], ("2026-03-01", "2026-03-31"), ("2026-04-01", "2026-04-30"))
        by = {r["category"]: r for r in c["by_category"]}
        assert by["Raw materials"]["change"] == 15_000
        assert by["Raw materials"]["change_pct"] == 50.0
        assert by["Rent"]["change"] == 0
        assert by["Misc stuff"]["change_pct"] is None  # new category: no % change
        assert c["total_a"] == 50_000 and c["total_b"] == 70_000
        assert c["by_category"][0]["category"] == "Raw materials"  # largest change first

    def test_default_periods(self):
        (a0, a1), (b0, b1) = default_periods("2026-09-30")
        assert (str(a0.date()), str(a1.date()), str(b0.date()), str(b1.date())) == (
            "2026-08-01", "2026-08-31", "2026-09-01", "2026-09-30")
        (a0, _), (b0, b1) = default_periods("2026-09-15", months=3)
        assert str(b0.date()) == "2026-06-01" and str(b1.date()) == "2026-08-31"
        assert str(a0.date()) == "2026-03-01"

    def test_demo_finds_the_planted_problems(self, demo):
        u = unusual_transactions(demo["ledger"], "2026-09-30", lookback_days=120)
        types = {(f["type"], f["category"]) for f in u["flags"]}
        assert ("possible_duplicate", "Logistics") in types
        assert ("outlier", "Electricity") in types
        consult = [f for f in u["flags"] if f["category"] == "Professional Fees"]
        assert consult and consult[0]["amount"] == 95_000

    def test_demo_raw_materials_rise(self, demo):
        c = compare_expenses(demo["ledger"], ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30"))
        rm = next(r for r in c["by_category"] if r["category"] == "Raw materials")
        assert rm["change_pct"] > 10


class TestDuplicates:
    def test_exact_repeat_is_grouped(self, tiny):
        led = pd.concat([tiny["ledger"], tiny["ledger"].iloc[[2]].assign(txn_id="T3b")])
        assert find_duplicates(led) == [["T3", "T3b"]]

    def test_same_amount_different_day_is_not_a_duplicate(self, tiny):
        led = pd.concat([tiny["ledger"], tiny["ledger"].iloc[[2]].assign(txn_id="T3b", date=pd.Timestamp("2026-03-11"))])
        assert find_duplicates(led) == []


class TestCash:
    def test_cash_from_dated_balance(self, tiny):
        c = cash_position(tiny["ledger"], tiny["balances"], tiny["as_of"])
        # 60,000 + 270,000 − 178,000
        assert c["cash_balance"] == 152_000
        assert c["anchor_balance"]["as_of"] == "2026-02-28"

    def test_mid_period_cash(self, tiny):
        c = cash_position(tiny["ledger"], tiny["balances"], "2026-03-12")
        assert c["cash_balance"] == 60_000 + 100_000 - 20_000 - 30_000

    def test_no_balance_means_unknown_not_revenue_minus_expenses(self, tiny):
        c = cash_position(tiny["ledger"], None, tiny["as_of"])
        assert c["status"] == "unknown"
        assert "cash_balance" not in c

    def test_balance_after_date_is_unknown(self, tiny):
        c = cash_position(tiny["ledger"], tiny["balances"], "2026-02-01")
        assert c["status"] == "unknown"

    def test_reconciliation_detects_a_gap(self, tiny):
        bal = pd.concat([tiny["balances"], pd.DataFrame({"as_of": [pd.Timestamp("2026-03-31")], "account": ["Bank"], "balance": [149_000.0]})])
        c = cash_position(tiny["ledger"], bal, tiny["as_of"])
        # Ledger says 60k + 150k − 100k = 110k on 31 Mar; stated 149k → 39k unexplained.
        assert c["reconciliation"][0]["computed_from_ledger"] == 110_000
        assert c["reconciliation"][0]["reconciled"] is False
        assert any("reconcile" in l for l in c["evidence"]["limitations"])

    def test_demo_reconciles(self, demo):
        c = cash_position(demo["ledger"], demo["balances"], "2026-09-30")
        assert all(r["reconciled"] for r in c["reconciliation"])

    def test_paid_pending_overdue(self, tiny):
        o = obligations_status(tiny["obligations"], tiny["as_of"])
        r, p = o["receivables"], o["payables"]
        assert r["paid"] == 100_000
        assert r["overdue"] == 40_000 and r["overdue_items"][0]["days_overdue"] == 10
        assert r["pending_not_due"] == 25_000
        assert p["overdue"] == 15_000 and p["pending_not_due"] == 20_000
        assert r["overdue_by_age"]["1-30 days"] == 40_000

    def test_upcoming_payments(self, tiny):
        u = upcoming_payments(tiny["obligations"], tiny["as_of"], days=10)
        assert u["overdue_total"] == 15_000
        assert u["upcoming_total"] == 20_000  # rent on 5 May
        assert upcoming_payments(tiny["obligations"], tiny["as_of"], days=3)["upcoming_total"] == 0

    def test_missing_obligations(self):
        assert obligations_status(None, "2026-04-30")["status"] == "insufficient_data"
        assert upcoming_payments(pd.DataFrame(), "2026-04-30")["status"] == "insufficient_data"


def test_alerts_on_demo_and_without_balance(demo):
    from finpilot.engine.alerts import build_alerts

    a = build_alerts(demo["ledger"], demo["balances"], demo["obligations"], "2026-09-30")
    titles = " | ".join(x["title"] for x in a)
    assert "customer payments overdue" in titles
    assert "possible duplicate" in titles
    assert "bills overdue" in titles
    none = build_alerts(demo["ledger"], None, None, "2026-09-30")
    assert none[0]["title"] == "Cash position unknown"
