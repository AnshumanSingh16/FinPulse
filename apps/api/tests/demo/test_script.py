"""The scripted demo agents: same orchestrator, same verifier, deterministic answers."""

from __future__ import annotations

import asyncio

import pytest

from finpulse.agents.llm import LLMRequest
from finpulse.analytics import default_as_of
from finpulse.core.errors import LLMUnavailableError
from finpulse.demo import DEMO_MODEL, DemoScriptLLM
from finpulse.demo.script import inr, parse, pct
from finpulse.investigation.orchestrator import InvestigationOrchestrator
from finpulse.investigation.schemas import Investigation
from finpulse.synthetic import PRIMARY_DEMO, SCENARIOS, generate
from tests.analytics.synthetic_adapter import to_financial_data
from tests.test_entities_api import MEHRA

SHARMA = to_financial_data(generate(SCENARIOS[PRIMARY_DEMO]))


async def run(llm: DemoScriptLLM) -> Investigation:
    as_of = default_as_of(SHARMA)
    assert as_of is not None
    return await InvestigationOrchestrator(llm).investigate(SHARMA, as_of)


# Run once for the module (the run itself is what is under test).
INVESTIGATION = asyncio.run(run(DemoScriptLLM(pace_seconds=0)))


@pytest.fixture
def investigation() -> Investigation:
    return INVESTIGATION


async def test_every_agent_passes_the_verifier_first_time(investigation: Investigation) -> None:
    inv = investigation
    runs = [*inv.agent_analyses.values(), inv.red_team_run, inv.senior_synthesis_run]
    assert inv.status == "completed" and inv.ai_mode == "demo_script"
    for r in runs:
        assert r is not None and r.status == "succeeded", r and r.agent
        assert r.model == DEMO_MODEL and r.attempts == 1
        assert r.verification is not None
        assert not r.verification.pruned and not any(r.verification.attempts_issues)
    assert inv.claim_audit.issues_caught == 0 and inv.claim_audit.evidence_references_resolve
    assert inv.final_assessment.source == "senior_synthesis"
    assert inv.final_assessment.risk_level == "medium"


async def test_the_red_team_challenges_and_the_senior_agent_rules(
    investigation: Investigation,
) -> None:
    inv = investigation
    # The credit agent reads the clean record as low risk: a real disagreement to resolve.
    assert any("credit_intelligence" in d.agents for d in inv.disagreements)
    assert inv.red_team_findings is not None
    challenges = inv.red_team_findings.challenges
    targets = {c["target_claim_id"] for c in challenges}
    assert {r.claim_id for r in inv.review_requests} <= targets
    # Evidence that weakens the risk conclusion is put forward…
    contradicting = {
        e for c in challenges for x in c["contradictory_evidence"] for e in x["evidence_ids"]
    }
    assert {"metric:payments.consistency", "metric:liquidity.ratio"} <= contradicting
    # …and every serious challenge gets a ruling.
    ruled = {c["target_claim_id"] for c in inv.final_assessment.challenges_addressed}
    assert {c["target_claim_id"] for c in challenges if c["severity"] != "minor"} <= ruled
    assert inv.recommendations and inv.recommendations[0]["priority"] == "high"


async def test_the_timeline_shows_all_eight_steps_completed(investigation: Investigation) -> None:
    assert investigation.timeline is not None
    assert all(s.state == "completed" for s in investigation.timeline.steps)


async def test_it_is_deterministic(investigation: Investigation) -> None:
    again = await run(DemoScriptLLM(pace_seconds=0))
    assert again.final_assessment == investigation.final_assessment
    assert again.recommendations == investigation.recommendations


async def test_it_refuses_other_entities() -> None:
    as_of = default_as_of(MEHRA)
    assert as_of is not None
    with pytest.raises(LLMUnavailableError):
        await InvestigationOrchestrator(DemoScriptLLM(pace_seconds=0)).investigate(MEHRA, as_of)


async def test_unknown_agents_are_refused() -> None:
    llm = DemoScriptLLM(pace_seconds=0)
    request = LLMRequest(system="", messages=[{"role": "user", "content": ""}], schema={})
    with pytest.raises(LLMUnavailableError):
        await llm.complete(request)


def test_numbers_are_written_the_way_the_verifier_reads_them() -> None:
    from decimal import Decimal

    assert inr(Decimal("1482538.00")) == "₹14,82,538"
    assert inr(Decimal("-250469.66")) == "-₹2,50,470"
    assert inr(Decimal("950")) == "₹950"
    assert pct(Decimal("0.3671")) == "36.7%"


def test_the_prompt_is_read_from_its_structured_blocks() -> None:
    text = "\n".join(
        [
            "## Entity",
            "Sharma Electricals: business, x. Analysis as of 2026-09-30.",
            "<evidence>",
            '{"id": "metric:x", "kind": "calculated_metric", "title": "X", "text": "", '
            '"values": {"value": "1"}}',
            "</evidence>",
            "## Significant assessments requiring review",
            "Challenge each.",
            "<context>",
            '{"claim_id": "RSK-01", "reason": "r", "agent": "risk_investigation", '
            '"statement": "s"}',
            "</context>",
        ]
    )
    p = parse(text)
    assert p.entity.startswith("Sharma Electricals:")
    assert p.value("metric:x") == 1
    assert p.sections["Significant assessments requiring review"][0]["claim_id"] == "RSK-01"


def test_engine_sentences_are_quoted_whole() -> None:
    from finpulse.demo.script import first_sentence

    text = "Customers paid 10.6 days late, against 4.9 days. 25% of receivables are overdue."
    assert first_sentence(text) == "Customers paid 10.6 days late, against 4.9 days."
