from pathlib import Path

from finpulse.scoring import load_model
from finpulse.scoring.methodology import generated_block, render_factor_tables

DOC = Path(__file__).resolve().parents[4] / "docs" / "FINANCIAL_PASSPORT.md"


def test_published_methodology_matches_the_configuration() -> None:
    """If this fails, regenerate: uv run python -m finpulse.scoring.methodology <doc>."""
    assert generated_block(DOC.read_text(encoding="utf-8")) == render_factor_tables(load_model())


def test_published_methodology_disclaims_being_a_credit_score() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "not a credit score" in text and "cibil" in text and "synthetic data" in text
