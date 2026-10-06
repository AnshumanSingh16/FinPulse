"""Deterministic financial analytics. Pure: no I/O, no clock, no LLM.

Reads a ``FinancialData`` snapshot and returns typed metrics with their period, sources and
confidence. Python is the source of truth for every number FinPulse shows.
"""

from finpulse.analytics.engine import ENGINE_VERSION, compute_report, default_as_of
from finpulse.analytics.inputs import FinancialData
from finpulse.analytics.registry import CATALOGUE

__all__ = ["CATALOGUE", "ENGINE_VERSION", "FinancialData", "compute_report", "default_as_of"]
