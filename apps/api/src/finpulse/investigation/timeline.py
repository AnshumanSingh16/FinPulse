"""The eight user-facing investigation steps, rebuilt from the workflow's real stages and events.

The orchestrator runs eleven stages (see ``orchestrator``); users see eight steps. Each step
declares exactly which stages and agents execute it, and its state, timing and highlights come
only from those stages' records and those agents' events. Steps 2–5 are four specialist agents
that the orchestrator runs concurrently, and they are marked as one parallel group rather than
presented as a sequence. Nothing here is estimated: a step with no recorded work is pending
(while the run is live) or skipped.

The same function serves a live run (``InvestigationProgress``) and a finished record
(``Investigation``), so the timeline a user watches is the timeline that is stored.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from finpulse.agents.catalogue import AGENTS
from finpulse.agents.schemas import AgentRun
from finpulse.investigation.schemas import (
    AgentProgress,
    ChallengeNote,
    InvestigationEvent,
    InvestigationTimeline,
    KeyFinding,
    StageName,
    StageRecord,
    StepState,
    TimelineStep,
)

# Each agent's summary-level claim: the path of the claim that states its overall finding.
KEY_FINDING_PATH = {
    "financial_profile": "summary",
    "credit_intelligence": "reliability_view",
    "early_warning_investigation": "common_thread",
    "risk_investigation": "overall",
    "stress_interpretation": "resilience_summary",
    "red_team": "overall_robustness",
    "senior_synthesis": "overall_assessment",
}

# Agents that do not run when their stage is skipped.
SKIPPED_STAGES: dict[str, list[str]] = {
    "red_team_challenge": ["red_team"],
    "senior_synthesis": ["senior_synthesis"],
}


@dataclass(frozen=True)
class StepSpec:
    key: str
    title: str
    description: str
    stages: tuple[StageName, ...] = ()
    agents: tuple[str, ...] = ()
    inputs: tuple[StageName, ...] = ()  # earlier deterministic stages whose results it works on
    parallel_group: str | None = None


STEPS: tuple[StepSpec, ...] = (
    StepSpec(
        "collect_evidence",
        "Collecting financial evidence",
        "Loads the bank, invoice, bill and loan records and runs the deterministic engines: 25 "
        "metrics, the Financial Passport, the early-warning rules and the stress scenarios. "
        "Their results become a hashed evidence pack, the only material the agents may cite.",
        stages=(
            "financial_data",
            "deterministic_analytics",
            "financial_passport",
            "early_warning_detection",
            "stress_testing",
            "evidence_assembly",
        ),
    ),
    StepSpec(
        "cash_flow",
        "Analyzing cash flow",
        "The Financial Profile Agent reads the cash-flow, revenue, expense, balance and "
        "liquidity metrics to describe the entity's financial condition.",
        agents=("financial_profile",),
        inputs=("deterministic_analytics",),
        parallel_group="specialists",
    ),
    StepSpec(
        "reliability",
        "Evaluating financial reliability",
        "The Credit Intelligence Agent weighs repayment capacity and payment behaviour, using "
        "alternative data where credit history is thin. It never produces a credit decision.",
        agents=("credit_intelligence",),
        inputs=("financial_passport",),
        parallel_group="specialists",
    ),
    StepSpec(
        "early_warnings",
        "Investigating early warnings",
        "The Early Warning Investigation Agent explains why each deterministic warning fired. "
        "The Risk Investigation Agent ranks the most important risks and their likely causes.",
        agents=("early_warning_investigation", "risk_investigation"),
        inputs=("early_warning_detection",),
        parallel_group="specialists",
    ),
    StepSpec(
        "stress_scenarios",
        "Running stress scenarios",
        "The stress-test engine projected cash under each scenario in step 1. The Stress-Test "
        "Interpretation Agent explains the consequences and the key vulnerability.",
        agents=("stress_interpretation",),
        inputs=("stress_testing",),
        parallel_group="specialists",
    ),
    StepSpec(
        "red_team",
        "Red-team challenge",
        "Disagreements between agents are detected deterministically, and significant risk "
        "assessments are queued for mandatory review. The Red-Team Agent then challenges them "
        "with contradictory evidence, missing information and alternative explanations.",
        stages=("disagreement_detection", "red_team_challenge"),
        agents=("red_team",),
    ),
    StepSpec(
        "verify_evidence",
        "Verifying evidence",
        "The deterministic verifier checked each agent's output as it returned. Cited evidence "
        "must exist, numbers must match it, and statement types must be correct; anything else "
        "is pruned. This step audits all verified claims before synthesis and confirms every "
        "reference resolves to the hashed evidence pack.",
        stages=("evidence_verification",),
    ),
    StepSpec(
        "final_assessment",
        "Generating final assessment",
        "The Senior Financial Intelligence Agent synthesises the verified, challenged findings "
        "(its own output is verified too). The orchestrator then assembles the assessment and "
        "caps confidence by deterministic rules.",
        stages=("senior_synthesis", "final_assessment"),
        agents=("senior_synthesis",),
    ),
)

_STEP_STATE: dict[str, StepState] = {
    "succeeded": "completed",
    "failed": "failed",
    "running": "running",
    "skipped": "skipped",
    "pending": "pending",
}
_SEVERITY = {"completed": 0, "skipped": 0, "completed_with_issues": 1, "failed": 2}


def key_finding(run: AgentRun) -> KeyFinding | None:
    """The agent's summary-level verified claim, if it produced one."""
    path = KEY_FINDING_PATH.get(run.agent)
    for c in run.claims:
        if c.path == path:
            return KeyFinding(
                claim_id=c.claim_id,
                statement=c.statement,
                statement_type=c.statement_type,
                confidence=c.confidence,
                evidence_ids=c.evidence_ids,
            )
    return None


