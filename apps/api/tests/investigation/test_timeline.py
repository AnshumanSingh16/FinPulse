"""The eight user-facing steps must reflect the workflow's real stages and agent events."""

from __future__ import annotations

from typing import Any

import pytest

from finpulse.agents.llm import LLMRefusalError
from finpulse.core.errors import LLMUnavailableError
from finpulse.investigation.orchestrator import InvestigationOrchestrator, Recorder
from finpulse.investigation.timeline import STEPS, build_timeline
from tests.agents.fakes import STANCES, FakeLLM
from tests.investigation.test_orchestrator import AS_OF, MEHRA, PACK, Clock, investigate

TITLES = [
    "Collecting financial evidence",
    "Analyzing cash flow",
    "Evaluating financial reliability",
    "Investigating early warnings",
    "Running stress scenarios",
    "Red-team challenge",
    "Verifying evidence",
    "Generating final assessment",
]


@pytest.fixture(autouse=True)
def _stances() -> Any:
    STANCES.clear()
    yield
    STANCES.clear()


def test_every_step_maps_to_real_stages_or_agents() -> None:
    assert [s.title for s in STEPS] == TITLES
    assert all(s.stages or s.agents for s in STEPS)
    assert [s.number for s in build_timeline([], [], running=True).steps] == list(range(1, 9))


async def test_completed_investigation_timeline() -> None:
    inv = await investigate(FakeLLM(PACK))
    assert inv.timeline is not None
    steps = {s.key: s for s in inv.timeline.steps}

    assert [s.title for s in inv.timeline.steps] == TITLES
    assert all(s.state == "completed" for s in inv.timeline.steps)
    assert {k for k, s in steps.items() if s.parallel_group == "specialists"} == {
        "cash_flow",
        "reliability",
        "early_warnings",
        "stress_scenarios",
    }
    assert steps["verify_evidence"].stages == ["evidence_verification"]
    assert steps["verify_evidence"].highlights[0].startswith("43 verified claim(s)")
    assert steps["collect_evidence"].duration_ms is not None
    assert steps["early_warnings"].highlights[0].startswith("Input: ")

    # What the stored record shows is exactly what rebuilding from its own events gives.
    assert inv.timeline == build_timeline(inv.stages, inv.events, running=False)


async def test_agents_carry_findings_evidence_and_challenges() -> None:
    inv = await investigate(FakeLLM(PACK))
    assert inv.timeline is not None
    agents = {a.agent: a for a in inv.timeline.agents}

    profile = agents["financial_profile"]
    run = inv.agent_analyses["financial_profile"]
    assert profile.state == "succeeded" and profile.focus
    assert profile.key_finding is not None
    assert profile.key_finding.claim_id in {c.claim_id for c in run.claims}
    assert set(profile.evidence_ids) == {e for c in run.claims for e in c.evidence_ids}

    # Every red-team challenge is attached to the agent whose claim it targets, with the
    # senior agent's ruling.
    challenged = {(c.target_claim_id, a.agent) for a in agents.values() for c in a.challenges}
    targets = {
        ch["target_claim_id"]
        for ch in (inv.red_team_findings.challenges if inv.red_team_findings else [])
    }
    assert {t for t, _ in challenged} == targets
    for target, agent in challenged:
        assert any(c.claim_id == target for c in inv.agent_analyses[agent].claims)
    assert all(c.resolution for a in agents.values() for c in a.challenges)


async def test_live_timeline_while_specialists_run() -> None:
    inv = await investigate(FakeLLM(PACK))
    first_agent = next(i for i, e in enumerate(inv.events) if e.event == "agent_started")
    events = inv.events[: first_agent + 1]
    stages = [s for s in inv.stages if s.completed_at <= events[-1].at]

    steps = build_timeline(stages, events, running=True).steps

    assert steps[0].state == "completed"
    assert sorted(s.state for s in steps[1:5]) == ["pending", "pending", "pending", "running"]
    assert all(s.state == "pending" for s in steps[5:])


async def test_a_failed_specialist_fails_only_its_step() -> None:
    inv = await investigate(FakeLLM(PACK, {"credit_intelligence": [LLMRefusalError("declined")]}))
    assert inv.timeline is not None
    states = {s.key: s.state for s in inv.timeline.steps}
    assert states["reliability"] == "failed"
    assert states["cash_flow"] == "completed" and states["verify_evidence"] == "completed"


async def test_senior_fallback_is_completed_with_issues() -> None:
    inv = await investigate(FakeLLM(PACK, {"senior_synthesis": [LLMRefusalError("declined")]}))
    assert inv.timeline is not None
    assert inv.timeline.steps[-1].state == "completed_with_issues"


async def test_unreachable_model_skips_later_steps() -> None:
    names = [
        "financial_profile",
        "credit_intelligence",
        "early_warning_investigation",
        "risk_investigation",
        "stress_interpretation",
    ]
    llm = FakeLLM(PACK, {a: [LLMUnavailableError("set ANTHROPIC_API_KEY")] for a in names})
    seen: list[Recorder] = []
    assert AS_OF is not None
    with pytest.raises(LLMUnavailableError):
        await InvestigationOrchestrator(llm, clock=Clock()).investigate(
            MEHRA, AS_OF, listener=seen.append
        )
    rec = seen[-1]

    steps = build_timeline(rec.stages, rec.events, running=False).steps

    assert steps[0].state == "completed"
    assert [s.state for s in steps[1:5]] == ["failed"] * 4
    assert [s.state for s in steps[5:]] == ["skipped"] * 3
