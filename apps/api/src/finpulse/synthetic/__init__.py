"""Deterministic synthetic financial data. Pure: no I/O, no clock, no LLM."""

from finpulse.synthetic.engine import GENERATOR_VERSION, generate
from finpulse.synthetic.model import Dataset
from finpulse.synthetic.scenarios import PRIMARY_DEMO, SCENARIOS, get_scenario

__all__ = ["GENERATOR_VERSION", "PRIMARY_DEMO", "SCENARIOS", "Dataset", "generate", "get_scenario"]
