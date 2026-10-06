"""Scenario registry. Add a scenario by writing a ``ScenarioSpec`` in its own module and listing
it here; ``seed``/``reset`` pick it up automatically."""

from finpulse.synthetic.scenarios.ananya_rao_design import ANANYA_RAO_DESIGN
from finpulse.synthetic.scenarios.annapurna_kitchen import ANNAPURNA_KITCHEN
from finpulse.synthetic.scenarios.kaveri_packaging import KAVERI_PACKAGING
from finpulse.synthetic.scenarios.rapid_mobile_hub import RAPID_MOBILE_HUB
from finpulse.synthetic.scenarios.sharma_electricals import SHARMA_ELECTRICALS
from finpulse.synthetic.spec import ScenarioSpec

PRIMARY_DEMO = SHARMA_ELECTRICALS.code

SCENARIOS: dict[str, ScenarioSpec] = {
    spec.code: spec
    for spec in (
        SHARMA_ELECTRICALS,  # deteriorating MSME — primary demo entity
        KAVERI_PACKAGING,  # healthy MSME
        ANNAPURNA_KITCHEN,  # thin-file but healthy MSME
        RAPID_MOBILE_HUB,  # high-risk MSME
        ANANYA_RAO_DESIGN,  # freelancer / independent professional
    )
}


def get_scenario(code: str) -> ScenarioSpec:
    try:
        return SCENARIOS[code]
    except KeyError:
        known = ", ".join(sorted(SCENARIOS))
        raise KeyError(f"unknown scenario {code!r}; known: {known}") from None
