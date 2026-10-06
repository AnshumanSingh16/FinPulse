"""Re-export: the adapter lives in the package so the CLI can investigate synthetic scenarios."""

from finpulse.synthetic.adapter import to_financial_data

__all__ = ["to_financial_data"]
