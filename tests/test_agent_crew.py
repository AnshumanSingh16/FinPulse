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


def test_planner_takes_the_easiest_plan_that_reaches_the_target(plans):
    p = plans["demo_cafe"]
    chosen = [m for m in p["moves"] if m["suggested"] and m["kind"] != "reserve"]
    cost = sum(m["effort"] for m in chosen)
    assert p["odds"]["suggested"]["p_safe"] >= ap.TARGET_ODDS
    for alt in p["search"]["plans"]:
        if alt["reaches_safety"] and alt["p_safe"] >= ap.TARGET_ODDS:
            assert alt["cost"] >= cost


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
    assert not any(m["kind"] == "borrow" for m in plans["demo"]["moves"] + plans["demo_cafe"]["moves"])
    t = tables["demo_agency"]
    withb = ap.plan(t["ledger"], t["balances"], t["obligations"], AS_OF, approved={"borrow:standby"})
    assert withb["with_approved"]["lowest"] >= a["baseline"]["lowest"] + bk["amount"] - 1 or withb["with_approved"]["lowest_date"] == "2026-09-30"


# ---------------------------------------------------------------- can I afford it?


@pytest.mark.parametrize("book,amount,when,verdict", [
    ("demo", 600_000, "2026-10-15", "yes"),
    ("demo", 1_200_000, "2026-10-15", "risky"),
    ("demo_agency", 100_000, None, "not_now"),
])
def test_afford_verdicts(tables, book, amount, when, verdict):
    t = tables[book]
    r = ap.afford(t["ledger"], t["balances"], t["obligations"], AS_OF, amount, when, "Machine")
    assert r["verdict"] == verdict
    assert r["without_moves"]["lowest"] == pytest.approx(r["before"]["lowest"] - amount, abs=1) or r["without_moves"]["lowest_date"] < r["date"]


def test_afford_earliest_safe_day_is_checked_by_a_real_forecast(tables):
    t = tables["demo"]
    r = ap.afford(t["ledger"], t["balances"], t["obligations"], AS_OF, 850_000, "2026-10-01", "Machine")
    day = r["earliest_safe_date_without_moves"]
    assert day is not None
    obl, _ = ap.at_risk(t["obligations"], AS_OF)
    f = ap._forecast(t["ledger"], t["balances"], obl, AS_OF, 90, r["safety"], [{"date": day, "amount": -850_000, "label": "x"}])
    assert f["lowest_balance"] >= r["safety"]
    if pd.Timestamp(day) > AS_OF + pd.Timedelta(days=1):
        before = str((pd.Timestamp(day) - pd.Timedelta(days=1)).date())
        g = ap._forecast(t["ledger"], t["balances"], obl, AS_OF, 90, r["safety"], [{"date": before, "amount": -850_000, "label": "x"}])
        assert g["lowest_balance"] < r["safety"]


def test_afford_api_and_tool(app, tmp_path, tables):
    app.post("/api/source", json={"source": "demo"})
    r = app.post("/api/autopilot/afford", json={"amount": 600000, "date": "2026-10-15", "label": "Packing machine"}).json()
    assert r["verdict"] == "yes" and r["evidence"]["title"]
    assert app.post("/api/autopilot/afford", json={"amount": -5}).status_code == 400
    assert app.post("/api/autopilot/afford", json={"amount": 5, "date": "someday"}).status_code == 400
    t = tables["demo"]
    ctx = ToolContext(t["ledger"], t["obligations"], t["balances"], AS_OF, tmp_path / "x.db", "demo", "Demo")
    ok, out = run_tool(ctx, "plan_purchase", {"amount": 1_200_000, "date": "2026-10-15"})
    assert ok and out["verdict"] == "risky" and out["verdict_meaning"]
    ok, out = run_tool(ctx, "plan_purchase", {"amount": 0})
    assert not ok


# ---------------------------------------------------------------- the crew, live


def test_crew_stream_runs_every_agent_in_order(app):
    app.post("/api/source", json={"source": "demo_agency"})
    ev = stream(app, "/api/crew/stream")
    done = [e for e in ev if e.get("type") == "agent" and e["phase"] == "done"]
    assert [e["agent"] for e in done] == ["forecaster", "risk", "collections", "payables", "spending", "tax", "planner", "financing", "auditor"]
    starts = [e for e in ev if e.get("type") == "agent" and e["phase"] == "start"]
    assert len(starts) == len(done)
    final = ev[-1]
    assert final["type"] == "final" and final["data"]["mode"] == "rule-based"
    assert "1 Nov" in final["data"]["brief"] and "91%" in final["data"]["brief"]
    assert "collect:Kaveri Hospitals" in final["data"]["suggested"]
    assert "matches the planner" in done[-1]["text"]


def test_crew_speaks_hindi(app):
    app.post("/api/source", json={"source": "demo_cafe"})
    ev = stream(app, "/api/crew/stream", "hi")
    final = ev[-1]["data"]
    assert any("ऀ" <= ch <= "ॿ" for ch in final["brief"])
    assert all(any("ऀ" <= ch <= "ॿ" for ch in e["name"]) for e in ev if e.get("type") == "agent" and e["phase"] == "done")


def _fake_ai(answer_text):
    calls = []

    def create(**kw):
        calls.append(kw)
        if len(calls) == 1:
            return NS(content=[NS(type="tool_use", id="a", name="get_cash_autopilot", input={})], stop_reason="tool_use")
        return NS(content=[NS(type="text", text=answer_text)], stop_reason="end_turn")

    return NS(beta=NS(messages=NS(create=create))), calls


def test_crew_brief_by_ai_when_its_figures_check_out(tmp_path, monkeypatch):
    fake, calls = _fake_ai("Cash runs out on 2026-11-01 unless you act. Approve the plan: odds go from 2% to 14%; keep the ₹7,50,000 overdraft ready as a backup.")
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
