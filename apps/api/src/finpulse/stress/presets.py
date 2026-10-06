"""The named scenarios. Each is just a list of shocks with chosen parameters, so new presets
(including combinations) need no code beyond an entry here."""

from __future__ import annotations

from typing import Any

PRESETS: dict[str, tuple[str, list[dict[str, Any]]]] = {
    "revenue_down_10": (
        "Revenue decreases by 10%",
        [{"type": "revenue_decline", "decline_pct": "0.10"}],
    ),
    "revenue_down_20": (
        "Revenue decreases by 20%",
        [{"type": "revenue_decline", "decline_pct": "0.20"}],
    ),
    "revenue_down_30": (
        "Revenue decreases by 30%",
        [{"type": "revenue_decline", "decline_pct": "0.30"}],
    ),
    "major_customer_stops_paying_30_days": (
        "Major customer stops paying for 30 days",
        [{"type": "customer_payment_stop", "days": 30}],
    ),
    "major_customer_stops_paying_60_days": (
        "Major customer stops paying for 60 days",
        [{"type": "customer_payment_stop", "days": 60}],
    ),
    "major_customer_stops_paying_90_days": (
        "Major customer stops paying for 90 days",
        [{"type": "customer_payment_stop", "days": 90}],
    ),
    "operating_expenses_up_15": (
        "Operating expenses increase by 15%",
        [{"type": "operating_expense_increase", "increase_pct": "0.15"}],
    ),
    "new_debt": ("New debt is added", [{"type": "new_debt"}]),
    "interest_rate_up_300bps": (
        "Interest rates increase by 3 percentage points",
        [{"type": "interest_rate_increase", "increase_bps": 300}],
    ),
    "major_supplier_cost_up_10": (
        "Major supplier raises prices by 10%",
        [{"type": "supplier_cost_increase", "increase_pct": "0.10"}],
    ),
}