def agent_event_data(run: AgentRun) -> dict[str, Any]:
    """What an agent's completion event carries, so live progress can show its findings."""
    output = run.output or {}
    finding = key_finding(run)
    data: dict[str, Any] = {
        "claim_ids": [c.claim_id for c in run.claims],
        "evidence_ids": sorted({e for c in run.claims for e in c.evidence_ids}),
        "key_finding": finding.model_dump() if finding else None,
    }
    if run.agent == "red_team":
        data["challenges"] = [
            {
                "target_claim_id": ch.get("target_claim_id"),
                "severity": ch.get("severity"),
                "summary": ch.get("challenge_summary"),
            }
            for ch in output.get("challenges", [])
        ]
    if run.agent == "senior_synthesis":
        data["resolutions"] = [
            {"target_claim_id": r.get("target_claim_id"), "resolution": r.get("resolution")}
            for r in output.get("challenges_addressed", [])
        ]
    return data


def _agents(events: Iterable[InvestigationEvent], running: bool) -> dict[str, AgentProgress]:
    agents = {n: AgentProgress(agent=n, title=s.title, focus=s.purpose) for n, s in AGENTS.items()}
    challenges: list[dict[str, Any]] = []
    resolutions: dict[str, str] = {}
    for e in events:
        name = e.data.get("agent")
        a = agents.get(name) if isinstance(name, str) else None
        if e.event == "agent_started" and a:
            a.state, a.started_at = "running", e.at
        elif e.event in ("agent_completed", "agent_failed") and a:
            d = e.data
            a.state = "succeeded" if e.event == "agent_completed" else "failed"
            a.completed_at = e.at
            a.claims, a.attempts, a.error = d.get("claims"), d.get("attempts"), d.get("error")
            a.stance = d.get("stance")
            a.issues_caught, a.pruned = d.get("issues_caught"), d.get("pruned")
            a.claim_ids = list(d.get("claim_ids") or [])
            a.evidence_ids = list(d.get("evidence_ids") or [])
            kf = d.get("key_finding")
            a.key_finding = KeyFinding.model_validate(kf) if kf else None
            challenges.extend(d.get("challenges") or [])
            for r in d.get("resolutions") or []:
                resolutions[str(r.get("target_claim_id"))] = str(r.get("resolution"))
        elif e.event == "stage_completed" and e.data.get("status") == "skipped":
            for n in SKIPPED_STAGES.get(e.stage, []):
                agents[n].state = "skipped"
    owner = {cid: a for a in agents.values() for cid in a.claim_ids}
    for ch in challenges:
        target = owner.get(str(ch.get("target_claim_id")))
        if target is not None:
            target.challenges.append(
                ChallengeNote(
                    target_claim_id=str(ch.get("target_claim_id")),
                    severity=str(ch.get("severity")),
                    summary=str(ch.get("summary") or ""),
                    resolution=resolutions.get(str(ch.get("target_claim_id"))),
                )
            )
    if not running:
        for a in agents.values():
            if a.state in ("pending", "running"):
                a.state = "skipped"
    return agents


