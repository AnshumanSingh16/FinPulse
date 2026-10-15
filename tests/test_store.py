import pandas as pd
import pytest

from finpilot.data import store


def test_dataset_round_trip(tmp_path, tiny):
    db = tmp_path / "f.db"
    store.save_dataset(db, "Shop", {"ledger": tiny["ledger"], "obligations": tiny["obligations"], "balances": None}, "2026-04-30")
    got = store.load_dataset(db)
    assert got["name"] == "Shop" and got["as_of"] == "2026-04-30"
    assert got["balances"] is None
    pd.testing.assert_series_equal(got["ledger"]["amount"], tiny["ledger"]["amount"], check_names=False)
    assert str(got["ledger"]["date"].iloc[0].date()) == "2026-03-02"
    store.clear_dataset(db)
    assert store.load_dataset(db) is None


def test_actions_need_a_human_decision_and_decide_once(tmp_path):
    db = tmp_path / "f.db"
    a = store.propose_action(db, "Send payment reminder", {"to": "Metro Foods", "amount": 100})
    assert store.approvals(db)[0]["status"] == "pending"
    store.decide_action(db, a, "approved")
    assert store.approvals(db)[0]["status"] == "approved"
    with pytest.raises(ValueError):
        store.decide_action(db, a, "rejected")
    with pytest.raises(ValueError):
        store.decide_action(db, a, "maybe")
    kinds = [x["kind"] for x in store.activity(db)]
    assert "action_proposed" in kinds and "action_approved" in kinds
