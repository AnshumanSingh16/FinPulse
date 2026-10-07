"""A scripted, deterministic stand-in for the language model, for the Sharma Electricals demo.

``DemoScriptLLM`` implements the same ``LLMClient`` interface as the Claude client, so the real
orchestrator, the real agents' schemas, the deterministic verifier, disagreement detection and
the red-team requirements all run unchanged. Only the model's answers are replaced: for each
agent the script writes a fixed analysis of the demo story, and every number in it is taken from
the evidence in the agent's own prompt (formatted the way the verifier reads numbers), so the
output is verified exactly as a live model's would be.

What this is NOT: a model. The analysis was written in advance for one entity and one story; it
does not reason about the data beyond reading the values it quotes. Investigations it produces
are marked ``ai_mode = "demo_script"`` and the UI labels them as scripted. It refuses any entity
other than the demo entity.

Responses are paced with a fixed delay per agent (``DEMO_SCRIPT_PACE`` seconds × a per-agent
factor) so the live timeline can be watched; the pacing is disclosed in the UI.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from finpulse.agents.llm import LLMRequest, LLMResponse
from finpulse.core.errors import LLMUnavailableError

DEMO_MODEL = "finpulse-demo-script-1"
DEMO_ENTITY = "Sharma Electricals"
# Relative pacing per agent, so the concurrent specialists finish one after another.
PACE = {
    "financial_profile": 2.6,
    "credit_intelligence": 3.4,
    "early_warning_investigation": 4.6,
    "risk_investigation": 5.4,
    "stress_interpretation": 3.9,
    "red_team": 4.2,
    "senior_synthesis": 4.8,
}

Claim = dict[str, Any]


class DemoScriptError(LLMUnavailableError):
    """The demo script cannot answer this request (another entity, or its evidence is missing)."""


# --- reading the prompt ---------------------------------------------------------------------


@dataclass
class Prompt:
    entity: str
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    claims: list[dict[str, Any]] = field(default_factory=list)
    challenges: list[dict[str, Any]] = field(default_factory=list)
    sections: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def item(self, eid: str) -> dict[str, Any]:
        found = self.evidence.get(eid)
        if found is None:
            raise DemoScriptError(f"The demo script needs evidence {eid!r}, which is missing.")
        return found

    def value(self, eid: str, key: str = "value") -> Decimal:
        raw = self.item(eid)["values"].get(key)
        if raw is None:
            raise DemoScriptError(f"The demo script needs {eid}:{key}, which is missing.")
        return Decimal(str(raw))

    def warning(self, rule: str) -> str | None:
        """The id of the active warning raised by ``rule``, if any."""
        for eid, item in self.evidence.items():
            is_warning = eid.startswith("warning:") and eid.count(":") == 1
            if is_warning and item["values"].get("rule") == rule:
                return eid
        return None

    def claims_of(self, prefix: str) -> list[dict[str, Any]]:
        return [c for c in self.claims if str(c["claim_id"]).startswith(prefix + "-")]

    def first(self, prefix: str) -> list[str]:
        found = self.claims_of(prefix)
        return [found[0]["claim_id"]] if found else []


def _block(lines: list[str], tag: str) -> list[list[dict[str, Any]]]:
    out: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] | None = None
    for line in lines:
        if line == f"<{tag}>":
            current = []
        elif line == f"</{tag}>":
            if current is not None:
                out.append(current)
            current = None
        elif current is not None and line.strip():
            current.append(json.loads(line))
    return out


def parse(text: str) -> Prompt:
    lines = text.split("\n")
    entity = lines[1] if len(lines) > 1 else ""
    prompt = Prompt(entity=entity)
    for rows in _block(lines, "evidence"):
        prompt.evidence.update({r["id"]: r for r in rows})
    for rows in _block(lines, "claims"):
        prompt.claims.extend(rows)
    for rows in _block(lines, "challenges"):
        prompt.challenges.extend(rows)
    # Context sections: "## <title>" followed (after an instruction line) by a <context> block.
    title = ""
    for i, line in enumerate(lines):
        if line.startswith("## "):
            title = line[3:]
        elif line == "<context>":
            end = lines.index("</context>", i)
            prompt.sections[title] = [json.loads(x) for x in lines[i + 1 : end] if x.strip()]
    return prompt


# --- writing numbers the way the evidence (and the verifier) reads them ---------------------


def _int(v: Decimal) -> int:
    return int(v.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def inr(v: Decimal) -> str:
    """₹14,82,538 (Indian digit grouping); negative as -₹2,50,470."""
    n = abs(_int(v))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-₹" if v < 0 else "₹") + s


def lakh(v: Decimal) -> str:
    return f"₹{(v / Decimal(100_000)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)} lakh"


def pct(ratio: Decimal, places: str = "0.1") -> str:
    return f"{(ratio * 100).quantize(Decimal(places), rounding=ROUND_HALF_UP)}%"


def num(v: Decimal, places: str = "0.1") -> str:
    return str(v.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def claim(statement: str, kind: str, ids: list[str], confidence: str = "high") -> Claim:
    return {
        "statement": statement,
        "statement_type": kind,
        "evidence_ids": ids,
        "confidence": confidence,
    }


def synth(
    statement: str, kind: str, ids: list[str], based_on: list[str], conf: str = "high"
) -> Claim:
    return {**claim(statement, kind, ids, conf), "based_on_claims": based_on}


CM, FACT, FORECAST, ASSUMPTION, AI = (
    "CALCULATED_METRIC",
    "FACT",
    "FORECAST",
    "ASSUMPTION",
    "AI_INTERPRETATION",
)
S60 = "stress:major_customer_stops_paying_60_days"
S90 = "stress:major_customer_stops_paying_90_days"


# --- the story, agent by agent ----------------------------------------------------------------


class Facts:
    """Figures several agents quote, formatted on first use from the agent's own evidence. An
    agent only sees part of the evidence pack, so a figure it was not given raises
    ``DemoScriptError`` instead of being invented."""

    def __init__(self, p: Prompt) -> None:
        self.p = p
        self.liq = p.warning("liquidity_deterioration")

    def __getitem__(self, key: str) -> str:
        p, liq = self.p, self.liq
        sub = (lambda name: f"{liq}:{name}") if liq else (lambda name: "missing:" + name)
        getters: dict[str, Callable[[], str]] = {
            "growth": lambda: pct(p.value("metric:revenue.growth")),
            "revenue": lambda: inr(p.value("metric:revenue.monthly")),
            "receivables": lambda: inr(p.value("metric:receivables.outstanding")),
            "not_due": lambda: inr(p.value("metric:receivables.outstanding", "not_yet_due")),
            "dso": lambda: num(p.value("metric:receivables.days")),
            "cash": lambda: inr(p.value("metric:cash.balance")),
            "od_limit": lambda: lakh(p.value("metric:cash.balance", "overdraft_limit")),
            "concentration": lambda: pct(p.value("metric:customers.concentration")),
            "largest": lambda: str(p.item("metric:customers.concentration")["values"]["largest"]),
            "consistency": lambda: pct(p.value("metric:payments.consistency")),
            "burden": lambda: pct(p.value("metric:debt.service_burden")),
            "debt": lambda: lakh(p.value("metric:debt.outstanding")),
            "ratio": lambda: f"{num(p.value('metric:liquidity.ratio'), '0.01')}×",
            "cash_then": lambda: inr(p.value(sub("cash_average"), "then")),
            "cash_now": lambda: inr(p.value(sub("cash_average"), "now")),
            "rec_then": lambda: inr(p.value(sub("receivables_then"))),
            "dso_then": lambda: num(p.value(sub("collection_days"), "then")),
            "overdue": lambda: pct(p.value(sub("receivables_now"), "overdue_share"), "1"),
        }
        return getters[key]()


def _facts(p: Prompt) -> Facts:
    return Facts(p)


def possessive(name: str) -> str:
    return name + ("'" if name.endswith("s") else "'s")


def first_sentence(text: str) -> str:
    """Up to the first full stop that ends a sentence (not the one in "10.6")."""
    return re.split(r"(?<=\.)\s+(?=[A-Z0-9])", text, maxsplit=1)[0]


def sentence(p: Prompt, warning_id: str) -> str:
    """A warning's finding in the engine's own words, without its "[SEVERITY] Title." prefix."""
    text = str(p.item(warning_id)["text"])
    return re.sub(r"^\[[A-Z]+\] [^.]+\. ", "", text).split(" Measure:")[0]


def financial_profile(p: Prompt) -> dict[str, Any]:
    f = _facts(p)
    positive = _int(p.value("metric:cashflow.positive_months", "cash_positive_months"))
    return {
        "risk_stance": "elevated",
        "summary": claim(
            f"Sharma Electricals is growing — revenue rose {f['growth']} over the last three "
            f"months, to {f['revenue']} in September — but the growth is being paid for out of "
            f"its own cash: receivables have built up to {f['receivables']} while the bank "
            f"balance is {f['cash']}.",
            AI,
            [
                "metric:revenue.growth",
                "metric:revenue.monthly",
                "metric:receivables.outstanding",
                "metric:cash.balance",
            ],
            "medium",
        ),
        "strengths": [
            claim(
                f"Revenue grew {f['growth']} in the last three months against the three before.",
                CM,
                ["metric:revenue.growth"],
            ),
            claim(
                f"Every loan instalment and supplier bill in the last 12 months was paid on time: "
                f"payment consistency is {f['consistency']}.",
                CM,
                ["metric:payments.consistency"],
            ),
        ],
        "weaknesses": [
            claim(
                f"Net cash margin over the last six months is "
                f"{pct(p.value('metric:cashflow.net_margin'))}: more cash went out than came in, "
                f"and only {positive} of the last 6 months were cash-positive.",
                CM,
                ["metric:cashflow.net_margin", "metric:cashflow.positive_months"],
            ),
            claim(
                f"Own cash covers {num(p.value('metric:buffer.months'))} months of outgoings.",
                CM,
                ["metric:buffer.months"],
            ),
            claim(
                f"Receivable days are {f['dso']}: customers take about a month and a half to pay.",
                CM,
                ["metric:receivables.days"],
            ),
        ],
        "data_limitations": [
            claim(
                "FinPulse sees bank, invoice, bill and loan records only; there is no "
                "credit-bureau data and nothing on the customers' own finances.",
                FACT,
                ["fact:data_sources"],
            )
        ],
    }


def credit_intelligence(p: Prompt) -> dict[str, Any]:
    f = _facts(p)
    liq = p.warning("liquidity_deterioration")
    return {
        "risk_stance": "low",
        "reliability_view": claim(
            f"On its repayment record Sharma Electricals looks reliable: every obligation in the "
            f"last 12 months was paid on time ({f['consistency']}), debt is small (about "
            f"{f['debt']} outstanding) and repayments take {f['burden']} of receipts.",
            AI,
            [
                "metric:payments.consistency",
                "metric:debt.outstanding",
                "metric:debt.service_burden",
            ],
            "medium",
        ),
        "repayment_capacity": [
            claim(
                f"Loan instalments take {f['burden']} of operating receipts.",
                CM,
                ["metric:debt.service_burden"],
            )
        ],
        "payment_behaviour": [
            claim(
                f"Payment consistency is {f['consistency']} over the last 12 months.",
                CM,
                ["metric:payments.consistency"],
            )
        ],
        "alternative_data_signals": [
            claim(
                f"Income stability is {num(p.value('metric:income.stability'))}/100: money has "
                "come in every month of the last six.",
                CM,
                ["metric:income.stability"],
            ),
            claim(
                "The traditional credit footprint is thin: one bank loan on record and no new "
                "borrowing in the last six months.",
                CM,
                ["metric:debt.new_loans_6m"],
            ),
        ],
        "concerns": [
            claim(
                f"Cash is moving into receivables: the average balance fell from "
                f"{f['cash_then']} to {f['cash_now']} while receivables rose from "
                f"{f['rec_then']} to {f['receivables']}.",
                CM,
                [
                    *([liq, f"{liq}:cash_average", f"{liq}:receivables_then"] if liq else []),
                    "metric:receivables.outstanding",
                ],
            )
        ]
        if liq
        else [],
        "information_gaps": [
            "No credit-bureau report: one bank loan is the only traditional credit history.",
            "Nothing in the records shows the largest customer's own financial position.",
        ],
    }


def early_warning_investigation(p: Prompt) -> dict[str, Any]:
    f = _facts(p)
    investigations: list[dict[str, Any]] = []
    rules = [
        (
            "liquidity_deterioration",
            "The builder's larger, slower-paying orders are absorbing the business's cash: it is "
            "extending more credit to one customer just as that customer pays later.",
            ["metric:customers.concentration"],
        ),
        (
            "receivables_growth",
            "Receivables are growing faster than sales because collections are slowing, not only "
            "because the business is selling more.",
            ["metric:receivables.days"],
        ),
        (
            "delayed_collections",
            "Customers — above all the largest — are paying further past their due dates.",
            ["metric:customers.concentration"],
        ),
        (
            "receivable_days_increase",
            "Collection time is lengthening as a growing share of sales goes to a customer that "
            "pays late.",
            ["metric:customers.concentration"],
        ),
        (
            "customer_concentration",
            "One builder's housing project is driving the business's growth, so its share of "
            "revenue keeps rising.",
            ["metric:revenue.growth"],
        ),
    ]
    found: list[str] = []
    for rule, explanation, connected in rules:
        wid = p.warning(rule)
        if wid is None:
            continue
        found.append(wid)
        trigger = sentence(p, wid)
        investigations.append(
            {
                "warning_evidence_id": wid,
                "trigger": claim(trigger, CM, [wid]),
                "connected_evidence": [
                    claim(
                        f"Receivable days are {f['dso']}; {f['largest']} is "
                        f"{f['concentration']} of revenue.",
                        CM,
                        ["metric:receivables.days", "metric:customers.concentration"],
                    )
                ],
                "likely_explanation": claim(explanation, AI, [wid, *connected], "medium"),
                "open_questions": [f"Has {f['largest']} changed its own payment cycle?"],
            }
        )
    if not found:
        raise DemoScriptError("The demo script expects the demo story's early warnings.")
    return {
        "risk_stance": "elevated",
        "investigations": investigations,
        "common_thread": claim(
            f"All of these warnings trace back to one customer: {f['largest']} is buying more and "
            "paying later, which lengthens collection time, grows receivables and draws down "
            "cash.",
            AI,
            [*found, "metric:customers.concentration"],
            "medium",
        ),
    }


def risk_investigation(p: Prompt) -> dict[str, Any]:
    f = _facts(p)
    liq = p.warning("liquidity_deterioration")
    conc = p.warning("customer_concentration")
    late = p.warning("delayed_collections")
    rec = p.warning("receivables_growth")
    risks = []
    if liq:
        risks.append(
            {
                "title": "Cash absorbed by receivables",
                "severity": "high",
                "risk": claim(sentence(p, liq).split(" Collection time")[0], CM, [liq]),
                "likely_causes": [
                    claim(
                        f"Sales to {f['largest']} are growing and are paid later, so more of the "
                        "business's working capital sits in its invoices.",
                        AI,
                        [x for x in (rec, "metric:customers.concentration") if x],
                        "medium",
                    )
                ],
                "evidence_strength": "strong",
            }
        )
    if conc:
        risks.append(
            {
                "title": f"Dependence on {f['largest']}",
                "severity": "medium",
                "risk": claim(
                    f"{f['largest']} is {f['concentration']} of revenue over the last six months.",
                    CM,
                    ["metric:customers.concentration", conc],
                ),
                "likely_causes": [
                    claim(
                        "A single large housing project is driving the business's growth.",
                        AI,
                        [conc],
                        "medium",
                    )
                ],
                "evidence_strength": "strong",
            }
        )
    if late:
        risks.append(
            {
                "title": "Slowing collections",
                "severity": "medium",
                "risk": claim(
                    f"{first_sentence(sentence(p, late))} Receivable days are {f['dso']}.",
                    CM,
                    [late, "metric:receivables.days"],
                ),
                "likely_causes": [
                    claim(
                        "The largest customer pays further past its due dates.",
                        AI,
                        [late],
                        "medium",
                    )
                ],
                "evidence_strength": "moderate",
            }
        )
    return {
        "risk_stance": "elevated",
        "risks": risks,
        "overall": claim(
            "The business is vulnerable rather than in distress: its liquidity now depends on "
            "one builder paying on time, and that builder is paying later.",
            AI,
            [x for x in (liq, "metric:customers.concentration", "risk:summary") if x],
            "medium",
        ),
    }


def stress_interpretation(p: Prompt) -> dict[str, Any]:
    shock = f"{S60}:shock.customer_payment_stop"
    customer = str(p.item(shock)["values"]["customer"])
    scenarios = [
        {
            "scenario_evidence_id": S60,
            "consequences": [
                claim(
                    f"If {customer} pays nothing for 60 days, "
                    f"{inr(p.value(shock, 'withheld'))} is withheld and the account is overdrawn "
                    f"at its lowest, {inr(p.value(f'{S60}:outcome.cash', 'scenario_minimum'))} in "
                    "Nov 2026; projected risk rises from low to high.",
                    FORECAST,
                    [shock, f"{S60}:outcome.cash", f"{S60}:outcome.risk"],
                )
            ],
            "key_vulnerability": claim(
                "A single customer's payment timing can take the business into its overdraft: "
                "a 20% fall in revenue does less damage.",
                AI,
                [S60, "stress:revenue_down_20"],
                "medium",
            ),
        },
        {
            "scenario_evidence_id": S90,
            "consequences": [
                claim(
                    "A 90-day delay exhausts the overdraft: funds run out around 2026-12-16 and "
                    "projected risk becomes critical.",
                    FORECAST,
                    [S90, f"{S90}:outcome.failure_point"],
                )
            ],
            "key_vulnerability": claim(
                "The overdraft absorbs a 60-day delay but not a 90-day one.",
                AI,
                [S60, S90],
                "medium",
            ),
        },
        {
            "scenario_evidence_id": "stress:revenue_down_20",
            "consequences": [
                claim(
                    "A 20% fall in revenue lowers closing cash but keeps projected risk low.",
                    FORECAST,
                    ["stress:revenue_down_20"],
                )
            ],
            "key_vulnerability": claim(
                "The business is more exposed to how fast it is paid than to how much it sells.",
                AI,
                ["stress:revenue_down_20", S60],
                "medium",
            ),
        },
    ]
    return {
        "risk_stance": "elevated",
        "scenarios": scenarios,
        "most_damaging_scenario_evidence_id": S90,
        "resilience_summary": claim(
            "With no shock the six-month outlook stays low risk, but the business is fragile to "
            f"one event: {customer} paying late. A 60-day delay takes the account into its "
            "overdraft and a 90-day delay exhausts it.",
            AI,
            ["stress:baseline", f"{S60}:outcome.risk", f"{S90}:outcome.failure_point"],
            "medium",
        ),
        "assumption_caveats": [
            claim(
                "The projections repeat the last three months with no seasonality, so they do not "
                "capture the builder paying later still.",
                ASSUMPTION,
                ["assumption:stress.method"],
            )
        ],
    }


def _challenge(p: Prompt, target: dict[str, Any]) -> dict[str, Any]:
    f = _facts(p)
    agent = str(target.get("agent", ""))
    tid = str(target["claim_id"])
    concentration = claim(
        f"{f['largest']} is {f['concentration']} of revenue.",
        CM,
        ["metric:customers.concentration"],
    )
    sixty = claim(
        f"A 60-day payment delay from {f['largest']} takes the account to "
        f"{inr(p.value(f'{S60}:outcome.cash', 'scenario_minimum'))} at its lowest.",
        FORECAST,
        [f"{S60}:outcome.cash"],
    )
    if agent == "credit_intelligence":
        return {
            "target_claim_id": tid,
            "challenge_summary": "A clean repayment record does not show capacity under stress: "
            "the business has never been tested by a cash shortfall, and one customer can create "
            "one.",
            "contradictory_evidence": [concentration, sixty],
            "missing_information": [
                "A credit-bureau report: one bank loan is the only traditional credit history."
            ],
            "weak_assumptions": [
                claim(
                    f"The view assumes the small loan (about {f['debt']} outstanding) is what "
                    "matters; the larger exposure is the credit the business itself extends.",
                    AI,
                    ["metric:debt.outstanding", "metric:receivables.outstanding"],
                    "medium",
                )
            ],
            "alternative_explanations": [],
            "severity": "major",
        }
    if agent == "stress_interpretation":
        late = p.warning("delayed_collections")
        late_days = num(p.value(late, "current_value")) if late else ""
        return {
            "target_claim_id": tid,
            "challenge_summary": "The baseline may be optimistic: it repeats the last three "
            "months, but the builder has been paying later through them.",
            "contradictory_evidence": [
                claim(
                    f"Customers paid {late_days} days late on average in the last 90 days, more "
                    "than before.",
                    CM,
                    [p.warning("delayed_collections") or "metric:receivables.days"],
                )
            ]
            if p.warning("delayed_collections")
            else [],
            "missing_information": [],
            "weak_assumptions": [
                claim(
                    "The projection assumes no further slowdown in collections.",
                    ASSUMPTION,
                    ["assumption:stress.method"],
                )
            ],
            "alternative_explanations": [],
            "severity": "minor",
        }
    # The risk, warning and profile conclusions: what weakens them.
    return {
        "target_claim_id": tid,
        "challenge_summary": "The evidence shows strain, not distress: every obligation is paid "
        "on time, nothing is more than a month overdue, and liquidity looks comfortable on paper.",
        "contradictory_evidence": [
            claim(
                f"Payment consistency is {f['consistency']}: every loan instalment and supplier "
                "bill was paid on time.",
                CM,
                ["metric:payments.consistency"],
            ),
            claim(
                f"None of the {f['receivables']} of receivables is more than a month overdue; "
                f"{f['not_due']} is not yet due.",
                CM,
                ["metric:receivables.outstanding"],
            ),
            claim(
                f"The liquidity ratio is {f['ratio']}: cash plus receivables exceed short-term "
                "obligations.",
                CM,
                ["metric:liquidity.ratio"],
            ),
            claim(
                "With no shock, the six-month projection stays low risk.",
                FORECAST,
                ["stress:baseline"],
            ),
        ],
        "missing_information": [
            f"{possessive(f['largest'])} own financial position and the status of its housing "
            "project.",
            "Whether the builder has agreed payment dates for its overdue invoices.",
        ],
        "weak_assumptions": [
            claim(
                "The early-warning thresholds are judgement-based and not calibrated against real "
                "outcomes.",
                ASSUMPTION,
                ["assumption:early_warning.method"],
            )
        ],
        "alternative_explanations": [
            claim(
                "Receivables may be rising mainly because sales to a growing customer doubled: a "
                "bigger order book takes longer to collect without anything being wrong.",
                AI,
                ["metric:revenue.growth", "metric:customers.concentration"],
                "medium",
            )
        ],
        "severity": "moderate",
    }


def red_team(p: Prompt) -> dict[str, Any]:
    f = _facts(p)
    targets = p.sections.get("Significant assessments requiring review", [])
    disagreements = p.sections.get("Disagreements between agents", [])
    return {
        "challenges": [_challenge(p, t) for t in targets],
        "disagreements_assessed": [
            {
                "disagreement_id": d["id"],
                "assessment": claim(
                    "The evidence supports the more cautious reading: repayment is clean today, "
                    "but cash is falling while receivables rise, and one customer's delay would "
                    "take the account into overdraft.",
                    AI,
                    [
                        "metric:payments.consistency",
                        p.warning("liquidity_deterioration") or "metric:cash.balance",
                        f"{S60}:outcome.risk",
                    ],
                    "medium",
                ),
            }
            for d in disagreements
        ],
        "overall_robustness": claim(
            "The risk conclusion survives the challenges with a lower severity: clean repayment, "
            f"nothing more than a month overdue and a {f['ratio']} liquidity ratio show there is "
            "no distress today, but none of it removes the dependence on one builder's payments.",
            AI,
            [
                "metric:payments.consistency",
                "metric:receivables.outstanding",
                "metric:liquidity.ratio",
                "metric:customers.concentration",
            ],
            "medium",
        ),
    }


RULINGS: dict[str, tuple[str, str]] = {
    "credit_intelligence": (
        "upheld",
        "The red team is right: a clean record shows willingness to pay, not capacity under "
        "stress, and the stress test shows one customer's delay is enough to create a shortfall.",
    ),
    "stress_interpretation": (
        "partially_upheld",
        "The baseline repeats recent months, so it may flatter the outlook; the conclusion that "
        "the business is fragile to the builder's payments stands.",
    ),
}
DEFAULT_RULING = (
    "partially_upheld",
    "The red team is right that there is no distress yet — obligations are paid and nothing is "
    "badly overdue — so the risk is medium rather than high. But the cash trend and the "
    "dependence on one builder are real, so the warning stands.",
)


def senior_synthesis(p: Prompt) -> dict[str, Any]:
    f = _facts(p)
    liq = p.warning("liquidity_deterioration")
    agents = {c["claim_id"]: c["agent"] for c in p.claims}
    upstream = p.first("PRO") + p.first("RSK")
    shock = f"{S60}:shock.customer_payment_stop"
    cash_ids = [f"{liq}:cash_average"] if liq else ["metric:cash.balance"]
    od_limit = inr(p.value("metric:cash.balance", "overdraft_limit"))
    return {
        "headline": "Growing and paying on time, but increasingly funding "
        f"{possessive(f['largest'])} project out of its own cash: medium risk.",
        "overall_assessment": synth(
            f"Sharma Electricals is not in distress: revenue grew {f['growth']}, every "
            f"obligation is paid on time and debt is small. But its growth is consuming cash — "
            f"receivables rose to {f['receivables']} and collection time to {f['dso']} days while "
            f"average cash fell to {f['cash_now']} — and {f['concentration']} of revenue comes "
            "from one builder that is paying later. The early-warning engine's medium rating is "
            "supported.",
            AI,
            [
                "metric:revenue.growth",
                "metric:payments.consistency",
                "metric:receivables.outstanding",
                "metric:receivables.days",
                *cash_ids,
                "metric:customers.concentration",
                "risk:summary",
            ],
            upstream,
            "medium",
        ),
        "facts": [
            synth(
                "FinPulse analysed bank transactions, invoices, supplier bills and loan records "
                "from Apr 2025 to Sep 2026; it has no credit-bureau data.",
                FACT,
                ["fact:data_coverage", "fact:data_sources"],
                [],
            ),
            synth(
                f"The business has one bank account with a {od_limit} overdraft limit.",
                FACT,
                ["fact:accounts"],
                [],
            ),
        ],
        "calculated_metrics": [
            synth(
                f"Revenue grew {f['growth']} over the last three months, to {f['revenue']} in "
                "September.",
                CM,
                ["metric:revenue.growth", "metric:revenue.monthly"],
                [],
            ),
            synth(
                f"Receivables rose from {f['rec_then']} to {f['receivables']} in three months and "
                f"collection time from {f['dso_then']} to {f['dso']} days; {f['overdue']} of "
                "receivables are overdue.",
                CM,
                [
                    "metric:receivables.outstanding",
                    "metric:receivables.days",
                    *(
                        [
                            f"{liq}:receivables_then",
                            f"{liq}:collection_days",
                            f"{liq}:receivables_now",
                        ]
                        if liq
                        else []
                    ),
                ],
                [],
            ),
            synth(
                f"The average cash balance fell from {f['cash_then']} to {f['cash_now']} over the "
                "same three months.",
                CM,
                cash_ids,
                [],
            ),
            synth(
                f"{f['largest']} accounts for {f['concentration']} of revenue over the last six "
                "months.",
                CM,
                ["metric:customers.concentration"],
                [],
            ),
            synth(
                f"Payment consistency is {f['consistency']} and loan repayments take "
                f"{f['burden']} of receipts.",
                CM,
                ["metric:payments.consistency", "metric:debt.service_burden"],
                [],
            ),
        ],
        "forecasts": [
            synth(
                "With no shock, the six-month projection stays low risk, with "
                f"{inr(p.value('stress:baseline', 'closing_balance'))} in the bank at the end.",
                FORECAST,
                ["stress:baseline"],
                [],
            ),
            synth(
                f"If {f['largest']} pays nothing for 60 days, {inr(p.value(shock, 'withheld'))} is "
                "withheld, the account is overdrawn by "
                f"{inr(-p.value(f'{S60}:outcome.cash', 'scenario_minimum'))} at its lowest in "
                "Nov 2026, and projected risk rises from low to high.",
                FORECAST,
                [shock, f"{S60}:outcome.cash", f"{S60}:outcome.risk"],
                [],
            ),
        ],
        "assumptions": [
            synth(
                "The projections repeat the last three months, with no seasonality and no further "
                "slowdown in collections.",
                ASSUMPTION,
                ["assumption:stress.method"],
                [],
            ),
            synth(
                "Early-warning thresholds are judgement-based and not calibrated against real "
                "outcomes.",
                ASSUMPTION,
                ["assumption:early_warning.method"],
                [],
            ),
        ],
        "interpretations": [
            synth(
                "This is a working-capital squeeze, not a profitability problem: the business is "
                "financing its largest customer's growth.",
                AI,
                [*([liq] if liq else []), "metric:customers.concentration"],
                upstream,
                "medium",
            ),
            synth(
                f"The liquidity ratio of {f['ratio']} looks comfortable only because it counts the "
                "builder's unpaid invoices as liquid.",
                AI,
                ["metric:liquidity.ratio", "metric:receivables.outstanding"],
                [],
                "medium",
            ),
        ],
        "challenges_addressed": [
            {
                "target_claim_id": ch["target_claim_id"],
                "resolution": RULINGS.get(agents.get(ch["target_claim_id"], ""), DEFAULT_RULING)[0],
                "explanation": synth(
                    RULINGS.get(agents.get(ch["target_claim_id"], ""), DEFAULT_RULING)[1],
                    AI,
                    ["metric:payments.consistency", f"{S60}:outcome.risk"],
                    [ch["target_claim_id"]],
                    "medium",
                ),
            }
            for ch in p.challenges
        ],
        "disagreements_resolved": [
            {
                "disagreement_id": d["id"],
                "resolution": synth(
                    "Resolved towards the engine's medium rating: the repayment record is clean, "
                    "but liquidity is deteriorating and depends on one customer.",
                    AI,
                    ["risk:summary", "metric:payments.consistency"],
                    [c for c in d.get("claim_ids", []) if c in agents],
                    "medium",
                ),
            }
            for d in p.sections.get("Disagreements between agents", [])
        ],
        "recommendations": [
            {
                "action": f"Ask {f['largest']} for a payment schedule for its overdue invoices "
                "and confirm the status of its housing project before extending more credit.",
                "priority": "high",
                "rationale": synth(
                    f"{f['largest']} is {f['concentration']} of revenue and is paying later; a "
                    "60-day delay from it would take the account into overdraft.",
                    AI,
                    ["metric:customers.concentration", f"{S60}:outcome.risk"],
                    [],
                ),
            },
            {
                "action": "Set a credit limit for the builder, or ask for part-payment in advance "
                "on new orders, so one customer cannot hold more of the business's working "
                "capital.",
                "priority": "high",
                "rationale": synth(
                    f"Receivables reached {f['receivables']} while average cash fell to "
                    f"{f['cash_now']}.",
                    AI,
                    ["metric:receivables.outstanding", *cash_ids],
                    [],
                ),
            },
            {
                "action": f"Keep the {f['od_limit']} overdraft undrawn as a buffer and track cash "
                "weekly until collections recover.",
                "priority": "medium",
                "rationale": synth(
                    "The overdraft absorbs a 60-day delay from the builder but not a 90-day one.",
                    AI,
                    [f"{S60}:outcome.cash", f"{S90}:outcome.failure_point", "fact:accounts"],
                    [],
                ),
            },
            {
                "action": "Re-run this investigation monthly and escalate if collection time or "
                "the overdue share keeps rising.",
                "priority": "medium",
                "rationale": synth(
                    f"Collection time has risen from {f['dso_then']} to {f['dso']} days in three "
                    "months.",
                    AI,
                    [f"{liq}:collection_days"] if liq else ["metric:receivables.days"],
                    [],
                ),
            },
        ],
        "open_questions": [
            f"Is {possessive(f['largest'])} housing project funded, and when are its next stage "
            "payments due?",
            "Would the builder accept shorter terms or part-advances on new orders?",
        ],
        "confidence": "medium",
        "confidence_rationale": "Eighteen months of complete records, but no credit-bureau data "
        "and nothing on the builder's own finances.",
    }


SCRIPTS: dict[str, Callable[[Prompt], dict[str, Any]]] = {
    "financial_profile": financial_profile,
    "credit_intelligence": credit_intelligence,
    "early_warning_investigation": early_warning_investigation,
    "risk_investigation": risk_investigation,
    "stress_interpretation": stress_interpretation,
    "red_team": red_team,
    "senior_synthesis": senior_synthesis,
}


class DemoScriptLLM:
    """``LLMClient`` that answers from the demo script (see the module docstring)."""

    model = DEMO_MODEL
    ai_mode = "demo_script"

    def __init__(self, pace_seconds: float = 1.0) -> None:
        self.pace_seconds = pace_seconds

    async def complete(self, request: LLMRequest) -> LLMResponse:
        agent = request.metadata.get("agent", "")
        script = SCRIPTS.get(agent)
        if script is None:
            raise DemoScriptError(f"The demo script has no answer for agent {agent!r}.")
        prompt = parse(str(request.messages[0]["content"]))
        if not prompt.entity.startswith(DEMO_ENTITY + ":"):
            raise DemoScriptError(
                f"The demo script covers {DEMO_ENTITY} only. Set ANTHROPIC_API_KEY to "
                "investigate other entities."
            )
        output = script(prompt)
        if self.pace_seconds > 0:
            await asyncio.sleep(self.pace_seconds * PACE.get(agent, 3.0))
        return LLMResponse(
            text=json.dumps(output, ensure_ascii=False),
            model=self.model,
            stop_reason="end_turn",
            input_tokens=0,
            output_tokens=0,
        )