def _worst(states: Sequence[str]) -> StepState:
    if all(s == "skipped" for s in states):
        return "skipped"
    worst = max(states, key=lambda s: _SEVERITY.get(s, 0))
    return "completed" if worst == "skipped" else worst  # type: ignore[return-value]


def _ms(start: dt.datetime | None, end: dt.datetime | None) -> int | None:
    return round((end - start).total_seconds() * 1000) if start and end else None


def _step(
    number: int,
    spec: StepSpec,
    records: dict[str, StageRecord],
    started: dict[str, dt.datetime],
    agents: dict[str, AgentProgress],
    running: bool,
) -> TimelineStep:
    mine = [agents[n] for n in spec.agents]
    highlights = [f"Input: {records[s].summary}" for s in spec.inputs if s in records]
    if spec.stages:
        done = [records[s] for s in spec.stages if s in records]
        begun = [started[s] for s in spec.stages if s in started]
        state: StepState
        if len(done) == len(spec.stages):
            state = _worst([r.status for r in done])
            # A step that still produced its result (its last stage did not fail) despite an
            # earlier failure, e.g. a deterministic fallback after the senior agent, has issues.
            if state == "failed" and done[-1].status != "failed":
                state = "completed_with_issues"
        elif begun and running:
            state = "running"
        elif not running:
            state = "failed" if any(r.status == "failed" for r in done) or begun else "skipped"
        else:
            state = "pending"
        highlights += [r.summary for r in done if r.summary]
        return TimelineStep(
            number=number,
            key=spec.key,
            title=spec.title,
            description=spec.description,
            stages=list(spec.stages),
            agents=list(spec.agents),
            parallel_group=spec.parallel_group,
            state=state,
            started_at=min(begun) if begun else None,
            completed_at=done[-1].completed_at if len(done) == len(spec.stages) else None,
            duration_ms=sum(r.duration_ms for r in done) if done else None,
            highlights=highlights,
        )
    # Agent-only steps (2–5): state and timing are the agents' own.
    states = [_STEP_STATE[a.state] for a in mine]
    if any(s == "running" for s in states):
        step_state: StepState = "running"
    elif any(s == "pending" for s in states):
        step_state = "pending"
    elif all(s == "failed" for s in states):
        step_state = "failed"
    elif any(s == "failed" for s in states):
        step_state = "completed_with_issues"
    else:
        step_state = _worst(states)
    starts = [a.started_at for a in mine if a.started_at]
    ends = [a.completed_at for a in mine if a.completed_at]
    finished = len(ends) == len(mine)
    for a in mine:
        if a.state == "succeeded":
            highlights.append(f"{a.title}: {a.claims} verified claim(s).")
        elif a.state == "failed":
            highlights.append(f"{a.title} failed ({a.error or 'error'}).")
    return TimelineStep(
        number=number,
        key=spec.key,
        title=spec.title,
        description=spec.description,
        stages=["specialized_investigation"],
        agents=list(spec.agents),
        parallel_group=spec.parallel_group,
        state=step_state,
        started_at=min(starts) if starts else None,
        completed_at=max(ends) if finished and ends else None,
        duration_ms=_ms(min(starts), max(ends)) if finished and starts and ends else None,
        highlights=highlights,
    )


def build_timeline(
    stages: Sequence[StageRecord], events: Sequence[InvestigationEvent], *, running: bool
) -> InvestigationTimeline:
    records: dict[str, StageRecord] = {r.stage: r for r in stages}
    started: dict[str, dt.datetime] = {e.stage: e.at for e in events if e.event == "stage_started"}
    agents = _agents(events, running)
    steps = [
        _step(i, spec, records, started, agents, running) for i, spec in enumerate(STEPS, start=1)
    ]
    return InvestigationTimeline(steps=steps, agents=list(agents.values()))
