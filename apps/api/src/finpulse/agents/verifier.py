"""The deterministic verifier: no agent statement reaches a user unless it passes these checks.

For every ``Claim`` in an agent's output:
  * it cites at least one evidence item, and every cited id exists in the evidence pack;
  * its statement type is supported by what it cites — a CALCULATED_METRIC must cite a
    calculated metric, a FORECAST a stress projection, an ASSUMPTION an assumption, a FACT a
    recorded fact (AI_INTERPRETATION may cite anything, but must cite);
  * every number in the statement appears in the evidence it cites (or in the evidence behind
    the upstream claims it builds on), allowing only for displayed rounding. A number the
    model worked out itself — a sum, a difference, an average — is therefore rejected;
  * in sectioned outputs (the senior synthesis) it sits in the section matching its type.

Other text fields may only contain numbers that exist somewhere in the evidence pack. Fields
that point at evidence or at other agents' claims must point at things that exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from finpulse.agents.evidence import EvidencePack
from finpulse.agents.numbers import extract, numbers_in, supported
from finpulse.agents.schemas import Issue, IssueCode, RegisteredClaim, StatementType

PathKey = str | int
REQUIRED_KIND: dict[str, str] = {
    "FACT": "fact",
    "CALCULATED_METRIC": "calculated_metric",
    "FORECAST": "forecast",
    "ASSUMPTION": "assumption",
}
CLAIM_KEYS = {"statement", "statement_type", "evidence_ids", "confidence"}


def is_claim(node: object) -> bool:
    return isinstance(node, dict) and set(node) >= CLAIM_KEYS


def path_str(path: tuple[PathKey, ...]) -> str:
    out = ""
    for key in path:
        out += f"[{key}]" if isinstance(key, int) else (f".{key}" if out else key)
    return out


@dataclass
class Found:
    path: tuple[PathKey, ...]
    code: IssueCode
    detail: str

    def issue(self) -> Issue:
        return Issue(path=path_str(self.path), code=self.code, detail=self.detail)


@dataclass
class VerifyRules:
    """What one agent's output must satisfy beyond the universal claim checks."""

    section_types: dict[str, StatementType] = field(default_factory=dict)
    evidence_ref_fields: dict[str, str] = field(default_factory=dict)  # field → id prefix
    claim_ref_fields: frozenset[str] = frozenset({"target_claim_id", "based_on_claims"})


@dataclass
class Result:
    found: list[Found]
    claims_checked: int
    numbers_checked: int

    @property
    def passed(self) -> bool:
        return not self.found


