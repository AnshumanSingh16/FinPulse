"""The stronger autopilot: simulated futures from customers' own payment history, a planner that searches every combination
and stress-tests the best, an auditor, the financing backup, "can I afford it?", the live agent crew and the "what changed" feed."""

import json
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot.agent.tools import ToolContext, run_tool
from finpilot.api import crew
from finpilot.api.dataset import _demo_tables
from finpilot.api.server import create_app
from finpilot.engine import autopilot as ap
from finpilot.engine import risk

AS_OF = pd.Timestamp("2026-09-30")
BOOKS = ("demo", "demo_agency", "demo_cafe")


@pytest.fixture(scope="module")
def tables():
    return {b: _demo_tables(b) for b in BOOKS}


@pytest.fixture(scope="module")
def plans(tables):
    return {b: ap.plan(t["ledger"], t["balances"], t["obligations"], AS_OF) for b, t in tables.items()}


def _client(tmp_path, monkeypatch, client=None):
    monkeypatch.setenv("FINPILOT_AI", "off")
    monkeypatch.setenv("FINPILOT_ENV_FILE", str(tmp_path / "test.env"))
    from finpilot.api import dataset

    monkeypatch.setattr(dataset, "today", lambda: AS_OF)
    c = TestClient(create_app(tmp_path / "t.db", client=client, static_dir=None))
    return c


@pytest.fixture
def app(tmp_path, monkeypatch):
    return _client(tmp_path, monkeypatch)


def stream(c, path, lang="en"):
    events = []
    with c.stream("POST", path, headers={"X-Lang": lang}) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


# ---------------------------------------------------------------- simulated futures


@pytest.mark.parametrize("book", BOOKS)
def test_simulation_without_randomness_is_exactly_the_forecast(tables, book):
    t = tables[book]
    obl, _ = ap.at_risk(t["obligations"], AS_OF)
    f = ap._forecast(t["ledger"], t["balances"], obl, AS_OF, 90, 0)
    m = risk.build(t["ledger"], t["obligations"], AS_OF, f, ap.stuck_parties(t["obligations"], AS_OF))
    path = risk.simulate(m, 0, deterministic=True)["_paths"][0]
    assert np.allclose(path, [d["balance"] for d in f["daily"]], atol=0.01)


def test_payment_dates_come_from_each_customers_history(tables):
    t = tables["demo_agency"]
    obl, _ = ap.at_risk(t["obligations"], AS_OF)
    f = ap._forecast(t["ledger"], t["balances"], obl, AS_OF, 90, 0)
    m = risk.build(t["ledger"], t["obligations"], AS_OF, f, {"Kaveri Hospitals"})
    o = t["obligations"]
    paid = o[(o["counterparty"] == "UrbanFit Gyms") & (o["status"] == "paid")]
    expected = sorted((pd.to_datetime(paid["paid_date"]) - pd.to_datetime(paid["due_date"])).dt.days.clip(lower=0))
    assert sorted(m.delays["UrbanFit Gyms"]) == expected
    assert {r["kind"] for r in m.receivables if r["party"] == "Kaveri Hospitals"} == {"stuck"}


def test_reminding_a_stuck_customer_raises_the_odds_and_runs_are_repeatable(tables):
    t = tables["demo_agency"]
    obl, _ = ap.at_risk(t["obligations"], AS_OF)
    f = ap._forecast(t["ledger"], t["balances"], obl, AS_OF, 90, 333_000)
    m = risk.build(t["ledger"], t["obligations"], AS_OF, f, {"Kaveri Hospitals"})
    a, b = risk.simulate(m, 333_000), risk.simulate(m, 333_000)
    assert a["p_safe"] == b["p_safe"] and a["p_short"] == b["p_short"]
    r = risk.simulate(m, 333_000, reminded={"Kaveri Hospitals"})
    assert r["p_short"] < a["p_short"]
    assert 0 <= a["p_safe"] <= 1 and a["sims"] == risk.N_SIMS


# ---------------------------------------------------------------- planner, auditor, backup


@pytest.mark.parametrize("book", BOOKS)
def test_auditor_rerun_matches_the_planner(plans, book):
    p = plans[book]
    assert p["audit"]["matches"]
    assert p["search"]["combinations"] == 2 ** p["search"]["moves_considered"]


