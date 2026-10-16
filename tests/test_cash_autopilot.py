"""The cash autopilot: 90-day look-ahead, late customers not counted, every move's effect measured by re-running the forecast,
the owner's decisions, and the three demo businesses (healthy manufacturer, agency running out, café dipping below safety)."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from finpilot.agent import offline
from finpilot.api.dataset import _demo_tables
from finpilot.api.server import create_app
from finpilot.engine import autopilot as ap

AS_OF = pd.Timestamp("2026-09-30")


@pytest.fixture(scope="module")
def plans():
    out = {}
    for book in ("demo", "demo_agency", "demo_cafe"):
        t = _demo_tables(book)
        out[book] = (t, ap.plan(t["ledger"], t["balances"], t["obligations"], AS_OF))
    return out


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    monkeypatch.setenv("FINPILOT_ENV_FILE", str(tmp_path / "test.env"))
    from finpilot.api import dataset

    monkeypatch.setattr(dataset, "today", lambda: AS_OF)
    c = TestClient(create_app(tmp_path / "t.db", static_dir=None))
    c.db = tmp_path / "t.db"
    return c


def use(c, book):
    assert c.post("/api/source", json={"source": book}).status_code == 200


# ---------------------------------------------------------------- engine


def test_three_demo_stories(plans):
    _, m = plans["demo"]
    assert m["baseline"]["safe"] and m["baseline"]["runs_out"] is None

    _, a = plans["demo_agency"]
    assert a["baseline"]["runs_out"] == "2026-11-01"
    assert not a["baseline"]["safe"] and a["with_suggested"]["safe"]

    _, c = plans["demo_cafe"]
    assert c["baseline"]["runs_out"] is None and not c["baseline"]["safe"]
    assert c["baseline"]["below_safety_from"].startswith("2026-12")
    assert c["with_suggested"]["safe"]


def test_late_customer_invoices_are_not_counted(plans):
    t, a = plans["demo_agency"]
    assert [r["party"] for r in a["at_risk"]] == ["Kaveri Hospitals"]
    obl, risky = ap.at_risk(t["obligations"], AS_OF)
    marked = obl[obl["status"] == "at_risk"]
    assert set(marked["counterparty"]) == {"Kaveri Hospitals"}
    assert (pd.to_datetime(marked["due_date"]) >= AS_OF).all()
    assert risky[0]["amount"] == pytest.approx(marked["amount"].sum())


def test_every_impact_equals_a_rerun_of_the_forecast(plans):
    t, a = plans["demo_agency"]
    obl, _ = ap.at_risk(t["obligations"], AS_OF)
    s = ap.Settings()
    for m in a["moves"]:
        if m["kind"] == "reserve":
            assert m["impact"] == 0
            continue
        extra, _ = ap.apply([m], obl, AS_OF, s)
        f = ap._forecast(t["ledger"], t["balances"], obl, AS_OF, s.horizon_days, a["safety"], extra)
        assert m["impact"] == pytest.approx(f["lowest_balance"] - a["baseline"]["lowest"], abs=1)


def test_suggested_plan_matches_its_own_forecast(plans):
    t, a = plans["demo_cafe"]
    obl, _ = ap.at_risk(t["obligations"], AS_OF)
    chosen = [m for m in a["moves"] if m["suggested"] and m["kind"] != "reserve"]
    extra, _ = ap.apply(chosen, obl, AS_OF, ap.Settings())
    f = ap._forecast(t["ledger"], t["balances"], obl, AS_OF, 90, a["safety"], extra)
    assert f["lowest_balance"] == pytest.approx(a["with_suggested"]["lowest"], abs=1)
    assert a["moves"][0]["suggested"]  # suggested moves come first


def test_default_safety_is_half_the_buffer(plans):
    t, a = plans["demo"]
    assert a["safety"] == ap.default_safety(t["ledger"], AS_OF)
    assert a["safety"] % 1000 == 0


def test_defer_moves_only_that_payment(tiny):
    """Moving a bill must not change anything else in the forecast — no shifted run-rate start."""
    obl = tiny["obligations"]
    as_of = pd.Timestamp("2026-04-20")
    s = ap.Settings()
    base = ap._forecast(tiny["ledger"], tiny["balances"], obl, as_of, 60, 0)
    m = {"id": "defer:BILL-2", "kind": "defer", "amount": 15_000.0, "items": ["BILL-2"], "from_date": "2026-04-25", "to_date": "2026-05-16"}
    extra, _ = ap.apply([m], obl, as_of, s)
    f = ap._forecast(tiny["ledger"], tiny["balances"], obl, as_of, 60, 0, extra)
    by_day = {d["date"]: d["balance"] for d in base["daily"]}
    for d in f["daily"]:
        diff = d["balance"] - by_day[d["date"]]
        expected = 15_000 if "2026-04-25" <= d["date"] < "2026-05-16" else 0
        assert diff == pytest.approx(expected, abs=1), d["date"]


def test_weekly_adds_up_and_groups_paused_spend(plans):
    t, a = plans["demo_agency"]
    obl, _ = ap.at_risk(t["obligations"], AS_OF)
    pause = next(m for m in a["moves"] if m["id"] == "pause:Owner Drawings")
    extra, _ = ap.apply([pause], obl, AS_OF, ap.Settings())
    f = ap._forecast(t["ledger"], t["balances"], obl, AS_OF, 91, a["safety"], extra)
    weeks = ap.weekly(f)
    assert len(weeks) == 13
    opening = f["starting_cash"]
    for w in weeks:
        assert w["closing"] == pytest.approx(opening + w["money_in"] - w["money_out"], abs=2)
        opening = w["closing"]
        assert sum(1 for i in w["items"] if i["source"] == "pause:Owner Drawings") <= 1


def test_titles_use_indian_number_format(plans):
    _, a = plans["demo_agency"]
    collect = next(m for m in a["moves"] if m["kind"] == "collect")
    assert "₹5,25,600" in collect["title"]


# ---------------------------------------------------------------- API


def test_api_plan_approve_undo_dismiss(client):
    use(client, "demo_agency")
    p = client.get("/api/autopilot").json()
    assert p["status"] == "ok" and p["business_type"] == "services" and len(p["weekly"]) == 13
    assert p["plan_basis"] == "suggested"

    r = client.post("/api/autopilot/moves/collect:Kaveri Hospitals", json={"decision": "approve"}).json()
    assert r["next"] == "whatsapp" and "Kaveri" in r["text"] and r["whatsapp"].startswith("https://wa.me/")
    p = client.get("/api/autopilot").json()
    assert p["plan_basis"] == "approved"
    assert p["with_approved"]["lowest"] > p["baseline"]["lowest"]
    assert {m["id"]: m["state"] for m in p["moves"]}["collect:Kaveri Hospitals"] == "approved"
    assert any(i["kind"] == "scenario" for w in p["weekly"] for i in w["items"])

    client.post("/api/autopilot/moves/collect:Kaveri Hospitals", json={"decision": "undo"})
    client.post("/api/autopilot/moves/pause:Marketing", json={"decision": "dismiss"})
    p = client.get("/api/autopilot").json()
    ids = {m["id"]: m["state"] for m in p["moves"]}
    assert ids["collect:Kaveri Hospitals"] == "open" and "pause:Marketing" not in ids

    assert client.post("/api/autopilot/moves/collect:Nobody", json={"decision": "approve"}).status_code == 404
    assert client.post("/api/autopilot/moves/pause:Owner Drawings", json={"decision": "pay"}).status_code == 400


def test_api_approve_suggested_makes_agency_safe(client):
    use(client, "demo_agency")
    ids = client.post("/api/autopilot/approve-suggested").json()["approved"]
    assert "collect:Kaveri Hospitals" in ids
    p = client.get("/api/autopilot").json()
    assert p["with_approved"]["safe"] and p["with_approved"]["runs_out"] is None


def test_api_safety_setting(client):
    use(client, "demo")
    p = client.get("/api/autopilot").json()
    assert p["safety"] == p["default_safety"]
    client.post("/api/autopilot/safety", json={"amount": 13_00_000})
    p = client.get("/api/autopilot").json()
    assert p["safety"] == 13_00_000 and not p["baseline"]["safe"]
    assert client.post("/api/autopilot/safety", json={"amount": -5}).status_code == 400
    client.post("/api/autopilot/safety", json={"amount": None})
    assert client.get("/api/autopilot").json()["safety"] == p["default_safety"]


def test_api_demo_switch_keeps_books_apart(client):
    use(client, "demo_cafe")
    s = client.get("/api/state").json()
    assert s["source"] == "demo_cafe" and s["is_demo"] and s["business_type"] == "restaurant"
    assert {d["key"] for d in s["demos"]} == {"demo", "demo_agency", "demo_cafe"}
    client.post("/api/autopilot/moves/pause:Owner Drawings", json={"decision": "approve"})
    use(client, "demo_agency")
    states = {m["id"]: m["state"] for m in client.get("/api/autopilot").json()["moves"]}
    assert states.get("pause:Owner Drawings") == "open"
    assert client.post("/api/source", json={"source": "nonsense"}).status_code == 400


def test_api_done_on_defer_moves_the_bill(client, monkeypatch):
    """When the supplier agrees, the bill's due date really changes in the books."""
    import finpilot.api.server as srv
    from finpilot.api import dataset

    use(client, "demo")
    move = {"id": "defer:SCH-0057", "kind": "defer", "party": "Hadapsar Industrial Estate", "amount": 1.0, "items": ["SCH-0057"],
            "from_date": "2026-10-05", "to_date": "2026-10-26", "approved": False, "suggested": False, "impact": 0, "agent": "payables"}
    real = srv.ap.plan

    def with_defer(*a, **k):
        p = real(*a, **k)
        if p["status"] == "ok":
            p["moves"].append(dict(move))
        return p

    monkeypatch.setattr(srv.ap, "plan", with_defer)
    r = client.post("/api/autopilot/moves/defer:SCH-0057", json={"decision": "approve"}).json()
    assert r["next"] == "whatsapp" and "26 Oct instead of 05 Oct" in r["text"]
    client.post("/api/autopilot/moves/defer:SCH-0057", json={"decision": "done"})
    d = dataset.load(client.db, "demo")
    row = d.obligations[d.obligations["item_id"] == "SCH-0057"].iloc[0]
    assert pd.Timestamp(row["due_date"]) == pd.Timestamp("2026-10-26")


def test_business_type_setting(client):
    client.post("/api/source", json={"source": "demo"})
    s = client.get("/api/state").json()
    assert s["business_type"] == "manufacturing" and len(s["types"]) == 8
    assert s["type_info"]["customers"] == "customers"


# ---------------------------------------------------------------- offline answer


def test_offline_answers_run_short_with_the_autopilot(client):
    use(client, "demo_agency")
    r = client.post("/api/ask", json={"question": "Will I run short of cash?"}).json()
    assert "run out of cash on 1 Nov 2026" in r["answer"]
    assert "Kaveri Hospitals" in r["answer"] and "above your safety level" in r["answer"]
    assert [k for k, _ in offline.plan("Will I run short of cash?")] == ["autopilot"]
