"""Each agent on its own: what it is given, and what its output must satisfy."""

import copy

import pytest

from finpulse.agents.base import run_agent
from finpulse.agents.catalogue import AGENTS, ANALYSTS
from finpulse.agents.schemas import AgentRun
from tests.agents.fakes import FakeLLM, claim, interp, item, pack_for, valid_output

PACK = pack_for()


def given(agent: str) -> set[str]:
    return {i.id for i in AGENTS[agent].select(PACK)}


async def analysts() -> dict[str, AgentRun]:
    llm = FakeLLM(PACK)
    return {n: await run_agent(AGENTS[n], llm, PACK) for n in ANALYSTS}


@pytest.mark.parametrize("agent", ANALYSTS)
async def test_each_analyst_runs_independently(agent: str) -> None:
    run = await run_agent(AGENTS[agent], FakeLLM(PACK), PACK)

    assert run.status == "succeeded", run.verification
    assert run.claims and all(c.agent == agent for c in run.claims)
    assert AGENTS[agent].output_model.model_validate(run.output)


def test_each_agent_sees_the_evidence_it_needs() -> None:
    assert "metric:debt.service_burden" in given("credit_intelligence")
    assert not any(i.startswith("stress:") for i in given("credit_intelligence"))
    assert all(
        i.startswith(("stress:", "assumption:stress", "metric:", "fact:", "passport:overall"))
        for i in given("stress_interpretation")
    )
    assert any(
        i.startswith("warning:") and i.count(":") == 2 for i in given("early_warning_investigation")
    )
    assert "risk:timeline" in given("early_warning_investigation")
    assert not any(":shock." in i for i in given("risk_investigation"))
    assert given("red_team") == given("senior_synthesis") == {i.id for i in PACK.items}


async def test_red_team_works_from_verified_claims_only() -> None:
    upstream = await analysts()
    llm = FakeLLM(PACK)

    run = await run_agent(AGENTS["red_team"], llm, PACK, upstream)

    assert run.status == "succeeded"
    content = llm.requests[0].messages[0]["content"]
    assert '"claim_id": "PRO-01"' in content and '"claim_id": "STR-01"' in content
    assert run.output is not None
    assert run.output["challenges"][0]["target_claim_id"] in {
        c.claim_id for r in upstream.values() for c in r.claims
    }


async def test_red_team_cannot_target_a_claim_that_does_not_exist() -> None:
    upstream = await analysts()
    out = {
        "challenges": [
            {
                "target_claim_id": "RSK-99",
                "challenge_summary": "x",
                "contradictory_evidence": [],
                "missing_information": [],
                "weak_assumptions": [],
                "alternative_explanations": [],
                "severity": "minor",
            }
        ],
        "disagreements_assessed": [],
        "overall_robustness": interp([item(PACK, "risk:summary")]),
    }
    llm = FakeLLM(PACK, {"red_team": [out] * 3})

    run = await run_agent(AGENTS["red_team"], llm, PACK, upstream)

    # the bad challenge is dropped; the rest of the output stands
    assert run.status == "succeeded" and run.output is not None
    assert run.output["challenges"] == []
    assert run.verification is not None and run.verification.pruned


async def test_warning_investigation_must_name_a_real_warning() -> None:
    out = copy.deepcopy(valid_output("early_warning_investigation", PACK))
    out["investigations"][0]["warning_evidence_id"] = "metric:cash.runway"
    llm = FakeLLM(PACK, {"early_warning_investigation": [out]})

    run = await run_agent(AGENTS["early_warning_investigation"], llm, PACK)

    assert run.attempts == 2
    assert "wrong_reference_kind" in llm.requests[1].messages[-1]["content"]


async def test_senior_sections_must_match_their_types() -> None:
    upstream = await analysts()
    upstream["red_team"] = await run_agent(AGENTS["red_team"], FakeLLM(PACK), PACK, upstream)
    good = FakeLLM(PACK)
    probe = await run_agent(AGENTS["senior_synthesis"], good, PACK, upstream)
    assert probe.status == "succeeded"

    def misfiled(request):  # type: ignore[no-untyped-def]
        out = valid_output("senior_synthesis", PACK, request)
        out["facts"] = [claim(item(PACK, "metric:liquidity.ratio"), based_on_claims=[])]
        return out

    llm = FakeLLM(PACK, {"senior_synthesis": [misfiled]})
    run = await run_agent(AGENTS["senior_synthesis"], llm, PACK, upstream)

    assert run.attempts == 2
    assert "wrong_section_type" in llm.requests[1].messages[-1]["content"]


async def test_senior_is_told_which_agents_failed() -> None:
    upstream = await analysts()
    del upstream["stress_interpretation"]
    llm = FakeLLM(PACK)

    await run_agent(AGENTS["senior_synthesis"], llm, PACK, upstream)

    assert (
        "produced no verified findings: stress_interpretation, red_team"
        in (llm.requests[0].messages[0]["content"])
    )


def test_catalogue_is_complete() -> None:
    assert list(AGENTS) == [*ANALYSTS, "red_team", "senior_synthesis"]
    for spec in AGENTS.values():
        info = spec.info()
        assert info.output_schema["type"] == "object" and info.purpose