class Verifier:
    def __init__(
        self,
        pack: EvidencePack,
        rules: VerifyRules | None = None,
        upstream: dict[str, RegisteredClaim] | None = None,
        known_refs: dict[str, frozenset[str]] | None = None,
    ) -> None:
        self.pack = pack
        self.rules = rules or VerifyRules()
        self.upstream = upstream or {}
        # Fields that must name something the orchestrator supplied (e.g. disagreement ids).
        self.known_refs = known_refs or {}
        self._numbers: dict[str, set[Decimal]] = {}
        self._all: set[Decimal] | None = None

    # --- known numbers ----------------------------------------------------------------------

    def numbers_of(self, item_id: str) -> set[Decimal]:
        if item_id not in self._numbers:
            item = self.pack.get(item_id)
            self._numbers[item_id] = (
                numbers_in(item.values) | numbers_in(item.text) | numbers_in(item.title)
                if item
                else set()
            )
        return self._numbers[item_id]

    def all_numbers(self) -> set[Decimal]:
        if self._all is None:
            self._all = set().union(*(self.numbers_of(i.id) for i in self.pack.items))
        return self._all

    # --- checks -----------------------------------------------------------------------------

    def verify(self, output: dict[str, Any]) -> Result:
        result = Result(found=[], claims_checked=0, numbers_checked=0)
        self._walk(output, (), None, result)
        return result

    def _walk(
        self, node: object, path: tuple[PathKey, ...], section: str | None, r: Result
    ) -> None:
        if isinstance(node, dict) and is_claim(node):
            self._claim(node, path, section, r)
            return
        if isinstance(node, dict):
            for key, value in node.items():
                here = (*path, key)
                top = section if path else key
                if key in self.rules.evidence_ref_fields:
                    self._evidence_ref(value, here, self.rules.evidence_ref_fields[key], r)
                elif key in self.rules.claim_ref_fields:
                    self._claim_refs(value, here, r)
                elif key in self.known_refs:
                    if value not in self.known_refs[key]:
                        r.found.append(
                            Found(
                                here,
                                "unknown_reference",
                                f"{value!r} is not one of {sorted(self.known_refs[key])}.",
                            )
                        )
                else:
                    self._walk(value, here, top, r)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                self._walk(value, (*path, i), section, r)
        elif isinstance(node, str):
            self._free_text(node, path, r)

    def _claim(
        self, claim: dict[str, Any], path: tuple[PathKey, ...], section: str | None, r: Result
    ) -> None:
        r.claims_checked += 1
        ids: list[str] = list(claim.get("evidence_ids") or [])
        kind_needed = REQUIRED_KIND.get(claim["statement_type"])
        if not ids:
            r.found.append(
                Found(
                    (*path, "evidence_ids"),
                    "missing_citation",
                    "Every claim must cite at least one evidence item.",
                )
            )
        known_ids = [i for i in ids if self.pack.get(i) is not None]
        for i in ids:
            if self.pack.get(i) is None:
                r.found.append(
                    Found(
                        (*path, "evidence_ids"),
                        "unknown_evidence_id",
                        f"{i!r} is not an evidence item id.",
                    )
                )
        kinds = {self.pack.get(i).kind for i in known_ids}  # type: ignore[union-attr]
        if kind_needed and known_ids and kind_needed not in kinds:
            r.found.append(
                Found(
                    (*path, "statement_type"),
                    "type_not_supported",
                    f"A {claim['statement_type']} claim must cite at least one {kind_needed} "
                    f"item; it cites only {sorted(kinds)}.",
                )
            )
        wanted = self.rules.section_types.get(section or "")
        if wanted and claim["statement_type"] != wanted:
            r.found.append(
                Found(
                    (*path, "statement_type"),
                    "wrong_section_type",
                    f"Section {section!r} holds only {wanted} claims, not "
                    f"{claim['statement_type']}.",
                )
            )
        refs = claim.get("based_on_claims") or []
        self._claim_refs(refs, (*path, "based_on_claims"), r)
        known = set().union(*(self.numbers_of(i) for i in known_ids)) if known_ids else set()
        for ref in refs:
            if ref in self.upstream:
                for i in self.upstream[ref].evidence_ids:
                    known |= self.numbers_of(i)
        for n in extract(str(claim.get("statement", ""))):
            r.numbers_checked += 1
            if not supported(n, known):
                r.found.append(
                    Found(
                        (*path, "statement"),
                        "unsupported_number",
                        f"{n.text!r} does not appear in the cited evidence "
                        f"({', '.join(ids) or 'none'}). Quote numbers exactly as the evidence "
                        "gives them; do not calculate new ones.",
                    )
                )

    def _free_text(self, text: str, path: tuple[PathKey, ...], r: Result) -> None:
        for n in extract(text):
            r.numbers_checked += 1
            if not supported(n, self.all_numbers()):
                r.found.append(
                    Found(
                        path,
                        "unsupported_number",
                        f"{n.text!r} does not appear anywhere in the evidence.",
                    )
                )

    def _evidence_ref(
        self, value: object, path: tuple[PathKey, ...], prefix: str, r: Result
    ) -> None:
        item = self.pack.get(value) if isinstance(value, str) else None
        if item is None:
            r.found.append(Found(path, "unknown_evidence_id", f"{value!r} is not an evidence id."))
        elif not item.id.startswith(prefix):
            r.found.append(
                Found(path, "wrong_reference_kind", f"{value!r} must be a {prefix}… evidence id.")
            )

    def _claim_refs(self, value: object, path: tuple[PathKey, ...], r: Result) -> None:
        refs = [value] if isinstance(value, str) else list(value or [])  # type: ignore[call-overload]
        for ref in refs:
            if ref not in self.upstream:
                r.found.append(
                    Found(
                        path,
                        "unknown_claim_id",
                        f"{ref!r} is not the id of a verified upstream claim.",
                    )
                )


# --- pruning -------------------------------------------------------------------------------------


def prunable(found: list[Found]) -> bool:
    """Whether every issue sits inside a list element that can be dropped."""
    return all(any(isinstance(k, int) for k in f.path) for f in found)


def prune(output: dict[str, Any], found: list[Found]) -> tuple[dict[str, Any], list[str]]:
    """Remove the innermost list element containing each issue; returns removed statements."""
    targets: set[tuple[PathKey, ...]] = set()
    for f in found:
        last = max(i for i, k in enumerate(f.path) if isinstance(k, int))
        targets.add(f.path[: last + 1])
    removed = []
    # deepest and highest index first, so earlier removals don't shift later targets
    for target in sorted(targets, key=lambda t: (len(t), t[-1]), reverse=True):
        parent: Any = output
        for key in target[:-1]:
            parent = parent[key]
        element = parent[target[-1]]
        removed.append(_describe(element))
        del parent[target[-1]]
    return output, removed


def _describe(element: object) -> str:
    if is_claim(element):
        return str(element["statement"])  # type: ignore[index]
    if isinstance(element, dict):
        for value in element.values():
            if is_claim(value):
                return str(value["statement"])
        return str(element.get("title") or element.get("challenge_summary") or element)[:300]
    return str(element)[:300]
