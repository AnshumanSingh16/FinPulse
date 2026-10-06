"""A scripted stand-in for the language model, and builders of valid agent outputs.

The builders quote evidence text verbatim, so every number in their statements is in the cited
evidence: what a well-behaved model would return.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from functools import cache
from typing import Any

from finpulse.agents.evidence import EvidenceItem, EvidencePack, build_evidence_pack
from finpulse.agents.llm import LLMRequest, LLMResponse
from finpulse.analytics import default_as_of
from finpulse.synthetic import SCENARIOS, generate
from tests.analytics.synthetic_adapter import to_financial_data

TYPES = {
    "fact": "FACT",
    "calculated_metric": "CALCULATED_METRIC",
    "forecast": "FORECAST",
    "assumption": "ASSUMPTION",
}


@cache
def pack_for(code: str = "sharma_electricals") -> EvidencePack:
    data = to_financial_data(generate(SCENARIOS[code]))
    as_of = default_as_of(data)
    assert as_of is not None
    return build_evidence_pack(data, as_of)


def claim(item: EvidenceItem, **extra: Any) -> dict[str, Any]:
    return {
        "statement": item.text,
        "statement_type": TYPES[item.kind],
        "evidence_ids": [item.id],
        "confidence": "high",
        **extra,
    }


def interp(
    items: list[EvidenceItem], text: str = "Taken together, these point the same way.", **extra: Any
) -> dict[str, Any]:
    return {
        "statement": text,
        "statement_type": "AI_INTERPRETATION",
        "evidence_ids": [i.id for i in items],
        "confidence": "medium",
        **extra,
    }


def item(pack: EvidencePack, item_id: str) -> EvidenceItem:
    found = pack.get(item_id)
    assert found is not None, item_id
    return found


def warnings(pack: EvidencePack) -> list[EvidenceItem]:
    return [i for i in pack.select("warning:*") if i.id.count(":") == 1]


def claim_ids(request: LLMRequest) -> list[str]:
    return re.findall(r'"claim_id": "([A-Z]+-\d+)"', request.messages[0]["content"])


def valid_output(
    agent: str, pack: EvidencePack, request: LLMRequest | None = None
) -> dict[str, Any]:
    i = lambda x: item(pack, x)  # noqa: E731
    ws = warnings(pack)
    if agent == "financial_profile":
        return {
            "summary": interp([i("passport:overall"), i("risk:summary")]),
            "strengths": [claim(i("metric:payments.consistency"))],
            "weaknesses": [claim(i("metric:cash.runway")), claim(i("passport:overall"))],
            "data_limitations": [claim(i("fact:data_sources"))],
        }
    if agent == "credit_intelligence":
        return {
            "reliability_view": interp([i("metric:payments.consistency")]),
            "repayment_capacity": [claim(i("metric:debt.service_burden"))],
            "payment_behaviour": [claim(i("metric:payments.consistency"))],
            "alternative_data_signals": [claim(i("metric:income.stability"))],
            "concerns": [claim(i("metric:liquidity.ratio"))],
            "information_gaps": ["Whether the entity has loans outside these records."],
        }
    if agent == "early_warning_investigation":
        return {
            "investigations": [
                {
                    "warning_evidence_id": w.id,
                    "trigger": claim(w),
                    "connected_evidence": [claim(i("metric:liquidity.ratio"))],
                    "likely_explanation": interp([w]),
                    "open_questions": ["Did a large customer delay payment?"],
                }
                for w in ws[:2]
            ],
            "common_thread": interp([i("risk:summary")]),
        }
    if agent == "risk_investigation":
        return {
            "risks": [
                {
                    "title": "Liquidity squeeze",
                    "severity": "high",
                    "risk": claim(i("metric:liquidity.ratio")),
                    "likely_causes": [interp(ws[:1] or [i("risk:summary")])],
                    "evidence_strength": "strong",
                }
            ],
            "overall": interp([i("risk:summary")]),
        }
    if agent == "stress_interpretation":
        return {
            "scenarios": [
                {
                    "scenario_evidence_id": "stress:revenue_down_20",
                    "consequences": [claim(i("stress:revenue_down_20"))],
                    "key_vulnerability": interp([i("stress:revenue_down_20")]),
                }
            ],
            "most_damaging_scenario_evidence_id": "stress:revenue_down_30",
            "resilience_summary": interp([i("stress:baseline")]),
            "assumption_caveats": [claim(i("assumption:stress.method"))],
        }
    ids = claim_ids(request) if request else []
    if agent == "red_team":
        return {
            "challenges": [
                {
                    "target_claim_id": ids[0],
                    "challenge_summary": "Payment behaviour is still clean.",
                    "contradictory_evidence": [claim(i("metric:payments.consistency"))],
                    "missing_information": ["No credit-bureau records are available."],
                    "weak_assumptions": [claim(i("assumption:early_warning.method"))],
                    "alternative_explanations": [interp([i("metric:revenue.volatility")])],
                    "severity": "moderate",
                }
            ],
            "overall_robustness": interp([i("risk:summary")]),
        }
    if agent == "senior_synthesis":
        target = re.findall(r'"target_claim_id": "([A-Z]+-\d+)"', request.messages[0]["content"])
        return {
            "headline": "The business is deteriorating while its repayment record looks clean.",
            "overall_assessment": interp([i("risk:summary")], based_on_claims=ids[:1]),
            "facts": [claim(i("fact:data_coverage"), based_on_claims=[])],
            "calculated_metrics": [claim(i("metric:liquidity.ratio"), based_on_claims=ids[:2])],
            "forecasts": [claim(i("stress:revenue_down_20"), based_on_claims=[])],
            "assumptions": [claim(i("assumption:stress.method"), based_on_claims=[])],
            "interpretations": [interp([i("passport:overall")], based_on_claims=[])],
            "challenges_addressed": [
                {
                    "target_claim_id": t,
                    "resolution": "partially_upheld",
                    "explanation": interp([i("metric:payments.consistency")], based_on_claims=[]),
                }
                for t in target[:1]
            ],
            "open_questions": ["Will the largest customer resume orders?"],
            "confidence": "medium",
            "confidence_rationale": "The data is synthetic and covers a limited period.",
        }
    raise AssertionError(agent)


Script = str | dict[str, Any] | Exception | Callable[[LLMRequest], Any]


class FakeLLM:
    """Answers per agent from a script; when the script runs out, answers validly."""

    model = "fake-model"

    def __init__(self, pack: EvidencePack, script: dict[str, list[Script]] | None = None) -> None:
        self.pack = pack
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.requests: list[LLMRequest] = []

    def calls(self, agent: str) -> list[LLMRequest]:
        return [r for r in self.requests if r.metadata["agent"] == agent]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        agent = request.metadata["agent"]
        queue = self.script.get(agent)
        answer: Any = queue.pop(0) if queue else (lambda r: valid_output(agent, self.pack, r))
        if callable(answer) and not isinstance(answer, Exception):
            answer = answer(request)
        if isinstance(answer, Exception):
            raise answer
        text = answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)
        return LLMResponse(
            text=text,
            model=self.model,
            stop_reason="end_turn",
            input_tokens=1000,
            output_tokens=200,
        )
