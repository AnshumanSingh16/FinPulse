"""Business profile, operational signals, and deterministic scenarios."""

import pytest
from fastapi.testclient import TestClient

from finpilot.api.server import create_app
from finpilot.data import books
from finpilot.engine import business_intelligence as bi


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    return TestClient(create_app(tmp_path / "api.db", static_dir=None))


def test_profile_and_records_api(api):
    r = api.post("/api/business-profile", json={"name": "Studio", "category": "service", "type": "photography studio", "model": "bookings"})
    assert r.status_code == 200 and r.json()["profile"]["category"] == "service"
    r = api.post("/api/intelligence/services", json={"name": "Portrait session", "price": 10000, "delivery_cost": 3000, "monthly_capacity": 20, "monthly_bookings": 5})
    assert r.status_code == 200
    assert any("25.0%" in x["reason"] for x in r.json()["opportunities"])
    result = api.post("/api/intelligence/simulate", json={"kind": "service_price", "name": "Portrait session", "change_pct": 10})
    assert result.status_code == 200
    assert result.json()["scenario"]["monthly_revenue"] == 55000

def test_inventory_signal_and_scenario(tmp_path):
    db = tmp_path / "business.db"
    books.set_settings(db, "upload", {"business_category": "inventory", "business_name": "Boutique"})
    with books.connect(db) as con:
        con.execute("INSERT INTO inventory_items(book,name,stock_qty,unit_cost,selling_price,monthly_units_sold,lead_time_days) VALUES(?,?,?,?,?,?,?)", ("upload", "Linen shirt", 4, 500, 1000, 8, 20))
    signal = next(x for x in bi.opportunities(db, "upload") if x["key"].startswith("stock:"))
    assert "4 units" in signal["reason"]
    result = bi.simulate(db, "upload", {"kind": "inventory_discount", "name": "Linen shirt", "change_pct": -10})
    assert result["baseline"]["monthly_revenue"] == 8000
    assert result["scenario"]["monthly_revenue"] == 7200
    assert "no demand response" in result["assumptions"][0]


def test_service_utilization_and_price_scenario(tmp_path):
    db = tmp_path / "business.db"
    with books.connect(db) as con:
        con.execute("INSERT INTO service_offerings(book,name,price,delivery_cost,monthly_capacity,monthly_bookings) VALUES(?,?,?,?,?,?)", ("upload", "Portrait session", 10000, 3000, 20, 5))
    signal = next(x for x in bi.opportunities(db, "upload") if x["key"].startswith("utilization:"))
    assert "25.0%" in signal["reason"]
    result = bi.simulate(db, "upload", {"kind": "service_price", "name": "Portrait session", "change_pct": 10})
    assert result["baseline"]["monthly_revenue"] == 50000
    assert result["change"]["monthly_contribution"] == 5000


def test_missing_operational_records_are_not_guessed(tmp_path):
    db = tmp_path / "business.db"
    try:
        bi.simulate(db, "upload", {"kind": "inventory_discount", "name": "unknown", "change_pct": -10})
        assert False, "Expected missing product data to stop the simulation"
    except ValueError as e:
        assert "product that exists" in str(e)


def test_each_demo_gets_its_own_seed_and_reset_restores_it(tmp_path):
    db = tmp_path / "seeded.db"
    assert bi.profile(db, "demo")["category"] == "inventory"
    assert len(bi.inventory(db, "demo")) == 4
    assert bi.profile(db, "demo_agency")["category"] == "service"
    assert len(bi.services(db, "demo_agency")) == 4
    assert bi.profile(db, "demo_cafe")["category"] == "hybrid"
    assert len(bi.inventory(db, "demo_cafe")) == 3 and len(bi.services(db, "demo_cafe")) == 2
    books.reset_book(db, "demo_cafe")
    assert len(bi.inventory(db, "demo_cafe")) == 3 and len(bi.services(db, "demo_cafe")) == 2
