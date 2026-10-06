"""FinPulse Early Warning Engine: deterministic, configurable rules that detect deterioration in
financial health from historical comparisons. No LLM decides whether a warning exists."""

from finpulse.early_warning.config import EarlyWarningConfig, load_config
from finpulse.early_warning.engine import ENGINE_VERSION, Evaluator, detect_warnings, risk_summary
from finpulse.early_warning.rules import RULES

__all__ = [
    "ENGINE_VERSION",
    "RULES",
    "EarlyWarningConfig",
    "Evaluator",
    "detect_warnings",
    "load_config",
    "risk_summary",
]
