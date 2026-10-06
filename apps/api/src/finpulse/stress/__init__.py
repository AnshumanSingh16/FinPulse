"""Financial stress testing: deterministic what-if projections. No LLM is involved."""

from finpulse.stress.engine import ENGINE_VERSION, StressTestRequest, run_stress_test
from finpulse.stress.presets import PRESETS
from finpulse.stress.shocks import SHOCKS

__all__ = ["ENGINE_VERSION", "PRESETS", "SHOCKS", "StressTestRequest", "run_stress_test"]
