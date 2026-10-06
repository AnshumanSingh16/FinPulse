"""The deterministic parts of the workflow: disagreements, review selection, confidence, audit."""

import copy
from typing import Any

import pytest

from finpulse.agents.base import run_agent
from finpulse.agents.catalogue import AGENTS, ANALYSTS
from finpulse.agents.schemas import AgentRun
from finpulse.investigation import analysis
from finpulse.investigation.schemas import ReviewCoverage
from finpulse.scoring import load_model, with_monthly_change
from tests.agents.fakes import FakeLLM, claim, item, pack_for, valid_output
from tests.test_entities_api import SHARMA

PACK = pack_for()
PASSPORT = with_monthly_change(SHARMA, PACK.as_of, load_model())


def output(agent: str, **changes: Any) -> dict[str, Any]:
    out = copy.deepcopy(valid_output(agent, PACK))
    out.update(changes)
    return out


async def analysts(**outputs: dict[str, Any]) -> dict[str, AgentRun]:
    llm = FakeLLM(PACK, {a: [o] for a, o in outputs.items()})
    return {a: await run_agent(AGENTS[a], llm, PACK) for a in ANALYSTS}


# --- disagreements -----------------------------------------------------------------------------


async def test_agreeing_agents_raise_no_disagreement() -> None:
    runs = await analysts()  # every stance "high"; engine "critical": one step apart

    assert analysis.detect_disagreements(runs, PACK, "critical") == []


async def test_stance_spread_and_agent_vs_engine() -> None:
    runs = await analysts(financial_profile=output("financial_profile", risk_stance="low"))

    found = analysis.detect_disagreements(runs, PACK, "critical")

    assert [(d.id, d.kind, d.severity) for d in found] == [
        ("DIS-01", "stance_spread", "major"),
        ("DIS-02", "agent_vs_engine", "major"),
    ]
    assert found[0].agents == ["financial_profile", "credit_intelligence"]
    assert found[0].claim_ids == ["PRO-01", "CRE-01"]  # each side's headline claim
    assert "'low'" in found[1].description and "'critical'" in found[1].description
    assert found[1].evidence_ids == ["risk:summary"]


async def test_one_agents_strength_is_anothers_concern() -> None:
    runs = await analysts(
        financial_profile=output(
            "financial_profile", strengths=[claim(item(PACK, "metric:liquidity.ratio"))]
        ),
    )  # credit's concerns and risk's risks cite liquidity.ratio as negative

    [d] = analysis.detect_disagreements(runs, PACK, "high")

    assert d.kind == "conflicting_reading" and d.evidence_ids == ["metric:liquidity.ratio"]
    assert d.agents == ["credit_intelligence", "financial_profile", "risk_investigation"]


async def test_risk_severity_far_from_the_warnings_it_cites() -> None:
    critical = next(
        i
        for i in PACK.select("warning:*")
        if i.id.count(":") == 1 and i.values["severity"] == "critical"
    )
    risk = output("risk_investigation")
    risk["risks"][0]["severity"] = "low"
    risk["risks"][0]["likely_causes"] = [claim(critical)]
    runs = await analysts(risk_investigation=risk)

    [d] = analysis.detect_disagreements(runs, PACK, "critical")

    assert d.kind == "severity_mismatch" and d.claim_ids == ["RSK-01"]
    assert critical.id in d.evidence_ids


# --- red-team review ---------------------------------------------------------------------------


async def test_significant_assessments_are_sent_for_review() -> None:
    runs = await analysts()

    requests = analysis.select_review_requests(runs, PACK, [], "critical")

    reasons = {r.claim_id: r.reason for r in requests}
    assert reasons["RSK-01"].startswith("high-severity risk assessment")
    assert any(r.startswith("explanation of a critical early warning") for r in reasons.values())
    assert reasons["CRE-01"] == "overall reliability view"
    assert reasons["STR-03"] == "overall resilience judgement"
    assert reasons["PRO-01"] == "overall condition summary"
    assert len(requests) <= analysis.MAX_REVIEW_REQUESTS


async def test_low_severity_risks_are_not_forced_into_review() -> None:
    risk = output("risk_investigation")
    risk["risks"][0]["severity"] = "low"
    runs = await analysts(risk_investigation=risk)

    requests = analysis.select_review_requests(runs, PACK, [], "low")

    assert "RSK-01" not in {r.claim_id for r in requests}


