"""The investigation object: the complete, structured record of one financial investigation.

It holds what was analysed (warnings, metrics, evidence), what each agent concluded (verified),
where agents disagreed, what the red team challenged, the final assessment with
recommendations and confidence, and a timestamped log of every stage and event.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from finpulse.agents.schemas import AgentRun, Usage
from finpulse.analytics.schemas import EntityRef

StageName = Literal[
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
StageStatus = Literal["completed", "completed_with_issues", "failed", "skipped"]
EventLevel = Literal["info", "warning", "error"]
ConfidenceLevel = Literal["high", "medium", "low"]
# "demo_script": the agents' answers came from the scripted demo (finpulse.demo), not a model.
AIMode = Literal["live", "demo_script"]


class StageRecord(BaseModel):
    stage: StageName
    title: str
    status: StageStatus
    started_at: dt.datetime
    completed_at: dt.datetime
    duration_ms: int
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


class InvestigationEvent(BaseModel):
    at: dt.datetime
    stage: StageName
    level: EventLevel
    event: str = Field(description='Machine-readable, e.g. "agent_completed"')
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class TriggeredWarning(BaseModel):
    warning_id: str
    evidence_id: str
    rule: str
    category: str
    severity: str
    title: str
    description: str
    first_detected_on: dt.date
    investigated: bool = Field(description="The Early Warning Investigation Agent explained it")
    investigation_claim_ids: list[str]


class MetricUsed(BaseModel):
    code: str
    evidence_id: str
    name: str
    value: Decimal | None
    unit: str
    period: str
    cited_by: list[str] = Field(description="Verified claims that cite this metric")


class EvidenceReference(BaseModel):
    id: str
    kind: str
    source: str
    title: str
    text: str
    cited_by: list[str]


DisagreementKind = Literal[
    "stance_spread", "agent_vs_engine", "conflicting_reading", "severity_mismatch"
]


class Disagreement(BaseModel):
    id: str
    kind: DisagreementKind
    severity: Literal["major", "moderate"]
    description: str
    agents: list[str]
    claim_ids: list[str]
    evidence_ids: list[str]
    resolved: bool = Field(default=False, description="Resolved by the senior agent")


class ReviewRequest(BaseModel):
    claim_id: str
    reason: str
    agent: str
    statement: str
    reviewed: bool = False
    challenges: int = 0


class ReviewCoverage(BaseModel):
    requested: int
    reviewed: int
    unreviewed: list[str]


class RedTeamFindings(BaseModel):
    status: str
    challenges: list[dict[str, Any]]
    disagreements_assessed: list[dict[str, Any]]
    overall_robustness: dict[str, Any] | None
    coverage: ReviewCoverage


class FinalAssessment(BaseModel):
    source: Literal["senior_synthesis", "deterministic_fallback"]
    headline: str
    overall_assessment: dict[str, Any] | None
    risk_level: str = Field(description="From the deterministic early-warning engine")
    early_warning_index: int
    financial_health: dict[str, Any] = Field(description="Prototype passport score, not credit")
    facts: list[dict[str, Any]]
    calculated_metrics: list[dict[str, Any]]
    forecasts: list[dict[str, Any]]
    assumptions: list[dict[str, Any]]
    interpretations: list[dict[str, Any]]
    challenges_addressed: list[dict[str, Any]]
    disagreements_resolved: list[dict[str, Any]]
    open_questions: list[str]


class ConfidenceAssessment(BaseModel):
    level: ConfidenceLevel
    stated_by_senior_agent: ConfidenceLevel | None
    senior_rationale: str | None
    cap: ConfidenceLevel = Field(description="Ceiling set deterministically by the orchestrator")
    adjustments: list[str] = Field(description="Why the ceiling is where it is")


class ClaimAudit(BaseModel):
    claims_verified: int = Field(description="Claims returned; every one passed verification")
    claims_pruned: int = Field(description="Statements dropped because they could not be verified")
    issues_caught: int = Field(description="Verification issues found across all attempts")
    unmet_requirements: list[str]
    evidence_references_resolve: bool = Field(
        description="Every evidence id cited anywhere exists in the evidence pack"
    )


class EvidencePackRef(BaseModel):
    sha256: str
    items: int
    by_kind: dict[str, int]
    engine_versions: dict[str, str]


InvestigationStatus = Literal["completed", "completed_with_gaps", "failed"]


AgentState = Literal["pending", "running", "succeeded", "failed", "skipped"]
StepState = Literal["pending", "running", "completed", "completed_with_issues", "failed", "skipped"]


class KeyFinding(BaseModel):
    """The agent's headline claim (its summary-level statement), already verified."""

    claim_id: str
    statement: str
    statement_type: str
    confidence: str
    evidence_ids: list[str]


