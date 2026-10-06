"""The evidence pack: deterministic, complete and correctly labelled — no LLM involved."""

from collections import Counter

from finpulse.agents.evidence import build_evidence_pack
from finpulse.analytics import default_as_of
from finpulse.stress import PRESETS
from tests.agents.fakes import pack_for
from tests.test_entities_api import SHARMA


def test_pack_is_deterministic() -> None:
    as_of = default_as_of(SHARMA)
    assert as_of is not None

    again = build_evidence_pack(SHARMA, as_of)

    assert again.sha256 == pack_for().sha256
    assert [i.id for i in again.items] == [i.id for i in pack_for().items]


def test_pack_covers_every_engine_with_the_right_kinds() -> None:
    pack = pack_for()
    kinds = Counter(i.kind for i in pack.items)

    assert set(kinds) == {"fact", "calculated_metric", "forecast", "assumption"}
    assert len(pack.select("metric:*")) == 25
    assert all(
        i.kind == "calculated_metric"
        for i in pack.select("metric:*", "passport:*", "warning:*", "risk:*")
    )
    assert pack.get("passport:overall") and len(pack.select("passport:dimension:*")) == 6
    assert pack.select("warning:*") and pack.get("risk:summary") and pack.get("risk:timeline")
    for code in PRESETS:
        assert pack.get(f"stress:{code}").kind == "forecast"  # type: ignore[union-attr]
    shocks = [i for i in pack.select("stress:*") if ":shock." in i.id]
    assert shocks and all(i.kind == "assumption" for i in shocks)
    assert all(i.kind == "fact" for i in pack.select("fact:*"))


def test_warning_items_carry_their_evidence() -> None:
    pack = pack_for()
    [w, *_] = [i for i in pack.select("warning:*") if i.id.count(":") == 1]

    assert w.values["severity"] in {"low", "medium", "high", "critical"}
    assert pack.select(f"{w.id}:*"), "each warning's own evidence is citable too"


def test_not_applicable_scenarios_are_stated_not_dropped() -> None:
    pack = pack_for("ananya_rao_design")

    supplier = pack.get("stress:major_supplier_cost_up_10")
    assert supplier is not None and supplier.values["applicable"] is False
    assert "Not applicable" in supplier.text


def test_the_pack_says_what_finpulse_cannot_see() -> None:
    source = pack_for().get("fact:data_sources")

    assert source is not None and "no credit-bureau data" in source.text
