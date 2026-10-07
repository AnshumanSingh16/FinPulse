"""The demo's walkthrough: what to show, in order. Deterministic and data-free — every number
the demo shows comes from the engines at request time, never from this file."""

from __future__ import annotations

import uuid
from datetime import date
from functools import cache

from pydantic import BaseModel

from finpulse.analytics import default_as_of
from finpulse.synthetic import PRIMARY_DEMO, SCENARIOS, generate
from finpulse.synthetic.adapter import to_financial_data

STRESS_PRESET = "major_customer_stops_paying_60_days"


class DemoStep(BaseModel):
    number: int
    title: str
    section: str  # the entity view to open: "", "passport", "warnings", "health", …
    show: str  # what to point at


class DemoInfo(BaseModel):
    enabled: bool
    entity_id: uuid.UUID
    entity_code: str
    entity_name: str
    as_of: date
    stress_preset: str
    narrative: str
    steps: list[DemoStep]


STEPS = [
    DemoStep(
        number=1,
        title="At first, a healthy business",
        section="passport",
        show="Financial Health in the Sound band, a spotless repayment record and revenue still "
        "growing. A traditional lender sees one small bank loan, always paid on time.",
    ),
    DemoStep(
        number=2,
        title="FinPulse looks underneath",
        section="health",
        show="Revenue growing, but receivables rising, collection days lengthening, cash falling "
        "and one customer's share of revenue climbing.",
    ),
    DemoStep(
        number=3,
        title="The early warning",
        section="warnings",
        show="Medium risk, led by Liquidity deterioration: cash is moving out of the bank and "
        "into unpaid invoices, which the liquidity ratio does not show.",
    ),
    DemoStep(
        number=4,
        title="Stress test: the largest customer pays 60 days late",
        section="stress",
        show="Select 'Largest customer delays payment by 60 days' and run it: the six-month "
        "outlook goes from low to high risk and the account is overdrawn at its lowest point.",
    ),
    DemoStep(
        number=5,
        title="The AI investigation",
        section="investigation",
        show="Run the demo investigation: specialist agents explain why the business is becoming "
        "vulnerable, and the red team challenges them with the evidence that cuts the other way.",
    ),
    DemoStep(
        number=6,
        title="The brief",
        section="",
        show="Financial Passport, current risk, the early warning, the main evidence, the stress "
        "result and the recommended actions, on one page.",
    ),
]


@cache
def demo_entity() -> tuple[uuid.UUID, str, date]:
    """The demo entity's id, name and as-of date (the end of its data)."""
    spec = SCENARIOS[PRIMARY_DEMO]
    data = to_financial_data(generate(spec))
    as_of = default_as_of(data)
    if as_of is None:  # pragma: no cover - the demo scenario always has data
        raise RuntimeError("The demo scenario has no data.")
    return data.entity_id, data.display_name, as_of


def demo_info(enabled: bool) -> DemoInfo:
    entity_id, name, as_of = demo_entity()
    return DemoInfo(
        enabled=enabled,
        entity_id=entity_id,
        entity_code=PRIMARY_DEMO,
        entity_name=name,
        as_of=as_of,
        stress_preset=STRESS_PRESET,
        narrative=SCENARIOS[PRIMARY_DEMO].narrative,
        steps=STEPS,
    )
