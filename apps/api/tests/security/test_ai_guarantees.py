"""The AI may not make a lending decision, and its conclusions are distinguishable from facts."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from finpulse.agents.base import run_agent
from finpulse.agents.catalogue import AGENTS
from finpulse.agents.verifier import PROHIBITED, Verifier
from finpulse.investigation.schemas import PROVENANCE, Investigation
from tests.agents.fakes import FakeLLM, pack_for, valid_output

PACK = pack_for()
PROFILE = AGENTS["financial_profile"]


@pytest.mark.parametrize(
    "text",
    [
        "We recommend approving the loan application.",
        "The credit line should be declined.",
        "The business should not be financed.",
        "Sharma Electricals is creditworthy.",
        "The business is eligible for a loan of this size.",
        "Its credit score is 712.",
        "The lender can extend a loan on this evidence.",
    ],
)
def test_lending_decisions_are_recognised(text: str) -> None:
    assert PROHIBITED.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "This is not a credit score, credit assessment or lending decision.",
        "Never a lending decision: verify the receivables ageing before any review.",
        "The passport must not be used for lending on its own.",
        "Repayments on the existing loan have been on time.",
        "Request the latest GST returns and the loan statement.",
    ],
)
def test_descriptive_mentions_are_not_decisions(text: str) -> None:
    assert not PROHIBITED.search(text)


def with_summary(statement: str) -> dict[str, Any]:
    out = copy.deepcopy(valid_output("financial_profile", PACK))
    out["summary"]["statement"] = statement
    return out


def test_the_verifier_rejects_a_decision_in_any_field() -> None:
    out = with_summary("The loan should be approved.")
    out["weaknesses"][0]["statement"] = "Approve the loan application."

    found = Verifier(PACK, PROFILE.rules).verify(out).found

    assert {f.code for f in found} == {"prohibited_decision"}
    assert len(found) == 2


async def test_a_decision_is_sent_back_and_rewritten() -> None:
    llm = FakeLLM(PACK, {"financial_profile": [with_summary("We would approve the loan.")]})

    run = await run_agent(PROFILE, llm, PACK)

    assert run.status == "succeeded" and run.attempts == 2
    assert run.verification is not None
    assert [i.code for i in run.verification.attempts_issues[0]] == ["prohibited_decision"]
    assert "approve" not in str(run.output).lower()
    assert "lending decision" in llm.requests[1].messages[-1]["content"]


async def test_a_persistent_decision_is_pruned_or_fails() -> None:
    bad = copy.deepcopy(valid_output("financial_profile", PACK))
    bad["weaknesses"].append(dict(bad["weaknesses"][0], statement="Reject the loan application."))
    llm = FakeLLM(PACK, {"financial_profile": [bad] * 5})

    run = await run_agent(PROFILE, llm, PACK)

    assert "reject the loan" not in str(run.output).lower()
    if run.status == "succeeded":
        assert run.verification is not None
        assert any("Reject the loan" in p for p in run.verification.pruned)


def test_every_investigation_field_has_a_declared_provenance() -> None:
    declared = {f.split(".")[0].split("[")[0] for f in PROVENANCE.deterministic}
    declared |= {f.split(".")[0].split("[")[0] for f in PROVENANCE.ai_generated}
    bookkeeping = {
        "investigation_id",
        "entity_id",
        "entity",
        "as_of",
        "workflow_version",
        "ai_mode",
        "status",
        "started_at",
        "completed_at",
        "duration_ms",
        "red_team_run",
        "senior_synthesis_run",
        "usage",
        "timeline",
        "disclaimer",
        "provenance",
        "confidence",
    }
    assert set(Investigation.model_fields) - declared - bookkeeping == set()
    assert PROVENANCE.ai_can_modify_records is False and PROVENANCE.lending_decision is False
    assert "AI_INTERPRETATION" in PROVENANCE.statement_types
