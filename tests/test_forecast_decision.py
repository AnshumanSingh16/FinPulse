"""Cash forecasts and purchase simulations, checked against hand calculations."""

import pytest

from finpilot.engine.decision import Purchase, default_buffer, emi, simulate_purchase
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow


class TestForecast:
    def test_scheduled_only(self, tiny):
        f = forecast_cash_flow(tiny["ledger"], tiny["balances"], tiny["obligations"], tiny["as_of"])
        assert f["starting_cash"] == 152_000
        # Overdue bill (15k) paid on day 1; rent 20k on 5 May; INV-2 25k on 15 May.
        # Overdue receivable INV-1 not counted by default.
        cp = {c["days"]: c for c in f["checkpoints"]}
        assert cp[30]["balance"] == 152_000 - 15_000 - 20_000 + 25_000
        assert cp[30]["inflows"] == 25_000 and cp[30]["outflows"] == 35_000
        assert cp[90]["balance"] == cp[30]["balance"]
        assert f["lowest_balance"] == 117_000 and f["lowest_balance_date"] == "2026-05-05"
        assert f["excluded_items"][0]["item_id"] == "INV-1"
        assert any("NOT counted" in a for a in f["evidence"]["assumptions"])
        assert any("not a prediction" in l for l in f["evidence"]["limitations"])

    def test_overdue_receivable_and_delay(self, tiny):
        f = forecast_cash_flow(
            tiny["ledger"], tiny["balances"], tiny["obligations"], tiny["as_of"],
            ForecastOptions(include_overdue_receivables=True, overdue_receivable_days=10, receivable_delay_days=30, receivable_collection_pct=80),
        )
        cp = {c["days"]: c for c in f["checkpoints"]}
        # INV-1: 80% of 40k on 10 May. INV-2: 80% of 25k on 14 Jun (15 May + 30).
        assert cp[30]["balance"] == 152_000 - 35_000 + 32_000
        assert cp[60]["balance"] == cp[30]["balance"] + 20_000

    def test_run_rate_adds_unscheduled_costs_without_double_counting(self, tiny):
        plain = forecast_cash_flow(tiny["ledger"], tiny["balances"], tiny["obligations"], tiny["as_of"])
        rr = forecast_cash_flow(tiny["ledger"], tiny["balances"], tiny["obligations"], tiny["as_of"], ForecastOptions(include_run_rate=True, run_rate_months=2))
        # Rent has a scheduled item (5 May) so its run-rate only starts after it.
        rent_days = [i for i in rr["daily"] if i["date"] <= "2026-05-05"]
        assert rent_days  # sanity
        assert rr["assumed_flows_total"] != 0
        assert rr["checkpoints"][-1]["balance"] != plain["checkpoints"][-1]["balance"]
        assert any("Typical unscheduled flows" in a for a in rr["evidence"]["assumptions"])

    def test_buffer_and_negative_dates(self, tiny):
        f = forecast_cash_flow(tiny["ledger"], tiny["balances"], tiny["obligations"], tiny["as_of"],
                               ForecastOptions(min_buffer=130_000, extra_flows=[{"date": "2026-05-10", "amount": -200_000, "label": "Big"}]))
        # 152k − 15k = 137k on 1 May (still above 130k); − 20k rent on 5 May = 117k.
        assert f["first_date_below_buffer"] == "2026-05-05"
        assert f["first_negative_date"] == "2026-05-10"

    def test_no_balance_no_forecast(self, tiny):
        f = forecast_cash_flow(tiny["ledger"], None, tiny["obligations"], tiny["as_of"])
        assert f["status"] == "insufficient_data"
        assert "dated opening balance" in f["missing"]

    def test_no_obligations_is_qualified(self, tiny):
        f = forecast_cash_flow(tiny["ledger"], tiny["balances"], None, tiny["as_of"])
        assert f["status"] == "ok"
        assert f["checkpoints"][0]["balance"] == 152_000
        assert any("No invoices or bills" in l for l in f["evidence"]["limitations"])