async def test_requirements_and_coverage() -> None:
    runs = await analysts(financial_profile=output("financial_profile", risk_stance="low"))
    disagreements = analysis.detect_disagreements(runs, PACK, "critical")
    requests = analysis.select_review_requests(runs, PACK, disagreements, "critical")
    check = analysis.red_team_requirements(requests, disagreements)

    unmet = check({"challenges": [{"target_claim_id": "RSK-01"}], "disagreements_assessed": []})

    assert not any("RSK-01" in u for u in unmet)
    assert any("DIS-01" in u for u in unmet) and any("CRE-01" in u for u in unmet)
    red = AgentRun(
        agent="red_team",
        title="Red",
        status="succeeded",
        prompt_version="x",
        evidence_items=0,
        output={"challenges": [{"target_claim_id": "RSK-01"}]},
    )
    coverage = analysis.review_coverage(requests, red)
    assert coverage.reviewed == 1 and "RSK-01" not in coverage.unreviewed
    assert next(r for r in requests if r.claim_id == "RSK-01").reviewed


def test_senior_requirements() -> None:
    red = AgentRun(
        agent="red_team",
        title="Red",
        status="succeeded",
        prompt_version="x",
        evidence_items=0,
        output={
            "challenges": [
                {"target_claim_id": "RSK-01", "severity": "major"},
                {"target_claim_id": "PRO-01", "severity": "minor"},
            ]
        },
    )
    check = analysis.senior_requirements([], red)

    assert check(
        {"challenges_addressed": [], "disagreements_resolved": [], "recommendations": []}
    ) == [
        "The red-team challenge to RSK-01 is not addressed in `challenges_addressed`.",
        "Give at least one recommendation.",
    ]


# --- confidence, references, audit -------------------------------------------------------------


def run_of(agent: str, status: str = "succeeded", **extra: Any) -> AgentRun:
    return AgentRun(
        agent=agent,
        title=agent,
        status=status,
        prompt_version="x",
        evidence_items=0,
        output=extra.pop("output", {}),
        **extra,
    )  # type: ignore[arg-type]


FULL = ReviewCoverage(requested=3, reviewed=3, unreviewed=[])


@pytest.mark.parametrize(
    ("missing", "coverage", "expected", "reason"),
    [
        ([], FULL, "high", None),
        (["credit_intelligence"], FULL, "medium", "produced no verified analysis"),
        (["credit_intelligence", "risk_investigation"], FULL, "low", "2 specialist agents"),
        (
            [],
            ReviewCoverage(requested=3, reviewed=2, unreviewed=["RSK-01"]),
            "medium",
            "not challenged by the red team",
        ),
        (["red_team"], FULL, "low", "not red-team reviewed"),
    ],
)
def test_confidence_is_capped_by_what_went_wrong(
    missing: list[str], coverage: ReviewCoverage, expected: str, reason: str | None
) -> None:
    runs = {a: run_of(a) for a in (*ANALYSTS, "red_team")}
    runs["senior_synthesis"] = run_of(
        "senior_synthesis", output={"confidence": "high", "confidence_rationale": "Clear evidence."}
    )
    for m in missing:
        runs[m] = run_of(m, status="failed")

    c = analysis.assess_confidence(runs, ANALYSTS, coverage, [], PASSPORT)

    assert c.level == expected and c.stated_by_senior_agent == "high"
    if reason:
        assert any(reason in a for a in c.adjustments)


def test_confidence_never_rises_above_what_the_senior_agent_stated() -> None:
    runs = {a: run_of(a) for a in (*ANALYSTS, "red_team")}
    runs["senior_synthesis"] = run_of(
        "senior_synthesis", output={"confidence": "low", "confidence_rationale": "Thin data."}
    )

    assert analysis.assess_confidence(runs, ANALYSTS, FULL, [], PASSPORT).level == "low"


async def test_metrics_and_evidence_references() -> None:
    runs = await analysts()

    used = {m.code: m for m in analysis.metrics_used(runs.values(), PACK)}
    refs, resolve = analysis.evidence_references(runs.values(), PACK)

    assert used["liquidity.ratio"].cited_by and used["liquidity.ratio"].value is not None
    assert used["payments.consistency"].unit == "ratio"
    assert resolve and {r.id for r in refs} >= {"metric:liquidity.ratio", "stress:revenue_down_30"}
    assert all(PACK.get(r.id) is not None for r in refs)


def test_deterministic_fallback_quotes_evidence_verbatim() -> None:
    from finpulse.early_warning import load_config, risk_summary

    summary = risk_summary(SHARMA, PACK.as_of, load_config())

    final = analysis.final_assessment(None, PACK, summary, PASSPORT)

    assert final.source == "deterministic_fallback" and final.overall_assessment is None
    assert final.interpretations == []
    for c in final.calculated_metrics:
        assert c["statement"] == item(PACK, c["evidence_ids"][0]).text
    assert final.risk_level == summary.risk_level
