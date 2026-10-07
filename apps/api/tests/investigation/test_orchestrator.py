"""The investigation workflow end to end, with a scripted model."""

import copy
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from finpulse.agents.catalogue import AGENTS
from finpulse.agents.llm import LLMRefusalError
from finpulse.analytics import default_as_of
from finpulse.core.errors import LLMUnavailableError
from finpulse.investigation.orchestrator import InvestigationOrchestrator
from finpulse.investigation.schemas import Investigation
from tests.agents.fakes import STANCES, FakeLLM, pack_for, valid_output
from tests.test_entities_api import MEHRA

PACK = pack_for("mehra_lighting")
AS_OF = default_as_of(MEHRA)
STAGES = [
    "financial_data",
    "deterministic_analytics",
    "financial_passport",
    "early_warning_detection",
    "stress_testing",
    "evidence_assembly",
    "specialized_investigation",
    "disagreement_detection",
    "red_team_challenge",
    "evidence_verification",
    "senior_synthesis",
    "final_assessment",
]
ANALYST_NAMES = (
    "financial_profile",
    "credit_intelligence",
    "early_warning_investigation",
    "risk_investigation",
    "stress_interpretation",
)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(milliseconds=10)
        return self.now


async def investigate(llm: FakeLLM) -> Investigation:
    assert AS_OF is not None
    return await InvestigationOrchestrator(llm, clock=Clock()).investigate(MEHRA, AS_OF)


@pytest.fixture(autouse=True)
def _stances() -> Any:
    STANCES.clear()
    yield
    STANCES.clear()


async def test_complete_investigation() -> None:
    inv = await investigate(FakeLLM(PACK))

    assert inv.status == "completed"
    assert inv.entity_id == MEHRA.entity_id and inv.as_of == AS_OF
    assert [s.stage for s in inv.stages] == STAGES
    assert all(s.status == "completed" for s in inv.stages)
    assert inv.started_at < inv.completed_at
    # triggered warnings are exactly the engine's, with the investigated ones marked
    assert len(inv.triggered_warnings) == len(
        [i for i in PACK.select("warning:*") if i.id.count(":") == 1]
    )
    assert any(w.investigated and w.investigation_claim_ids for w in inv.triggered_warnings)
    assert inv.financial_metrics_used and all(m.cited_by for m in inv.financial_metrics_used)
    assert set(inv.agent_analyses) == set(ANALYST_NAMES)
    assert inv.red_team_findings is not None and inv.red_team_findings.challenges
    assert inv.red_team_findings.coverage.unreviewed == []
    assert inv.final_assessment.source == "senior_synthesis"
    assert inv.final_assessment.risk_level == "critical"
    assert inv.recommendations and inv.recommendations[0]["rationale"]["evidence_ids"]
    assert inv.confidence.level == "medium"  # what the senior agent stated; nothing capped it
    assert inv.claim_audit.evidence_references_resolve
    assert inv.claim_audit.claims_verified == sum(
        len(r.claims)
        for r in [*inv.agent_analyses.values(), inv.red_team_run, inv.senior_synthesis_run]
        if r
    )
    assert inv.evidence_pack.sha256 == PACK.sha256
    assert inv.usage.calls == 7
    assert "not a credit score" in inv.disclaimer


async def test_agents_receive_only_verified_data() -> None:
    llm = FakeLLM(PACK, {"credit_intelligence": [LLMRefusalError("declined")]})

    inv = await investigate(llm)

    for request in llm.requests:
        content = request.messages[0]["content"]
        evidence = content.split("<evidence>")[1].split("</evidence>")[0]
        for line in evidence.strip().splitlines():
            assert PACK.get(json.loads(line)["id"]) is not None  # only evidence-pack items
    red_input = llm.calls("red_team")[0].messages[0]["content"]
    assert "CRE-" not in red_input.split("## Significant")[0]  # no claims from the failed agent
    assert inv.status == "completed_with_gaps"
    assert inv.agent_analyses["credit_intelligence"].status == "failed"
    assert inv.confidence.level == "medium"
    assert any("Credit Intelligence" in a for a in inv.confidence.adjustments)