def test_planner_takes_the_easiest_plan_among_the_safest(plans):
    for book in ("demo_agency", "demo_cafe"):
        p = plans[book]
        chosen = [m for m in p["moves"] if m["suggested"] and m["kind"] != "reserve"]
        cost = sum(m["effort"] for m in chosen)
        mine = p["odds"]["suggested"]["p_safe"]
        tested = [t for t in p["search"]["plans"] if t["reaches_safety"]]
        best = max(t["p_safe"] for t in tested)
        if best >= ap.TARGET_ODDS:
            assert mine >= ap.TARGET_ODDS and all(t["cost"] >= cost for t in tested if t["p_safe"] >= ap.TARGET_ODDS)
        else:  # nobody reaches the target: within tolerance of the best odds, the easiest plan
            assert mine >= best - ap.ODDS_TOLERANCE
            assert all(t["cost"] >= cost for t in tested if t["p_safe"] >= best - ap.ODDS_TOLERANCE)


def test_safe_business_gets_no_moves_and_spendable_cash(plans):
    p = plans["demo"]
    assert not [m for m in p["moves"] if m["suggested"] and m["kind"] != "reserve"]
    b = p["baseline"]
    assert b["spendable_today"] == pytest.approx(min(b["lowest"] - p["safety"], p["today"] - p["safety"]))
    assert b["days_to_trouble"] is None


def test_financing_backup_only_when_the_plan_leaves_risk(plans, tables):
    a = plans["demo_agency"]
    bk = next(m for m in a["moves"] if m["kind"] == "borrow")
    assert a["odds"]["suggested"]["p_safe"] < ap.TARGET_ODDS <= bk["odds_with_plan"]
    assert not bk["suggested"] and bk["amount"] % ap.BACKUP_STEP == 0
    assert bk["interest_if_used"] == pytest.approx(bk["amount"] * ap.BACKUP_RATE * 90 / 365, abs=1)
    assert not any(m["kind"] == "borrow" for m in plans["demo"]["moves"])
    t = tables["demo_agency"]
    withb = ap.plan(t["ledger"], t["balances"], t["obligations"], AS_OF, approved={"borrow:standby"})
    assert withb["with_approved"]["lowest"] >= a["baseline"]["lowest"] + bk["amount"] - 1 or withb["with_approved"]["lowest_date"] == "2026-09-30"


# ---------------------------------------------------------------- can I afford it?


@pytest.mark.parametrize("book,amount,when,verdict", [
    ("demo", 300_000, "2026-10-15", "yes"),
    ("demo", 600_000, "2026-10-15", "yes_if"),
    ("demo", 1_200_000, "2026-10-15", "not_now"),
    ("demo_agency", 100_000, None, "risky"),
])
def test_afford_verdicts(tables, book, amount, when, verdict):
    t = tables[book]
    r = ap.afford(t["ledger"], t["balances"], t["obligations"], AS_OF, amount, when, "Machine")
    assert r["verdict"] == verdict
    assert r["without_moves"]["lowest"] == pytest.approx(r["before"]["lowest"] - amount, abs=1) or r["without_moves"]["lowest_date"] < r["date"]


def test_afford_earliest_safe_day_is_checked_by_a_real_forecast(tables):
    t = tables["demo"]
    r = ap.afford(t["ledger"], t["balances"], t["obligations"], AS_OF, 500_000, "2026-10-01", "Machine")
    day = r["earliest_safe_date_without_moves"]
    assert day is not None
    obl, _ = ap.at_risk(t["obligations"], AS_OF)
    f = ap._forecast(t["ledger"], t["balances"], obl, AS_OF, 90, r["safety"], [{"date": day, "amount": -500_000, "label": "x"}])
    assert f["lowest_balance"] >= r["safety"]
    if pd.Timestamp(day) > AS_OF + pd.Timedelta(days=1):
        before = str((pd.Timestamp(day) - pd.Timedelta(days=1)).date())
        g = ap._forecast(t["ledger"], t["balances"], obl, AS_OF, 90, r["safety"], [{"date": before, "amount": -500_000, "label": "x"}])
        assert g["lowest_balance"] < r["safety"]


