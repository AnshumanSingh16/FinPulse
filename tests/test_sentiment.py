"""Local customer feedback sentiment model and API."""

import io

import pytest
from fastapi.testclient import TestClient

from finpilot.api.server import create_app
from finpilot.data import books
from finpilot.engine import sentiment


def test_naive_bayes_predicts_basic_sentiment():
    assert sentiment.predict("Excellent quality and fast delivery")["sentiment"] == "positive"
    assert sentiment.predict("Late delivery and poor quality")["sentiment"] == "negative"
    assert sentiment.predict("Please send updated price list")["sentiment"] == "neutral"


def test_demo_businesses_have_feedback_samples(tmp_path):
    db = tmp_path / "feedback.db"
    for book in ("demo", "demo_agency", "demo_cafe"):
        result = sentiment.analysis(db, book)
        assert result["total"] == 9
        assert result["counts"]["positive"] >= 2
        assert result["counts"]["negative"] >= 2
        assert result["counts"]["neutral"] >= 2
        assert all(x["source"] == "fictional demo feedback" for x in result["records"])
    books.reset_book(db, "demo_cafe")
    assert sentiment.analysis(db, "demo_cafe")["total"] == 9


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("FINPILOT_AI", "off")
    return TestClient(create_app(tmp_path / "api.db", static_dir=None))


def test_feedback_api_and_csv_import(api):
    response = api.post("/api/intelligence/feedback", json={"customer": "Studio client", "text": "The campaign looks excellent and the team was helpful."})
    assert response.status_code == 200
    assert response.json()["feedback"]["records"][0]["sentiment"] == "positive"
    uploaded = api.post("/api/intelligence/import", data={"kind": "feedback"}, files={"file": ("reviews.csv", io.BytesIO(b"customer,comment\nClient A,The service was slow and disappointing.\n"), "text/csv")})
    assert uploaded.status_code == 200
    assert uploaded.json()["imported"] == 1
    assert any(x["sentiment"] == "negative" for x in uploaded.json()["feedback"]["records"])
