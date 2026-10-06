"""FinPulse Financial Passport: a deterministic, documented, multidimensional financial-health
profile built from the analytics engine's metrics. A prototype — not a credit score."""

from finpulse.scoring.config import ScoringModel, load_model
from finpulse.scoring.engine import explain_change, score_passport
from finpulse.scoring.history import passport_history, with_monthly_change

__all__ = [
    "ScoringModel",
    "explain_change",
    "load_model",
    "passport_history",
    "score_passport",
    "with_monthly_change",
]