def test_afford_api_and_tool(app, tmp_path, tables):
    app.post("/api/source", json={"source": "demo"})
    r = app.post("/api/autopilot/afford", json={"amount": 300000, "date": "2026-10-15", "label": "Packing machine"}).json()
    assert r["verdict"] == "yes" and r["evidence"]["title"]
    assert app.post("/api/autopilot/afford", json={"amount": -5}).status_code == 400
    assert app.post("/api/autopilot/afford", json={"amount": 5, "date": "someday"}).status_code == 400
    t = tables["demo"]
    ctx = ToolContext(t["ledger"], t["obligations"], t["balances"], AS_OF, tmp_path / "x.db", "demo", "Demo")
    ok, out = run_tool(ctx, "plan_purchase", {"amount": 1_200_000, "date": "2026-10-15"})
    assert ok and out["verdict"] == "not_now" and out["verdict_meaning"]
    ok, out = run_tool(ctx, "plan_purchase", {"amount": 0})
    assert not ok


# ---------------------------------------------------------------- the crew, live


def test_crew_stream_runs_every_agent_in_order(app):
    app.post("/api/source", json={"source": "demo_agency"})
    ev = stream(app, "/api/crew/stream")
    done = [e for e in ev if e.get("type") == "agent" and e["phase"] == "done"]
    assert [e["agent"] for e in done] == ["forecaster", "risk", "collections", "payables", "spending", "tax", "deals", "planner", "financing", "auditor", "strategist"]
    starts = [e for e in ev if e.get("type") == "agent" and e["phase"] == "start"]
    assert len(starts) == len(done)
    final = ev[-1]
    assert final["type"] == "final" and final["data"]["mode"] == "rule-based"
    assert "1 Nov" in final["data"]["brief"] and "90%" in final["data"]["brief"]
    assert "collect:Kaveri Hospitals" in final["data"]["suggested"]
    assert "matches the planner" in done[-2]["text"] and "Turn on AI" in done[-1]["text"]
    assert "Plan B: if Kaveri Hospitals hasn't paid by 10 Oct" in next(e["text"] for e in done if e["agent"] == "planner")


def test_crew_speaks_hindi(app):
    app.post("/api/source", json={"source": "demo_cafe"})
    ev = stream(app, "/api/crew/stream", "hi")
    final = ev[-1]["data"]
    assert any("ऀ" <= ch <= "ॿ" for ch in final["brief"])
    assert all(any("ऀ" <= ch <= "ॿ" for ch in e["name"]) for e in ev if e.get("type") == "agent" and e["phase"] == "done")


def _fake_ai(answer_text, strategist=None):
    """A scripted model: a new question gets a tool call first, then the scripted answer."""
    calls = []

    def create(**kw):
        calls.append(kw)
        msgs = kw["messages"]
        first = msgs[-1]["content"] if isinstance(msgs[-1]["content"], str) else None
        is_strat = "[Strategist]" in str(msgs[0]["content"])
        if first is not None:
            if is_strat and strategist:
                return NS(content=[NS(type="tool_use", id="s", name="test_move", input=strategist["move"])], stop_reason="tool_use")
            return NS(content=[NS(type="tool_use", id="a", name="get_cash_autopilot", input={})], stop_reason="tool_use")
        text = strategist["answer"] if is_strat and strategist else answer_text
        return NS(content=[NS(type="text", text=text)], stop_reason="end_turn")

    return NS(beta=NS(messages=NS(create=create))), calls


def test_crew_brief_by_ai_when_its_figures_check_out(tmp_path, monkeypatch):
    fake, calls = _fake_ai("Cash runs out on 2026-11-01 unless you act. Approve the plan: odds go from 0% to 41%; keep the ₹5,50,000 overdraft ready as a backup.")
    c = _client(tmp_path, monkeypatch, client=fake)
    c.post("/api/source", json={"source": "demo_agency"})
    final = stream(c, "/api/crew/stream")[-1]["data"]
    assert final["mode"] == "ai" and final["brief"].startswith("Cash runs out on 2026-11-01")
    assert any(e for e in calls[0]["tools"] if e["name"] == "plan_purchase")


def test_crew_falls_back_when_the_ai_invents_a_figure(tmp_path, monkeypatch):
    fake, _ = _fake_ai("You will run short by ₹9,99,999 on 2026-11-01.")
    c = _client(tmp_path, monkeypatch, client=fake)
    c.post("/api/source", json={"source": "demo_agency"})
    final = stream(c, "/api/crew/stream")[-1]["data"]
    assert final["mode"] == "rule-based" and "9,99,999" not in final["brief"] and final["warnings"]


# ---------------------------------------------------------------- what changed