async def test_disagreements_go_to_the_red_team_and_are_resolved() -> None:
    STANCES["financial_profile"] = "low"
    llm = FakeLLM(PACK)

    inv = await investigate(llm)

    assert {d.kind for d in inv.disagreements} == {"stance_spread", "agent_vs_engine"}
    red_input = llm.calls("red_team")[0].messages[0]["content"]
    assert '"id": "DIS-01"' in red_input and "Significant assessments requiring review" in red_input
    assert inv.red_team_findings is not None
    assert {d["disagreement_id"] for d in inv.red_team_findings.disagreements_assessed} == {
        d.id for d in inv.disagreements
    }
    assert all(d.resolved for d in inv.disagreements)
    assert len(inv.final_assessment.disagreements_resolved) == len(inv.disagreements)


async def test_red_team_is_pushed_to_review_what_it_skipped() -> None:
    def lazy(request: Any) -> dict[str, Any]:
        out = valid_output("red_team", PACK, request)
        out["challenges"] = out["challenges"][:1]  # reviews only the first required claim
        return out

    llm = FakeLLM(PACK, {"red_team": [lazy, lazy, lazy]})

    inv = await investigate(llm)

    assert len(llm.calls("red_team")) == 3
    assert (
        "passed verification but is incomplete" in llm.calls("red_team")[1].messages[-1]["content"]
    )
    coverage = inv.red_team_findings.coverage  # type: ignore[union-attr]
    assert coverage.unreviewed and coverage.reviewed == 1
    assert any(e.event == "review_missing" for e in inv.events)
    assert inv.confidence.level == "medium" and inv.status == "completed_with_gaps"
    assert next(s for s in inv.stages if s.stage == "red_team_challenge").status == (
        "completed_with_issues"
    )


async def test_unsupported_claims_never_reach_the_record() -> None:
    def invented(request: Any) -> dict[str, Any]:
        out = copy.deepcopy(valid_output("risk_investigation", PACK, request))
        bad = copy.deepcopy(out["risks"][0])
        bad["title"] = "Invented"
        bad["risk"]["statement"] = "Losses will reach ₹99,99,999."
        out["risks"].append(bad)
        return out

    llm = FakeLLM(PACK, {"risk_investigation": [invented] * 3})

    inv = await investigate(llm)

    risk = inv.agent_analyses["risk_investigation"]
    published = json.dumps(
        [
            risk.output,
            [c.statement for c in risk.claims],
            inv.final_assessment.model_dump(mode="json"),
            inv.recommendations,
        ]
    )
    assert "99,99,999" not in published  # never in an output, claim or the final assessment
    assert "99,99,999" in str(risk.verification.pruned)  # type: ignore[union-attr]  # audited
    assert inv.claim_audit.claims_pruned == 1 and inv.claim_audit.issues_caught >= 3
    assert inv.agent_analyses["risk_investigation"].verification.pruned  # type: ignore[union-attr]


async def test_senior_failure_falls_back_to_deterministic_results() -> None:
    llm = FakeLLM(PACK, {"senior_synthesis": [LLMRefusalError("declined")]})

    inv = await investigate(llm)

    assert inv.final_assessment.source == "deterministic_fallback"
    assert inv.final_assessment.interpretations == [] and inv.recommendations == []
    assert inv.confidence.level == "low" and inv.status == "completed_with_gaps"
    assert any(e.event == "fallback_assessment" for e in inv.events)


async def test_an_unreachable_model_fails_fast() -> None:
    llm = FakeLLM(PACK, {a: [LLMUnavailableError("set ANTHROPIC_API_KEY")] for a in ANALYST_NAMES})

    with pytest.raises(LLMUnavailableError):
        await investigate(llm)

    assert not llm.calls("red_team")


async def test_event_log_tells_the_whole_story() -> None:
    inv = await investigate(FakeLLM(PACK))

    events = [e.event for e in inv.events]
    assert events[0] == "investigation_started" and events[-1] == "investigation_completed"
    assert events.count("stage_started") == len(STAGES) == events.count("stage_completed")
    assert events.count("agent_completed") == len(AGENTS)
    assert "warning_triggered" in events and "review_requested" in events
    times = [e.at for e in inv.events]
    assert times == sorted(times)


async def test_events_are_logged_with_the_investigation_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from finpulse.observability.logging import configure_logging
    from tests.conftest import make_settings

    configure_logging(make_settings(LOG_FORMAT="json"))

    inv = await investigate(FakeLLM(PACK))

    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    mine = [line for line in lines if line.get("investigation_id") == str(inv.investigation_id)]
    assert {line["event"] for line in mine} >= {
        "investigation_started",
        "stage_completed",
        "agent_completed",
        "investigation_completed",
    }
