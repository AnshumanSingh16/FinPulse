"""The whole pipeline: order, partial failure and the final report."""

import pytest

from finpulse.agents.llm import LLMRefusalError
from finpulse.agents.orchestrator import dependency_closure, run_agents, run_pipeline
from finpulse.core.errors import LLMUnavailableError, NotFoundError
from tests.agents.fakes import FakeLLM, pack_for

PACK = pack_for()


async def test_full_pipeline() -> None:
    llm = FakeLLM(PACK)

    report = await run_pipeline(llm, PACK)

    assert report.status == "complete"
    assert list(report.agents) == [
        "financial_profile",
        "credit_intelligence",
        "early_warning_investigation",
        "risk_investigation",
        "stress_interpretation",
        "red_team",
        "senior_synthesis",
    ]
    assert report.synthesis is not None
    assert {"facts", "calculated_metrics", "forecasts", "assumptions", "interpretations"} <= set(
        report.synthesis
    )
    assert report.usage.calls == 7
    assert report.evidence_pack_sha256 == PACK.sha256
    assert "not a credit score" in report.disclaimer
    # the senior agent ran last, with everyone's claims
    assert llm.requests[-1].metadata["agent"] == "senior_synthesis"
    assert '"claim_id": "RED-01"' in llm.requests[-1].messages[0]["content"]


async def test_one_failed_analyst_gives_a_partial_report() -> None:
    llm = FakeLLM(PACK, {"credit_intelligence": [LLMRefusalError("declined")]})

    report = await run_pipeline(llm, PACK)

    assert report.status == "partial"
    assert report.agents["credit_intelligence"].status == "failed"
    assert report.agents["senior_synthesis"].status == "succeeded"
    senior_input = llm.calls("senior_synthesis")[0].messages[0]["content"]
    assert "CRE-01" not in senior_input and "credit_intelligence" in senior_input


async def test_when_every_analyst_fails_the_rest_are_skipped() -> None:
    llm = FakeLLM(
        PACK,
        {
            a: [LLMRefusalError("no")]
            for a in (
                "financial_profile",
                "credit_intelligence",
                "early_warning_investigation",
                "risk_investigation",
                "stress_interpretation",
            )
        },
    )

    report = await run_pipeline(llm, PACK)

    assert report.status == "failed" and report.synthesis is None
    assert report.agents["red_team"].status == "skipped"
    assert report.agents["senior_synthesis"].status == "skipped"


async def test_an_unreachable_model_fails_the_request() -> None:
    llm = FakeLLM(
        PACK,
        {
            a: [LLMUnavailableError("set ANTHROPIC_API_KEY")]
            for a in (
                "financial_profile",
                "credit_intelligence",
                "early_warning_investigation",
                "risk_investigation",
                "stress_interpretation",
            )
        },
    )

    with pytest.raises(LLMUnavailableError, match="ANTHROPIC_API_KEY"):
        await run_pipeline(llm, PACK)


async def test_running_one_agent_runs_only_what_it_needs() -> None:
    llm = FakeLLM(PACK)

    runs = await run_agents(llm, PACK, ["stress_interpretation"])

    assert list(runs) == ["stress_interpretation"] and len(llm.requests) == 1


def test_dependency_closure() -> None:
    assert dependency_closure(["red_team"])[-1] == "red_team"
    assert len(dependency_closure(["senior_synthesis"])) == 7
    with pytest.raises(NotFoundError):
        dependency_closure(["oracle"])