def test_what_changed_after_a_customer_pays(app):
    app.post("/api/source", json={"source": "demo_agency"})
    first = app.get("/api/autopilot").json()
    assert first["changes"] == [] and first["headline"].startswith("If nothing changes, cash runs out")
    r = app.post("/api/entries", json={"kind": "payment_in", "amount": 525600, "party": "Kaveri Hospitals"})
    assert r.status_code == 200, r.text
    after = app.get("/api/autopilot").json()
    texts = " ".join(c["text"] for c in after["changes"])
    assert "Kaveri Hospitals paid ₹5.26 L" in texts
    assert "no longer run out" in texts or "now runs out" in texts
    assert after["changes_since"]
    again = app.get("/api/autopilot").json()
    assert again["changes"] == after["changes"]  # the feed stays until the books change again


def test_changes_unit():
    prev = {"today": 1, "lowest": 1, "runs_out": "2026-11-01", "below": "2026-10-20", "spendable": 0, "p_safe": 0.02, "overdue": {"A": 100.0}}
    cur = {"today": 1, "lowest": 1, "runs_out": None, "below": None, "spendable": 50_000, "p_safe": 0.9, "overdue": {"B": 200.0}}
    out = crew.changes(prev, cur)
    tones = [c["tone"] for c in out]
    assert "caution" in tones and tones.count("good") >= 3
    assert crew.changes(None, cur) == []


def test_ai_strategist_tests_its_idea_before_suggesting_it(tmp_path, monkeypatch):
    idea = {"move": {"label": "Ask Zenith Realty for next month's retainer in advance", "flows": [{"date": "2026-10-08", "amount": 210000}, {"date": "2026-11-01", "amount": -210000}]},
            "answer": "Asking Zenith Realty for next month's retainer in advance helps your tightest weeks; I tested it on your forecast."}
    fake, _ = _fake_ai("Cash runs out on 2026-11-01 unless you act.", strategist=idea)
    c = _client(tmp_path, monkeypatch, client=fake)
    c.post("/api/source", json={"source": "demo_agency"})
    ev = stream(c, "/api/crew/stream")
    st = next(e for e in ev if e.get("type") == "agent" and e["phase"] == "done" and e["agent"] == "strategist")
    assert st["text"].startswith("Asking Zenith") and st["ideas"] and st["ideas"][0]["label"].startswith("Ask Zenith")
    assert st["ideas"][0]["change_in_lowest"] >= 0


def test_test_move_measures_an_idea(tables, tmp_path):
    t = tables["demo_agency"]
    ctx = ToolContext(t["ledger"], t["obligations"], t["balances"], AS_OF, tmp_path / "x.db", "demo_agency", "A")
    ok, r = run_tool(ctx, "test_move", {"label": "Sell two old monitors", "flows": [{"date": "2026-10-05", "amount": 100000}]})
    assert ok and r["verdict"] == "helps" and r["change_in_lowest"] == pytest.approx(100000, abs=1)
    ok, r = run_tool(ctx, "test_move", {"label": "x", "flows": [{"date": "2027-06-01", "amount": 5}]})
    assert not ok
    ok, r = run_tool(ctx, "test_move", {"label": "x", "flows": []})
    assert not ok


def test_deals_agent_offers_an_early_payment_discount(tables):
    """Only helps when the tightest day falls between "paid early" and the invoice's due date — here a big payment on 12 Oct
    and money arriving on 28 Oct make mid-October the tight spot."""
    t = tables["demo"]
    dip = [{"date": pd.Timestamp("2026-10-12"), "amount": -1_200_000, "label": "Machine", "source": "x", "category": "Machinery"},
           {"date": pd.Timestamp("2026-10-28"), "amount": 1_500_000, "label": "Loan", "source": "y", "category": "Loan Received"}]
    p = ap.plan(t["ledger"], t["balances"], t["obligations"], AS_OF, commitments=dip)
    deals = [m for m in p["moves"] if m["kind"] == "discount"]
    assert deals and all(m["impact"] > 0 for m in deals)
    assert any(m["suggested"] for m in deals)
    plain = ap.plan(t["ledger"], t["balances"], t["obligations"], AS_OF)
    assert not any(m["kind"] == "discount" for m in plain["moves"])  # no point paying a discount when the tight day is after the due dates
    m = deals[0]
    assert m["amount"] == pytest.approx(m["invoice"] * (1 - ap.DISCOUNT), abs=1) and m["cost"] == pytest.approx(m["invoice"] * ap.DISCOUNT, abs=1)
    assert m["party"] != "Metro Foods Pvt Ltd"  # never to a customer who is already late
    assert p["audit"]["matches"]