class ChallengeNote(BaseModel):
    """A red-team challenge against one of this agent's claims, and how it was settled."""

    challenger: str = "red_team"
    target_claim_id: str
    severity: str
    summary: str
    resolution: str | None = Field(
        default=None, description="The senior agent's ruling: upheld, partially_upheld, rejected"
    )


class AgentProgress(BaseModel):
    """One agent in the investigation, from its real events."""

    agent: str
    title: str
    focus: str = Field(default="", description="What the agent analyses (its catalogue purpose)")
    state: AgentState = "pending"
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    claims: int | None = None
    attempts: int | None = None
    error: str | None = None
    stance: str | None = None
    key_finding: KeyFinding | None = None
    evidence_ids: list[str] = Field(
        default_factory=list, description="Every evidence item its verified claims cite"
    )
    claim_ids: list[str] = Field(default_factory=list)
    issues_caught: int | None = Field(
        default=None, description="Verification issues found (and fixed or pruned) across attempts"
    )
    pruned: int | None = Field(default=None, description="Statements removed as unverifiable")
    challenges: list[ChallengeNote] = Field(default_factory=list)


class TimelineStep(BaseModel):
    """One of the eight investigation steps shown to users, mapped onto real stages and agents."""

    number: int
    key: str
    title: str
    description: str
    stages: list[StageName] = Field(description="Workflow stages this step covers")
    agents: list[str] = Field(description="Agents that execute this step")
    parallel_group: str | None = Field(
        default=None, description="Steps sharing a group run concurrently"
    )
    state: StepState
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    duration_ms: int | None = None
    highlights: list[str] = Field(description="What the step established, from stage summaries")


class InvestigationTimeline(BaseModel):
    steps: list[TimelineStep]
    agents: list[AgentProgress]


class Investigation(BaseModel):
    investigation_id: uuid.UUID
    entity_id: uuid.UUID
    entity: EntityRef
    as_of: dt.date
    workflow_version: str
    ai_mode: AIMode = Field(
        default="live",
        description="live: answers from the language model. demo_script: scripted demo answers "
        "(still verified), not a model",
    )
    status: InvestigationStatus
    started_at: dt.datetime
    completed_at: dt.datetime
    duration_ms: int
    stages: list[StageRecord]
    triggered_warnings: list[TriggeredWarning]
    risk_summary: dict[str, Any]
    financial_health: dict[str, Any]
    financial_metrics_used: list[MetricUsed]
    agent_analyses: dict[str, AgentRun]
    disagreements: list[Disagreement]
    review_requests: list[ReviewRequest]
    red_team_findings: RedTeamFindings | None
    red_team_run: AgentRun | None
    senior_synthesis_run: AgentRun | None
    final_assessment: FinalAssessment
    recommendations: list[dict[str, Any]]
    confidence: ConfidenceAssessment
    evidence_pack: EvidencePackRef
    evidence_references: list[EvidenceReference]
    claim_audit: ClaimAudit
    usage: Usage
    events: list[InvestigationEvent]
    timeline: InvestigationTimeline | None = Field(
        default=None, description="The eight user-facing steps, rebuilt from stages and events"
    )
    disclaimer: str


class InvestigationSummary(BaseModel):
    investigation_id: uuid.UUID
    entity_id: uuid.UUID
    entity_name: str
    as_of: dt.date
    ai_mode: AIMode = "live"
    status: InvestigationStatus
    risk_level: str
    confidence: ConfidenceLevel
    headline: str
    started_at: dt.datetime
    duration_ms: int

    @classmethod
    def of(cls, inv: Investigation) -> InvestigationSummary:
        return cls(
            investigation_id=inv.investigation_id,
            entity_id=inv.entity_id,
            entity_name=inv.entity.display_name,
            as_of=inv.as_of,
            ai_mode=inv.ai_mode,
            status=inv.status,
            risk_level=inv.final_assessment.risk_level,
            confidence=inv.confidence.level,
            headline=inv.final_assessment.headline,
            started_at=inv.started_at,
            duration_ms=inv.duration_ms,
        )


class ProgressError(BaseModel):
    code: str
    message: str


class InvestigationProgress(BaseModel):
    """A running (or finished) investigation's live state, built from its real events."""

    investigation_id: uuid.UUID
    entity_id: uuid.UUID
    entity_name: str
    as_of: dt.date
    ai_mode: AIMode = "live"
    status: Literal["running", "completed", "failed"]
    started_at: dt.datetime
    updated_at: dt.datetime
    current_stage: StageName | None
    stages: list[StageRecord]
    agents: list[AgentProgress]
    timeline: InvestigationTimeline
    events: list[InvestigationEvent]
    error: ProgressError | None = None
