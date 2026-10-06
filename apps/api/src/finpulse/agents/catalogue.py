"""The seven agents: what each sees, what it must return and how its output is checked."""

from __future__ import annotations

from finpulse.agents import prompts
from finpulse.agents.base import AgentSpec
from finpulse.agents.evidence import EvidenceItem, EvidencePack
from finpulse.agents.schemas import (
    CreditIntelligenceOutput,
    EarlyWarningInvestigationOutput,
    FinancialProfileOutput,
    RedTeamOutput,
    RiskInvestigationOutput,
    SeniorSynthesisOutput,
    StressInterpretationOutput,
)
from finpulse.agents.verifier import VerifyRules

CREDIT_METRICS = (
    "metric:debt.*",
    "metric:payments.consistency",
    "metric:cashflow.*",
    "metric:income.stability",
    "metric:liquidity.*",
    "metric:cash.*",
    "metric:buffer.months",
    "metric:transactions.consistency",
    "metric:revenue.*",
    "metric:receivables.*",
)
STRESS_METRICS = (
    "metric:cash.*",
    "metric:liquidity.*",
    "metric:buffer.months",
    "metric:debt.*",
    "metric:revenue.monthly",
    "metric:expenses.monthly",
    "metric:cashflow.net_monthly",
    "metric:customers.concentration",
    "metric:suppliers.concentration",
)


def _warnings(pack: EvidencePack, categories: set[str] | None = None) -> list[EvidenceItem]:
    return [
        i
        for i in pack.select("warning:*")
        if categories is None or (i.tags and i.tags[0] in categories)
    ]


def _profile(pack: EvidencePack) -> list[EvidenceItem]:
    return pack.select(
        "fact:*",
        "metric:*",
        "passport:overall",
        "passport:dimension:*",
        "passport:change",
        "risk:summary",
        "assumption:passport.method",
    )


def _credit(pack: EvidencePack) -> list[EvidenceItem]:
    return [
        *pack.select(
            "fact:*", *CREDIT_METRICS, "passport:*", "risk:summary", "assumption:passport.method"
        ),
        *_warnings(pack, {"debt", "cash", "liquidity", "receivables"}),
    ]


def _warning_investigation(pack: EvidencePack) -> list[EvidenceItem]:
    return [
        *pack.select(
            "fact:*",
            "metric:*",
            "passport:overall",
            "passport:change",
            "risk:*",
            "assumption:early_warning.method",
        ),
        *_warnings(pack),
    ]


def _risk(pack: EvidencePack) -> list[EvidenceItem]:
    scenarios = [i for i in pack.select("stress:*") if "scenario_detail" not in i.tags]
    return [
        *pack.select(
            "fact:*",
            "metric:*",
            "passport:overall",
            "passport:dimension:*",
            "passport:change",
            "risk:*",
            "assumption:early_warning.method",
            "assumption:stress.method",
        ),
        *[i for i in _warnings(pack) if i.id.count(":") == 1],  # the warnings, not their detail
        *scenarios,
    ]


def _stress(pack: EvidencePack) -> list[EvidenceItem]:
    return pack.select(
        "fact:entity",
        "fact:accounts",
        "fact:data_sources",
        *STRESS_METRICS,
        "passport:overall",
        "stress:*",
        "assumption:stress.*",
    )


def _everything(pack: EvidencePack) -> list[EvidenceItem]:
    return list(pack.items)


ANALYSTS = (
    "financial_profile",
    "credit_intelligence",
    "early_warning_investigation",
    "risk_investigation",
    "stress_interpretation",
)

AGENTS: dict[str, AgentSpec] = {
    spec.name: spec
    for spec in (
        AgentSpec(
            name="financial_profile",
            title="Financial Profile Agent",
            purpose="Summarises the entity's financial condition, strengths and weaknesses.",
            output_model=FinancialProfileOutput,
            role=prompts.FINANCIAL_PROFILE,
            select=_profile,
            claim_prefix="PRO",
        ),
        AgentSpec(
            name="credit_intelligence",
            title="Credit Intelligence Agent",
            purpose="Analyses evidence of financial reliability and repayment capacity where "
            "traditional credit history is limited.",
            output_model=CreditIntelligenceOutput,
            role=prompts.CREDIT_INTELLIGENCE,
            select=_credit,
            claim_prefix="CRE",
        ),
        AgentSpec(
            name="early_warning_investigation",
            title="Early Warning Investigation Agent",
            purpose="Investigates why each early-warning signal was triggered, connecting "
            "multiple pieces of evidence.",
            output_model=EarlyWarningInvestigationOutput,
            role=prompts.EARLY_WARNING_INVESTIGATION,
            select=_warning_investigation,
            claim_prefix="EWI",
            rules=VerifyRules(evidence_ref_fields={"warning_evidence_id": "warning:"}),
        ),
        AgentSpec(
            name="risk_investigation",
            title="Risk Investigation Agent",
            purpose="Determines the most important financial risks and their likely causes.",
            output_model=RiskInvestigationOutput,
            role=prompts.RISK_INVESTIGATION,
            select=_risk,
            claim_prefix="RSK",
        ),
        AgentSpec(
            name="stress_interpretation",
            title="Stress-Test Interpretation Agent",
            purpose="Explains the consequences of the deterministic stress-test results.",
            output_model=StressInterpretationOutput,
            role=prompts.STRESS_INTERPRETATION,
            select=_stress,
            claim_prefix="STR",
            rules=VerifyRules(
                evidence_ref_fields={
                    "scenario_evidence_id": "stress:",
                    "most_damaging_scenario_evidence_id": "stress:",
                }
            ),
        ),
        AgentSpec(
            name="red_team",
            title="Red-Team Agent",
            purpose="Challenges the other agents' conclusions: contradictory evidence, missing "
            "information, weak assumptions and alternative explanations.",
            output_model=RedTeamOutput,
            role=prompts.RED_TEAM,
            select=_everything,
            claim_prefix="RED",
            depends_on=ANALYSTS,
        ),
        AgentSpec(
            name="senior_synthesis",
            title="Senior Financial Intelligence Agent",
            purpose="Synthesises the verified outputs of the other agents, separating facts, "
            "calculated metrics, forecasts, assumptions and AI interpretation.",
            output_model=SeniorSynthesisOutput,
            role=prompts.SENIOR,
            select=_everything,
            claim_prefix="SEN",
            depends_on=(*ANALYSTS, "red_team"),
            rules=VerifyRules(
                section_types={
                    "facts": "FACT",
                    "calculated_metrics": "CALCULATED_METRIC",
                    "forecasts": "FORECAST",
                    "assumptions": "ASSUMPTION",
                    "interpretations": "AI_INTERPRETATION",
                    "overall_assessment": "AI_INTERPRETATION",
                }
            ),
        ),
    )
}