def test_plan_b_for_moves_that_depend_on_someone_else(plans):
    pb = plans["demo_agency"]["plan_b"]
    assert [x["if_fails"] for x in pb] == ["collect:Kaveri Hospitals"]
    assert pb[0]["checkpoint"] == "2026-10-10" and "collect:Kaveri Hospitals" not in pb[0]["then"]
    assert pb[0]["backup"] and pb[0]["backup"]["p_safe"] >= ap.TARGET_ODDS
    assert plans["demo"]["plan_b"] == []  # nothing uncertain in a plan with no moves


# ---------------------------------------------------------------- fast-forward: the agents keep watching


def ff(c, days, scenario):
    return stream(c, "/api/demo/fast-forward/stream") if False else _ff(c, days, scenario)


def _ff(c, days, scenario):
    events = []
    with c.stream("POST", "/api/demo/fast-forward/stream", json={"days": days, "scenario": scenario}) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_fast_forward_missed_checkpoint_learns_and_offers_plan_b(app):
    app.post("/api/source", json={"source": "demo_agency"})
    app.post("/api/autopilot/approve-suggested")
    ev = _ff(app, 12, "defaults")
    days = [e for e in ev if e["type"] == "day"]
    assert [d["date"] for d in days][0] == "2026-10-01" and days[-1]["date"] == "2026-10-12"
    acts = [e for e in ev if e["type"] == "activity"]
    texts = " ".join(a["text"] for a in acts)
    assert "hasn't paid ₹5.26 L by the 10 Oct checkpoint" in texts
    assert "Learned: Kaveri Hospitals is less likely to pay after a reminder than I assumed — 60% → 48%" in texts
    assert any(a.get("action") == {"type": "plan_b"} for a in acts)
    v = app.get("/api/autopilot").json()
    assert v["clock"] == {"date": "2026-10-12", "days_moved": 12} and v["learned"]["Kaveri Hospitals"] == pytest.approx(0.48, abs=0.001)
    assert all(not w["move_id"].startswith("collect:Kaveri") for w in v["watching"])
    led = app.get("/api/entries").json()
    assert led["today"] == "2026-10-12"
    r = app.post("/api/autopilot/plan-b").json()
    assert "borrow:standby" in r["approved"]
    app.post("/api/demo/reset")
    assert app.get("/api/autopilot").json()["clock"]["days_moved"] == 0


def test_fast_forward_good_news_and_overdraft_only_when_needed(app):
    app.post("/api/source", json={"source": "demo_agency"})
    app.post("/api/autopilot/approve-suggested")
    ev = _ff(app, 10, "pays")
    texts = " ".join(e["text"] for e in ev if e["type"] == "activity")
    assert "Kaveri Hospitals paid ₹5.26 L — 5 days after the reminder" in texts and "60% → 68%" in texts
    assert not any(i["kind"] == "overdraft" for e in ev if e["type"] == "day" for i in e["items"])


def test_fast_forward_books_stay_consistent(tables):
    from finpilot.data import khata
    from finpilot.engine import live
    from finpilot.engine.cash import cash_position

    t = tables["demo_cafe"]
    tab = khata.Tables(t["ledger"].copy(), t["obligations"].copy(), t["balances"].copy())
    plan = live.Plan(safety=679_000, overdraft_limit=200_000)
    new, log = live.advance(tab, AS_OF, 14, "usual", plan, seed=3)
    end = AS_OF + pd.Timedelta(days=14)
    assert cash_position(new.ledger, new.balances, end)["cash_balance"] == pytest.approx(log[-1]["balance"], abs=1)
    assert (new.ledger["reference"] == "Simulated").sum() > 0 and len(new.ledger) > len(t["ledger"])
    paid = new.obligations[(new.obligations["status"] == "paid") & (pd.to_datetime(new.obligations["paid_date"]) > AS_OF)]
    assert len(paid) > 0 and (pd.to_datetime(paid["paid_date"]) <= end).all()


def test_fast_forward_only_on_demos(app):
    app.post("/api/source", json={"source": "demo"})
    assert app.post("/api/demo/fast-forward/stream", json={"days": 99}).status_code == 400
    assert app.post("/api/demo/fast-forward/stream", json={"days": 3, "scenario": "nope"}).status_code == 400
