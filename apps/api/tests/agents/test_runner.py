"""One agent's run: verification, the repair loop, pruning and error handling."""

import copy
from typing import Any

import pytest

from finpulse.agents.base import MAX_ATTEMPTS, run_agent
from finpulse.agents.catalogue import AGENTS
from finpulse.agents.llm import LLMRefusalError
from finpulse.core.errors import LLMUnavailableError
from tests.agents.fakes import FakeLLM, item, pack_for, valid_output

PACK = pack_for()
PROFILE = AGENTS["financial_profile"]


def profile(**changes: Any) -> dict[str, Any]:
    out = copy.deepcopy(valid_output("financial_profile", PACK))
    out.update(changes)
    return out


def invented_weakness() -> dict[str, Any]:
    return {
        "statement": "Cash runway is 7.3 months.",
        "statement_type": "CALCULATED_METRIC",
        "evidence_ids": ["metric:cash.runway"],
        "confidence": "high",
    }


async def test_a_valid_answer_passes_first_time() -> None:
    llm = FakeLLM(PACK)

    run = await run_agent(PROFILE, llm, PACK)

    assert run.status == "succeeded" and run.attempts == 1
    assert run.verification is not None and run.verification.passed
    assert run.verification.claims_checked == 5
    assert [c.claim_id for c in run.claims] == ["PRO-01", "PRO-02", "PRO-03", "PRO-04", "PRO-05"]
    assert run.claims[0].path == "summary"
    assert run.usage.calls == 1 and run.usage.input_tokens == 1000
    assert run.prompt_version.startswith("financial_profile@")


async def test_the_model_sees_rules_evidence_and_schema() -> None:
    llm = FakeLLM(PACK)

    await run_agent(PROFILE, llm, PACK)

    [request] = llm.requests
    assert "never calculate" in request.system and "Financial Profile Agent" in request.system
    content = request.messages[0]["content"]
    assert '"id": "metric:cash.runway"' in content and "<evidence>" in content
    assert request.schema["additionalProperties"] is False


async def test_invented_number_is_sent_back_and_fixed() -> None:
    bad = profile(weaknesses=[invented_weakness()])
    llm = FakeLLM(PACK, {"financial_profile": [bad]})

    run = await run_agent(PROFILE, llm, PACK)

    assert run.status == "succeeded" and run.attempts == 2
    repair = llm.requests[1].messages
    assert [m["role"] for m in repair] == ["user", "assistant", "user"]
    assert "unsupported_number" in repair[2]["content"] and "7.3" in repair[2]["content"]
    assert run.verification is not None
    assert [i.code for i in run.verification.attempts_issues[0]] == ["unsupported_number"]
    assert run.verification.attempts_issues[1] == []


async def test_persistent_bad_list_items_are_pruned_and_reported() -> None:
    bad = profile(weaknesses=[invented_weakness(), claim_of("metric:liquidity.ratio")])
    llm = FakeLLM(PACK, {"financial_profile": [bad] * MAX_ATTEMPTS})

    run = await run_agent(PROFILE, llm, PACK)

    assert run.status == "succeeded" and run.attempts == MAX_ATTEMPTS
    assert run.output is not None and len(run.output["weaknesses"]) == 1
    assert run.verification is not None
    assert run.verification.pruned == ["Cash runway is 7.3 months."]
    assert "7.3" not in str(run.output) and all("7.3" not in c.statement for c in run.claims)


async def test_an_unverifiable_summary_fails_the_agent() -> None:
    bad = profile(summary={**invented_weakness(), "statement_type": "AI_INTERPRETATION"})
    llm = FakeLLM(PACK, {"financial_profile": [bad] * MAX_ATTEMPTS})

    run = await run_agent(PROFILE, llm, PACK)

    assert run.status == "failed" and run.output is None and run.claims == []
    assert run.error is not None and run.error.code == "verification_failed"
    assert run.verification is not None and run.verification.issues


async def test_schema_errors_are_retried() -> None:
    llm = FakeLLM(PACK, {"financial_profile": ["not json at all", {"summary": "wrong shape"}]})

    run = await run_agent(PROFILE, llm, PACK)

    assert run.status == "succeeded" and run.attempts == 3
    assert "did not match the response schema" in llm.requests[1].messages[-1]["content"]


async def test_schema_errors_every_time_fail_cleanly() -> None:
    llm = FakeLLM(PACK, {"financial_profile": ["{}"] * MAX_ATTEMPTS})

    run = await run_agent(PROFILE, llm, PACK)

    assert run.status == "failed" and run.error is not None
    assert run.error.code == "llm_invalid_output"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (LLMRefusalError("declined"), "llm_refusal"),
        (LLMUnavailableError("down"), "llm_unavailable"),
        (RuntimeError("bug"), "agent_error"),
    ],
)
async def test_errors_become_a_failed_run(error: Exception, code: str) -> None:
    llm = FakeLLM(PACK, {"financial_profile": [error]})

    run = await run_agent(PROFILE, llm, PACK)

    assert run.status == "failed" and run.error is not None and run.error.code == code


def claim_of(item_id: str) -> dict[str, Any]:
    i = item(PACK, item_id)
    return {
        "statement": i.text,
        "statement_type": "CALCULATED_METRIC",
        "evidence_ids": [i.id],
        "confidence": "high",
    }
