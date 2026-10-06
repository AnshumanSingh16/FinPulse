"""Running an agent with its dependencies (the single-agent endpoint). The full workflow is
tested in tests/investigation/."""

import pytest

from finpulse.agents.llm import LLMRefusalError
from finpulse.agents.orchestrator import dependency_closure, run_agents
from finpulse.core.errors import LLMUnavailableError, NotFoundError
from tests.agents.fakes import FakeLLM, pack_for

PACK = pack_for()
ANALYSTS = (
    "financial_profile",
    "credit_intelligence",
    "early_warning_investigation",
    "risk_investigation",
    "stress_interpretation",
)


async def test_running_one_agent_runs_only_what_it_needs() -> None:
    llm = FakeLLM(PACK)

    runs = await run_agents(llm, PACK, ["stress_interpretation"])

    assert list(runs) == ["stress_interpretation"] and len(llm.requests) == 1


async def test_senior_runs_after_everything_it_depends_on() -> None:
    llm = FakeLLM(PACK, {"credit_intelligence": [LLMRefusalError("declined")]})

    runs = await run_agents(llm, PACK, ["senior_synthesis"])

    assert list(runs)[-2:] == ["red_team", "senior_synthesis"]
    assert runs["credit_intelligence"].status == "failed"
    assert runs["senior_synthesis"].status == "succeeded"
    assert llm.requests[-1].metadata["agent"] == "senior_synthesis"
    assert "CRE-01" not in llm.requests[-1].messages[0]["content"]


async def test_when_every_analyst_fails_the_rest_are_skipped() -> None:
    llm = FakeLLM(PACK, {a: [LLMRefusalError("no")] for a in ANALYSTS})

    runs = await run_agents(llm, PACK, ["senior_synthesis"])

    assert runs["red_team"].status == "skipped" and runs["senior_synthesis"].status == "skipped"


async def test_an_unreachable_model_fails_the_request() -> None:
    llm = FakeLLM(PACK, {a: [LLMUnavailableError("set ANTHROPIC_API_KEY")] for a in ANALYSTS})

    with pytest.raises(LLMUnavailableError, match="ANTHROPIC_API_KEY"):
        await run_agents(llm, PACK, ["red_team"])


def test_dependency_closure() -> None:
    assert dependency_closure(["red_team"])[-1] == "red_team"
    assert len(dependency_closure(["senior_synthesis"])) == 7
    with pytest.raises(NotFoundError):
        dependency_closure(["oracle"])