class TestDecision:
    def test_emi_formula(self):
        # 10 lakh at 12% for 24 months: 1,000,000 × 0.01 × 1.01^24 / (1.01^24 − 1)
        assert emi(1_000_000, 12, 24) == pytest.approx(47_073.47, abs=0.01)
        assert emi(120_000, 0, 12) == 10_000
        assert emi(0, 10, 12) == 0

    def test_cash_purchase_scenarios(self, tiny):
        p = Purchase(name="Oven", cost=60_000, purchase_date="2026-05-01", monthly_benefit=10_000, benefit_start_months=1)
        r = simulate_purchase(tiny["ledger"], tiny["balances"], tiny["obligations"], tiny["as_of"], p,
                              horizon_days=90, min_buffer=50_000, include_run_rate=False)
        sc = {s["scenario"]: s for s in r["scenarios"]}
        base = sc["base"]
        # Without: 152k −15k (1 May) −20k (5 May) +25k (15 May) = 142k at day 90.
        assert base["without_purchase"]["end_balance"] == 142_000
        # With: −60k on 1 May; benefits 1 Jun, 1 Jul (2 × 10k) inside 90 days (to 29 Jul).
        assert base["with_purchase"]["end_balance"] == 142_000 - 60_000 + 20_000
        assert base["purchase_cash_impact"] == -40_000
        # Downside: benefit halved and 2 months late → none inside 90 days; INV-2 delayed 30 days to
        # 14 Jun at 90% → 22.5k.
        down = sc["downside"]
        assert down["with_purchase"]["end_balance"] == 152_000 - 35_000 + 22_500 - 60_000
        assert r["payback_months"] == 6.0
        assert r["verdict_tone"] == "good"

    def test_loan_purchase(self, tiny):
        p = Purchase(name="Van", cost=600_000, purchase_date="2026-05-01", financing="loan", down_payment_pct=20,
                     loan_rate_pct=12, tenure_months=24)
        r = simulate_purchase(tiny["ledger"], tiny["balances"], tiny["obligations"], tiny["as_of"], p,
                              horizon_days=90, min_buffer=50_000, include_run_rate=False)
        assert r["emi"] == emi(480_000, 12, 24)
        base = next(s for s in r["scenarios"] if s["scenario"] == "base")
        # Down payment 120k on 1 May; EMIs on 1 Jun and 1 Jul.
        assert base["purchase_cash_impact"] == pytest.approx(-(120_000 + 2 * r["emi"]), abs=0.02)
        assert r["verdict_tone"] in ("caution", "bad")
        assert r["total_loan_interest"] == pytest.approx(r["emi"] * 24 - 480_000, abs=0.01)

    def test_unaffordable(self, tiny):
        p = Purchase(name="Shop", cost=500_000, purchase_date="2026-05-02")
        r = simulate_purchase(tiny["ledger"], tiny["balances"], tiny["obligations"], tiny["as_of"], p,
                              horizon_days=60, min_buffer=10_000, include_run_rate=False)
        assert r["verdict_tone"] == "bad"
        base = next(s for s in r["scenarios"] if s["scenario"] == "base")
        assert base["with_purchase"]["first_negative_date"] == "2026-05-02"

    def test_invalid_inputs(self, tiny):
        args = (tiny["ledger"], tiny["balances"], tiny["obligations"], tiny["as_of"])
        assert simulate_purchase(*args, Purchase("x", 0, "2026-05-01"))["status"] == "invalid"
        assert simulate_purchase(*args, Purchase("x", 10, "2026-01-01"))["status"] == "invalid"
        assert simulate_purchase(*args, Purchase("x", 10, "2026-05-01", financing="loan", down_payment_pct=100))["status"] == "invalid"

    def test_missing_balance_stops_simulation(self, tiny):
        r = simulate_purchase(tiny["ledger"], None, tiny["obligations"], tiny["as_of"], Purchase("x", 10, "2026-05-01"))
        assert r["status"] == "insufficient_data"

    def test_default_buffer(self, tiny):
        # Last 3 full months before 30 Apr: Feb (none), Mar 50k, Apr 70k opex → 120k / 3.
        assert default_buffer(tiny["ledger"], tiny["as_of"]) == 40_000


def test_run_rate_leaves_out_one_offs(demo):
    from finpilot.engine.forecast import run_rate

    led = demo["ledger"]
    rr = run_rate(led, "2026-09-30", 3)
    skipped = set(rr.attrs["excluded_one_offs"])
    by_desc = dict(zip(led["txn_id"], led["description"]))
    assert any("Consultancy" in by_desc[i] for i in skipped)
    assert any(by_desc[i] == "Electricity bill" for i in skipped)
    # Only the extra copy of the duplicated freight payment is left out, not both.
    freight = led[(led["category"] == "Logistics") & (led["date"] == "2026-08-18")]
    assert len(set(freight["txn_id"]) & skipped) == 1


def test_purchase_made_today_is_counted(tiny):
    # Regression: a purchase dated on the as-of day must not vanish into day 0's closing balance.
    p = Purchase(name="Oven", cost=60_000, purchase_date="2026-04-30")
    r = simulate_purchase(tiny["ledger"], tiny["balances"], tiny["obligations"], tiny["as_of"], p,
                          horizon_days=30, min_buffer=0, include_run_rate=False)
    base = next(s for s in r["scenarios"] if s["scenario"] == "base")
    assert base["with_purchase"]["end_balance"] == base["without_purchase"]["end_balance"] - 60_000
    # 152k today; 1 May: −60k oven and −15k overdue bill → 77k; 5 May rent −20k → 57k low point.
    assert base["with_purchase"]["lowest_balance"] == 57_000
    assert base["daily_with"][1] == {"date": "2026-05-01", "balance": 77_000}
