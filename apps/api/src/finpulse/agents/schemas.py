"""Structured outputs of the agents (what the model must return) and of the agent layer.

Every substantive statement an agent makes is a ``Claim``: the statement, what kind of
statement it is, the evidence ids it rests on, and how sure the agent is. The model's JSON is
constrained to these schemas (structured outputs) and then checked by the deterministic
verifier before anything downstream sees it.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finpulse.analytics.schemas import EntityRef

StatementType = Literal["FACT", "CALCULATED_METRIC", "FORECAST", "ASSUMPTION", "AI_INTERPRETATION"]
Confidence = Literal["high", "medium", "low"]
Severity = Literal["low", "medium", "high", "critical"]


class _Out(BaseModel):
    """Model-facing: every field required, no extras (a requirement of structured outputs)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Claim(_Out):
    statement: str = Field(description="One or two plain sentences")
    statement_type: StatementType
    evidence_ids: list[str] = Field(description="Ids of the evidence items this rests on")
    confidence: Confidence


class SynthesisClaim(Claim):
    based_on_claims: list[str] = Field(
        description="Ids of the upstream agents' verified claims this builds on (may be empty)"
    )


# --- 1. Financial Profile ------------------------------------------------------------------------


class FinancialProfileOutput(_Out):
    summary: Claim = Field(description="Overall financial condition (AI_INTERPRETATION)")
    strengths: list[Claim]
    weaknesses: list[Claim]
    data_limitations: list[Claim] = Field(description="What the data does not show or cover")


# --- 2. Credit Intelligence ----------------------------------------------------------------------


class CreditIntelligenceOutput(_Out):
    reliability_view: Claim = Field(
        description="Overall view of financial reliability (AI_INTERPRETATION); never a credit "
        "decision or score"
    )
    repayment_capacity: list[Claim]
    payment_behaviour: list[Claim]
    alternative_data_signals: list[Claim] = Field(
        description="Evidence usable where traditional credit history is thin or absent"
    )
    concerns: list[Claim]
    information_gaps: list[str]


# --- 3. Early Warning Investigation ------------------------------------------------------------


class WarningInvestigation(_Out):
    warning_evidence_id: str = Field(description='The warning investigated, "warning:EW-…"')
    trigger: Claim = Field(description="What crossed which threshold (CALCULATED_METRIC)")
    connected_evidence: list[Claim] = Field(
        description="Other evidence that bears on the warning: corroborating or related"
    )
    likely_explanation: Claim = Field(description="Most likely cause (AI_INTERPRETATION)")
    open_questions: list[str]


class EarlyWarningInvestigationOutput(_Out):
    investigations: list[WarningInvestigation]
    common_thread: Claim = Field(description="How the warnings connect (AI_INTERPRETATION)")


# --- 4. Risk Investigation ---------------------------------------------------------------------


class RiskItem(_Out):
    title: str
    severity: Severity
    risk: Claim
    likely_causes: list[Claim]
    evidence_strength: Literal["strong", "moderate", "weak"]


class RiskInvestigationOutput(_Out):
    risks: list[RiskItem] = Field(description="Most important first")
    overall: Claim


# --- 5. Stress-Test Interpretation ---------------------------------------------------------------


class ScenarioInterpretation(_Out):
    scenario_evidence_id: str = Field(description='The scenario, "stress:<preset>"')
    consequences: list[Claim]
    key_vulnerability: Claim


class StressInterpretationOutput(_Out):
    scenarios: list[ScenarioInterpretation]
    most_damaging_scenario_evidence_id: str
    resilience_summary: Claim
    assumption_caveats: list[Claim] = Field(description="Which assumptions most limit the results")


# --- 6. Red Team -------------------------------------------------------------------------------


class Challenge(_Out):
    target_claim_id: str = Field(description="Id of the upstream claim being challenged")
    challenge_summary: str
    contradictory_evidence: list[Claim]
    missing_information: list[str]
    weak_assumptions: list[Claim]
    alternative_explanations: list[Claim]
    severity: Literal["major", "moderate", "minor"]


class RedTeamOutput(_Out):
    challenges: list[Challenge]
    overall_robustness: Claim


# --- 7. Senior Financial Intelligence ------------------------------------------------------------


class ChallengeResponse(_Out):
    target_claim_id: str = Field(description="The challenged claim")
    resolution: Literal["upheld", "partially_upheld", "rejected"]
    explanation: SynthesisClaim


class SeniorSynthesisOutput(_Out):
    headline: str
    overall_assessment: SynthesisClaim = Field(description="AI_INTERPRETATION")
    facts: list[SynthesisClaim] = Field(description="FACT claims only")
    calculated_metrics: list[SynthesisClaim] = Field(description="CALCULATED_METRIC claims only")
    forecasts: list[SynthesisClaim] = Field(description="FORECAST claims only")
    assumptions: list[SynthesisClaim] = Field(description="ASSUMPTION claims only")
    interpretations: list[SynthesisClaim] = Field(description="AI_INTERPRETATION claims only")
    challenges_addressed: list[ChallengeResponse]
    open_questions: list[str]
    confidence: Confidence
    confidence_rationale: str


# --- the agent layer's own outputs -------------------------------------------------------------

IssueCode = Literal[
    "unknown_evidence_id",
    "missing_citation",
    "type_not_supported",
    "unsupported_number",
    "wrong_section_type",
    "unknown_claim_id",
    "wrong_reference_kind",
]


class Issue(BaseModel):
    path: str = Field(description='Where in the output, e.g. "weaknesses[1].statement"')
    code: IssueCode
    detail: str


class VerificationReport(BaseModel):
    passed: bool
    claims_checked: int
    numbers_checked: int
    issues: list[Issue] = Field(description="Issues in the final output (empty when passed)")
    pruned: list[str] = Field(
        default_factory=list,
        description="Statements removed because they still failed after the repair attempts",
    )
    attempts_issues: list[list[Issue]] = Field(
        default_factory=list, description="Issues found at each attempt, for audit"
    )


class RegisteredClaim(BaseModel):
    claim_id: str = Field(description='Stable within a run, e.g. "RSK-03"')
    agent: str
    path: str
    statement: str
    statement_type: StatementType
    evidence_ids: list[str]
    confidence: Confidence


class AgentErrorInfo(BaseModel):
    code: str
    message: str


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0


AgentStatus = Literal["succeeded", "failed", "skipped"]


class AgentRun(BaseModel):
    agent: str
    title: str
    status: AgentStatus
    output: dict[str, Any] | None = Field(description="The agent's verified output")
    claims: list[RegisteredClaim] = Field(default_factory=list)
    verification: VerificationReport | None = None
    error: AgentErrorInfo | None = None
    model: str | None = None
    prompt_version: str
    evidence_items: int = Field(description="Number of evidence items the agent was given")
    attempts: int = 0
    usage: Usage = Field(default_factory=Usage)


class IntelligenceReport(BaseModel):
    entity: EntityRef
    as_of: dt.date
    status: Literal["complete", "partial", "failed"]
    evidence_pack_sha256: str
    evidence_items: int
    agents: dict[str, AgentRun]
    synthesis: dict[str, Any] | None = Field(
        description="The Senior Financial Intelligence Agent's verified synthesis"
    )
    usage: Usage
    disclaimer: str


class AgentInfo(BaseModel):
    name: str
    title: str
    purpose: str
    depends_on: list[str]
    prompt_version: str
    output_schema: dict[str, Any]
