"""The verifier on a tiny hand-made evidence pack."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from finpulse.agents.evidence import EvidenceItem, EvidencePack
from finpulse.agents.schemas import RegisteredClaim
from finpulse.agents.verifier import Verifier, VerifyRules, prunable, prune
from finpulse.analytics.schemas import EntityRef

ENTITY = EntityRef(
    id="00000000-0000-0000-0000-000000000001", display_name="Test", kind="business", segment="test"
)  # type: ignore[arg-type]
PACK = EvidencePack(
    entity=ENTITY,
    as_of=date(2026, 9, 30),
    pack_version="t",
    engine_versions={},
    sha256="x",
    items=[
        EvidenceItem(
            id="fact:data_coverage",
            kind="fact",
            source="data",
            title="Coverage",
            text="1467 transactions over 17 complete months.",
        ),
        EvidenceItem(
            id="metric:receivables.outstanding",
            kind="calculated_metric",
            source="analytics",
            title="Receivables",
            text="Receivables: ₹10,97,992.",
            values={"value": Decimal("1097992.00")},
        ),
        EvidenceItem(
            id="metric:receivables.days",
            kind="calculated_metric",
            source="analytics",
            title="DSO",
            text="Receivable days: 47.8 days.",
            values={"value": Decimal("47.8")},
        ),
        EvidenceItem(
            id="stress:revenue_down_20",
            kind="forecast",
            source="stress",
            title="Revenue −20%",
            text="Closing cash -₹7,97,120; funds run out around 2026-10-10.",
            values={"closing_balance": Decimal("-797119.65")},
        ),
        EvidenceItem(
            id="assumption:stress.method",
            kind="assumption",
            source="stress",
            title="Method",
            text="Overdraft interest at 13% a year.",
        ),
    ],
)
UPSTREAM = {
    "RSK-01": RegisteredClaim(
        claim_id="RSK-01",
        agent="risk_investigation",
        path="risks[0].risk",
        statement="DSO is 47.8 days.",
        statement_type="CALCULATED_METRIC",
        evidence_ids=["metric:receivables.days"],
        confidence="high",
    ),
}


def claim(statement: str, stype: str, *ids: str, **extra: Any) -> dict[str, Any]:
    return {
        "statement": statement,
        "statement_type": stype,
        "evidence_ids": list(ids),
        "confidence": "high",
        **extra,
    }


def issues(output: dict[str, Any], rules: VerifyRules | None = None) -> list[tuple[str, str]]:
    result = Verifier(PACK, rules, UPSTREAM).verify(output)
    return [(f.issue().path, f.code) for f in result.found]


def test_a_well_supported_output_passes() -> None:
    output = {
        "items": [
            claim(
                "Receivables stand at ₹10,97,992, about ₹11 lakh.",
                "CALCULATED_METRIC",
                "metric:receivables.outstanding",
            ),
            claim("Customers take 48 days to pay.", "CALCULATED_METRIC", "metric:receivables.days"),
            claim(
                "Under a 20% revenue fall, cash would end at -₹7,97,120 and run out around "
                "10 Oct 2026.",
                "FORECAST",
                "stress:revenue_down_20",
            ),
            claim(
                "The projection assumes 13% overdraft interest.",
                "ASSUMPTION",
                "assumption:stress.method",
            ),
            claim("The history is 17 months long.", "FACT", "fact:data_coverage"),
            claim(
                "Slow collections are squeezing cash.",
                "AI_INTERPRETATION",
                "metric:receivables.days",
                "stress:revenue_down_20",
            ),
        ],
        "note": "Receivable days are 47.8.",
    }

    result = Verifier(PACK).verify(output)

    assert result.passed, result.found
    assert result.claims_checked == 6 and result.numbers_checked >= 7


@pytest.mark.parametrize(
    ("bad", "code"),
    [
        (
            claim(
                "Receivables are ₹12,00,000.", "CALCULATED_METRIC", "metric:receivables.outstanding"
            ),
            "unsupported_number",
        ),
        # a difference the model worked out itself
        (
            claim(
                "Receivables minus 47.8 days is ₹10,97,944.",
                "CALCULATED_METRIC",
                "metric:receivables.outstanding",
                "metric:receivables.days",
            ),
            "unsupported_number",
        ),
        # right number, but cited from the wrong item
        (
            claim(
                "Customers take 47.8 days.", "CALCULATED_METRIC", "metric:receivables.outstanding"
            ),
            "unsupported_number",
        ),
        (claim("Receivables are high.", "CALCULATED_METRIC"), "missing_citation"),
        (
            claim("Receivables are high.", "CALCULATED_METRIC", "metric:imaginary"),
            "unknown_evidence_id",
        ),
        (claim("Cash will run out.", "FORECAST", "metric:receivables.days"), "type_not_supported"),
        (claim("DSO is 47.8 days.", "FACT", "metric:receivables.days"), "type_not_supported"),
    ],
)
def test_unsupported_claims_are_caught(bad: dict[str, Any], code: str) -> None:
    assert code in {c for _, c in issues({"items": [bad]})}


def test_free_text_numbers_must_exist_somewhere() -> None:
    assert issues({"open_questions": ["Is the 47.8-day DSO seasonal?", "Why ₹99,999?"]}) == [
        ("open_questions[1]", "unsupported_number")
    ]


def test_sections_must_hold_their_own_type() -> None:
    rules = VerifyRules(section_types={"facts": "FACT", "forecasts": "FORECAST"})
    output = {
        "facts": [claim("DSO is 47.8 days.", "CALCULATED_METRIC", "metric:receivables.days")],
        "forecasts": [claim("Cash ends at -₹7,97,120.", "FORECAST", "stress:revenue_down_20")],
    }

    assert issues(output, rules) == [("facts[0].statement_type", "wrong_section_type")]


def test_references_to_evidence_and_claims() -> None:
    rules = VerifyRules(evidence_ref_fields={"scenario": "stress:"})
    output = {
        "a": {"scenario": "stress:revenue_down_20"},
        "b": {"scenario": "metric:receivables.days"},
        "c": {"scenario": "stress:nope"},
        "d": {"target_claim_id": "RSK-01"},
        "e": {"target_claim_id": "RSK-99"},
    }

    assert issues(output, rules) == [
        ("b.scenario", "wrong_reference_kind"),
        ("c.scenario", "unknown_evidence_id"),
        ("e.target_claim_id", "unknown_claim_id"),
    ]


def test_numbers_may_come_from_the_upstream_claims_built_on() -> None:
    built_on = claim(
        "Collections are slow at 47.8 days.",
        "AI_INTERPRETATION",
        "fact:data_coverage",
        based_on_claims=["RSK-01"],
    )
    unsupported = claim(
        "Collections are slow at 47.8 days.",
        "AI_INTERPRETATION",
        "fact:data_coverage",
        based_on_claims=[],
    )

    assert issues({"x": [built_on]}) == []
    assert issues({"x": [unsupported]}) == [("x[0].statement", "unsupported_number")]


def test_pruning_drops_only_failing_list_elements() -> None:
    good = claim("DSO is 47.8 days.", "CALCULATED_METRIC", "metric:receivables.days")
    bad = claim("DSO is 99 days.", "CALCULATED_METRIC", "metric:receivables.days")
    output = {"summary": good, "items": [good, bad, good], "nested": [{"risk": bad}]}
    found = Verifier(PACK).verify(output).found

    assert prunable(found)
    pruned, removed = prune(output, found)

    assert pruned["items"] == [good, good] and pruned["nested"] == []
    assert removed == ["DSO is 99 days.", "DSO is 99 days."]
    assert Verifier(PACK).verify(pruned).passed


def test_a_failing_top_level_claim_cannot_be_pruned() -> None:
    found = (
        Verifier(PACK)
        .verify(
            {"summary": claim("DSO is 99 days.", "CALCULATED_METRIC", "metric:receivables.days")}
        )
        .found
    )

    assert not prunable(found)
