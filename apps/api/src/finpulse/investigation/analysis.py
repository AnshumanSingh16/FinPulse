"""Deterministic steps of the investigation workflow — no language model in this module.

* ``detect_disagreements``: where agents disagree with each other or with the engines.
* ``select_review_requests``: which significant risk assessments the red team must challenge.
* ``red_team_requirements`` / ``senior_requirements``: what those agents' outputs must cover.
* ``metrics_used``, ``evidence_references``, ``triggered_warnings``: what the conclusions rest on.
* ``final_assessment``, ``assess_confidence``, ``audit_claims``: the final record.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import Any

from finpulse.agents.catalogue import AGENTS
from finpulse.agents.evidence import EvidenceItem, EvidencePack
from finpulse.agents.schemas import AgentRun, RegisteredClaim
from finpulse.early_warning.schemas import RiskSummary, WarningsReport
from finpulse.investigation.schemas import (
    ClaimAudit,
    ConfidenceAssessment,
    ConfidenceLevel,
    Disagreement,
    EvidenceReference,
    FinalAssessment,
    MetricUsed,
    RedTeamFindings,
    ReviewCoverage,
    ReviewRequest,
    TriggeredWarning,
)
from finpulse.scoring.schemas import Passport

STANCES = ("low", "moderate", "elevated", "high", "severe")
ENGINE_LEVELS = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SEVERITIES = ("low", "medium", "high", "critical")
CONFIDENCE = ("low", "medium", "high")
# The claim that carries each analyst's overall judgement.
HEADLINE_PATHS = {
    "financial_profile": "summary",
    "credit_intelligence": "reliability_view",
    "early_warning_investigation": "common_thread",
    "risk_investigation": "overall",
    "stress_interpretation": "resilience_summary",
}
POSITIVE_SECTIONS = {"financial_profile": ("strengths",)}
NEGATIVE_SECTIONS = {
    "financial_profile": ("weaknesses",),
    "credit_intelligence": ("concerns",),
    "risk_investigation": ("risks",),
}
MAX_REVIEW_REQUESTS = 12
# Disagreements need at least this many steps between ratings on their scale.
DISAGREEMENT_GAP, MAJOR_GAP = 2, 3


def title(agent: str) -> str:
    return AGENTS[agent].title if agent in AGENTS else agent


def succeeded(runs: dict[str, AgentRun]) -> dict[str, AgentRun]:
    return {n: r for n, r in runs.items() if r.status == "succeeded" and r.output is not None}


def by_path(run: AgentRun) -> dict[str, RegisteredClaim]:
    return {c.path: c for c in run.claims}


def warning_item(pack: EvidencePack, evidence_id: str) -> EvidenceItem | None:
    """The warning an id refers to (its own id, or one of its evidence items)."""
    if not evidence_id.startswith("warning:"):
        return None
    parent = ":".join(evidence_id.split(":")[:2])
    return pack.get(parent)


# --- disagreements ------------------------------------------------------------------------------


def detect_disagreements(
    analysts: dict[str, AgentRun], pack: EvidencePack, engine_level: str
) -> list[Disagreement]:
    runs = succeeded(analysts)
    found: list[Disagreement] = []

    def headline(agent: str) -> list[str]:
        claim = by_path(runs[agent]).get(HEADLINE_PATHS.get(agent, ""))
        return [claim.claim_id] if claim else []

    stances = {
        n: str(r.output["risk_stance"])
        for n, r in runs.items()
        if r.output and "risk_stance" in r.output
    }
    if len(stances) >= 2:
        low = min(stances, key=lambda n: STANCES.index(stances[n]))
        high = max(stances, key=lambda n: STANCES.index(stances[n]))
        gap = STANCES.index(stances[high]) - STANCES.index(stances[low])
        if gap >= DISAGREEMENT_GAP:
            found.append(
                Disagreement(
                    id="",
                    kind="stance_spread",
                    severity="major" if gap >= MAJOR_GAP else "moderate",
                    description=f"{title(low)} rates overall risk '{stances[low]}' but "
                    f"{title(high)} rates it '{stances[high]}'.",
                    agents=[low, high],
                    claim_ids=headline(low) + headline(high),
                    evidence_ids=[],
                )
            )

    engine = ENGINE_LEVELS.get(engine_level, 0)
    for agent, stance in stances.items():
        gap = abs(STANCES.index(stance) - engine)
        if gap >= DISAGREEMENT_GAP:
            found.append(
                Disagreement(
                    id="",
                    kind="agent_vs_engine",
                    severity="major" if gap >= MAJOR_GAP else "moderate",
                    description=f"{title(agent)} rates overall risk '{stance}' while the "
                    f"deterministic early-warning engine reports '{engine_level}' risk.",
                    agents=[agent],
                    claim_ids=headline(agent),
                    evidence_ids=["risk:summary"],
                )
            )

    uses: dict[str, list[tuple[str, str, str]]] = defaultdict(list)  # id → (agent, claim, ±)
    for agent, sections, sign in [
        *((a, s, "+") for a, s in POSITIVE_SECTIONS.items()),
        *((a, s, "-") for a, s in NEGATIVE_SECTIONS.items()),
    ]:
        if agent not in runs:
            continue
        for claim in runs[agent].claims:
            if claim.path.split("[")[0].split(".")[0] in sections:
                for eid in claim.evidence_ids:
                    uses[eid].append((agent, claim.claim_id, sign))
    for eid, entries in uses.items():
        positive = {a for a, _, s in entries if s == "+"}
        negative = {a for a, _, s in entries if s == "-"}
        if positive and negative and positive | negative != positive & negative:
            item = pack.get(eid)
            found.append(
                Disagreement(
                    id="",
                    kind="conflicting_reading",
                    severity="moderate",
                    description=f"{item.title if item else eid} is read as a strength by "
                    f"{', '.join(title(a) for a in sorted(positive))} but as a weakness or "
                    f"risk by {', '.join(title(a) for a in sorted(negative))}.",
                    agents=sorted(positive | negative),
                    claim_ids=sorted({c for _, c, _ in entries}),
                    evidence_ids=[eid],
                )
            )

    risk = runs.get("risk_investigation")
    if risk and risk.output:
        claims = by_path(risk)
        for i, r in enumerate(risk.output.get("risks", [])):
            cited = [
                *r["risk"]["evidence_ids"],
                *(e for c in r["likely_causes"] for e in c["evidence_ids"]),
            ]
            warnings = {w.id: w for e in cited if (w := warning_item(pack, e)) is not None}
            if not warnings:
                continue
            worst = max(SEVERITIES.index(str(w.values["severity"])) for w in warnings.values())
            stated = SEVERITIES.index(r["severity"])
            if abs(stated - worst) >= DISAGREEMENT_GAP:
                risk_claim = claims.get(f"risks[{i}].risk")
                found.append(
                    Disagreement(
                        id="",
                        kind="severity_mismatch",
                        severity="moderate",
                        description=f"{title('risk_investigation')} rates '{r['title']}' as "
                        f"{r['severity']} severity, but the warnings it cites are rated up to "
                        f"{SEVERITIES[worst]} by the deterministic engine.",
                        agents=["risk_investigation"],
                        claim_ids=[risk_claim.claim_id] if risk_claim else [],
                        evidence_ids=sorted(warnings),
                    )
                )
    return [d.model_copy(update={"id": f"DIS-{n:02d}"}) for n, d in enumerate(found, start=1)]


# --- red-team review --------------------------------------------------------------------------


def select_review_requests(
    analysts: dict[str, AgentRun],
    pack: EvidencePack,
    disagreements: list[Disagreement],
    engine_level: str,
) -> list[ReviewRequest]:
    """The significant risk assessments the red team must challenge, most significant first."""
    runs = succeeded(analysts)
    requests: list[ReviewRequest] = []
    all_claims = {c.claim_id: c for r in runs.values() for c in r.claims}

    def add(claim: RegisteredClaim | None, reason: str) -> None:
        if claim is None or any(r.claim_id == claim.claim_id for r in requests):
            return
        requests.append(
            ReviewRequest(
                claim_id=claim.claim_id, reason=reason, agent=claim.agent, statement=claim.statement
            )
        )

    if (risk := runs.get("risk_investigation")) and risk.output:
        claims = by_path(risk)
        for i, r in enumerate(risk.output.get("risks", [])):
            if r["severity"] in ("high", "critical"):
                add(
                    claims.get(f"risks[{i}].risk"),
                    f"{r['severity']}-severity risk assessment: {r['title']}",
                )
    if (ewi := runs.get("early_warning_investigation")) and ewi.output:
        claims = by_path(ewi)
        for i, inv in enumerate(ewi.output.get("investigations", [])):
            w = pack.get(inv["warning_evidence_id"])
            severity = str(w.values.get("severity")) if w else ""
            if severity in ("high", "critical"):
                add(
                    claims.get(f"investigations[{i}].likely_explanation"),
                    f"explanation of a {severity} early warning",
                )
    if (credit := runs.get("credit_intelligence")) is not None:
        add(by_path(credit).get("reliability_view"), "overall reliability view")
    if (stress := runs.get("stress_interpretation")) is not None:
        add(by_path(stress).get("resilience_summary"), "overall resilience judgement")
    if (profile := runs.get("financial_profile")) and profile.output:
        stance = str(profile.output.get("risk_stance", "low"))
        if STANCES.index(stance) >= 2 or ENGINE_LEVELS.get(engine_level, 0) >= 3:
            add(by_path(profile).get("summary"), "overall condition summary")
    for d in disagreements:
        for cid in d.claim_ids:
            add(all_claims.get(cid), f"involved in disagreement {d.id}")
    return requests[:MAX_REVIEW_REQUESTS]


def red_team_requirements(
    requests: list[ReviewRequest], disagreements: list[Disagreement]
) -> Callable[[dict[str, Any]], list[str]]:
    def check(output: dict[str, Any]) -> list[str]:
        targeted = Counter(c["target_claim_id"] for c in output.get("challenges", []))
        assessed = {d["disagreement_id"] for d in output.get("disagreements_assessed", [])}
        return [
            *(
                f"Significant assessment {r.claim_id} ({r.reason}) has no challenge: add one."
                for r in requests
                if not targeted[r.claim_id]
            ),
            *(
                f"Disagreement {d.id} is not assessed in `disagreements_assessed`."
                for d in disagreements
                if d.id not in assessed
            ),
        ]

    return check


def senior_requirements(
    disagreements: list[Disagreement], red_team: AgentRun | None
) -> Callable[[dict[str, Any]], list[str]]:
    serious = []
    if red_team and red_team.output:
        serious = sorted(
            {
                c["target_claim_id"]
                for c in red_team.output.get("challenges", [])
                if c["severity"] in ("major", "moderate")
            }
        )

    def check(output: dict[str, Any]) -> list[str]:
        resolved = {d["disagreement_id"] for d in output.get("disagreements_resolved", [])}
        addressed = {c["target_claim_id"] for c in output.get("challenges_addressed", [])}
        unmet = [
            f"Disagreement {d.id} is not resolved in `disagreements_resolved`."
            for d in disagreements
            if d.id not in resolved
        ]
        unmet += [
            f"The red-team challenge to {t} is not addressed in `challenges_addressed`."
            for t in serious
            if t not in addressed
        ]
        if not output.get("recommendations"):
            unmet.append("Give at least one recommendation.")
        return unmet

    return check


def review_coverage(requests: list[ReviewRequest], red_team: AgentRun | None) -> ReviewCoverage:
    targeted: Counter[str] = Counter()
    if red_team and red_team.output:
        targeted = Counter(c["target_claim_id"] for c in red_team.output.get("challenges", []))
    for r in requests:
        r.challenges = targeted[r.claim_id]
        r.reviewed = r.challenges > 0
    return ReviewCoverage(
        requested=len(requests),
        reviewed=sum(r.reviewed for r in requests),
        unreviewed=[r.claim_id for r in requests if not r.reviewed],
    )


def red_team_findings(red_team: AgentRun | None, coverage: ReviewCoverage) -> RedTeamFindings:
    output = red_team.output if red_team and red_team.output else {}
    return RedTeamFindings(
        status=red_team.status if red_team else "skipped",
        challenges=output.get("challenges", []),
        disagreements_assessed=output.get("disagreements_assessed", []),
        overall_robustness=output.get("overall_robustness"),
        coverage=coverage,
    )


def mark_resolved(disagreements: list[Disagreement], senior: AgentRun | None) -> None:
    resolved = set()
    if senior and senior.output:
        resolved = {d["disagreement_id"] for d in senior.output.get("disagreements_resolved", [])}
    for d in disagreements:
        d.resolved = d.id in resolved


# --- what the conclusions rest on --------------------------------------------------------------


def _all_claims(runs: Iterable[AgentRun]) -> list[RegisteredClaim]:
    return [c for r in runs if r.status == "succeeded" for c in r.claims]


def metrics_used(runs: Iterable[AgentRun], pack: EvidencePack) -> list[MetricUsed]:
    cited: dict[str, list[str]] = defaultdict(list)
    for claim in _all_claims(runs):
        for eid in claim.evidence_ids:
            if eid.startswith("metric:"):
                code = eid.removeprefix("metric:")
            elif eid.startswith("passport:factor:"):
                code = eid.split(":", 3)[3]
            else:
                continue
            if claim.claim_id not in cited[code]:
                cited[code].append(claim.claim_id)
    out = []
    for code in sorted(cited):
        item = pack.get(f"metric:{code}")
        if item is None:
            continue
        value = item.values.get("value")
        out.append(
            MetricUsed(
                code=code,
                evidence_id=item.id,
                name=item.title,
                value=value if isinstance(value, Decimal) else None,
                unit=str(item.values.get("unit", "")),
                period=str(item.values.get("period", "")),
                cited_by=cited[code],
            )
        )
    return out


REF_FIELDS = ("warning_evidence_id", "scenario_evidence_id", "most_damaging_scenario_evidence_id")


def _ref_fields(node: object) -> Iterable[str]:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in REF_FIELDS and isinstance(v, str):
                yield v
            else:
                yield from _ref_fields(v)
    elif isinstance(node, list):
        for v in node:
            yield from _ref_fields(v)


def evidence_references(
    runs: Iterable[AgentRun], pack: EvidencePack
) -> tuple[list[EvidenceReference], bool]:
    runs = list(runs)
    cited: dict[str, list[str]] = defaultdict(list)
    for claim in _all_claims(runs):
        for eid in claim.evidence_ids:
            cited[eid].append(claim.claim_id)
    for run in runs:
        if run.status == "succeeded":
            for eid in _ref_fields(run.output):
                cited.setdefault(eid, [])
    refs, resolve = [], True
    for eid in sorted(cited):
        item = pack.get(eid)
        if item is None:
            resolve = False
            continue
        refs.append(
            EvidenceReference(
                id=item.id,
                kind=item.kind,
                source=item.source,
                title=item.title,
                text=item.text,
                cited_by=cited[eid],
            )
        )
    return refs, resolve


def triggered_warnings(
    report: WarningsReport, ewi: AgentRun | None, pack: EvidencePack
) -> list[TriggeredWarning]:
    explained: dict[str, list[str]] = defaultdict(list)
    if ewi and ewi.status == "succeeded" and ewi.output:
        claims = ewi.claims
        for i, inv in enumerate(ewi.output.get("investigations", [])):
            prefix = f"investigations[{i}]"
            explained[inv["warning_evidence_id"]] += [
                c.claim_id for c in claims if c.path.startswith(prefix)
            ]
    return [
        TriggeredWarning(
            warning_id=w.id,
            evidence_id=f"warning:{w.id}",
            rule=w.rule,
            category=w.category,
            severity=w.severity,
            title=w.title,
            description=w.description,
            first_detected_on=w.first_detected_on,
            investigated=bool(explained.get(f"warning:{w.id}")),
            investigation_claim_ids=explained.get(f"warning:{w.id}", []),
        )
        for w in report.warnings
    ]


# --- the final record --------------------------------------------------------------------------


def health_of(passport: Passport) -> dict[str, Any]:
    fh = passport.financial_health
    return {
        "score": fh.score,
        "band": fh.band.label if fh.band else None,
        "confidence": fh.confidence,
        "provisional": fh.provisional,
        "evidence_id": "passport:overall",
        "note": "Prototype financial-health profile; not a credit score.",
    }


def _verbatim(item: EvidenceItem | None) -> list[dict[str, Any]]:
    """A claim that quotes an evidence item word for word: verified by construction."""
    if item is None:
        return []
    kinds = {
        "fact": "FACT",
        "calculated_metric": "CALCULATED_METRIC",
        "forecast": "FORECAST",
        "assumption": "ASSUMPTION",
    }
    return [
        {
            "statement": item.text,
            "statement_type": kinds[item.kind],
            "evidence_ids": [item.id],
            "confidence": "high",
            "based_on_claims": [],
        }
    ]


def final_assessment(
    senior: AgentRun | None, pack: EvidencePack, summary: RiskSummary, passport: Passport
) -> FinalAssessment:
    base = {
        "risk_level": summary.risk_level,
        "early_warning_index": summary.early_warning_index,
        "financial_health": health_of(passport),
    }
    if senior and senior.status == "succeeded" and senior.output:
        o = senior.output
        return FinalAssessment(
            source="senior_synthesis",
            headline=o["headline"],
            overall_assessment=o["overall_assessment"],
            facts=o["facts"],
            calculated_metrics=o["calculated_metrics"],
            forecasts=o["forecasts"],
            assumptions=o["assumptions"],
            interpretations=o["interpretations"],
            challenges_addressed=o["challenges_addressed"],
            disagreements_resolved=o["disagreements_resolved"],
            open_questions=o["open_questions"],
            **base,
        )
    # Without the senior agent: deterministic results only, quoted verbatim, no interpretation.
    warnings = [i for i in pack.select("warning:*") if i.id.count(":") == 1][:5]
    return FinalAssessment(
        source="deterministic_fallback",
        headline=summary.headline,
        overall_assessment=None,
        facts=_verbatim(pack.get("fact:data_coverage")),
        calculated_metrics=[
            *_verbatim(pack.get("passport:overall")),
            *_verbatim(pack.get("risk:summary")),
            *(c for w in warnings for c in _verbatim(w)),
        ],
        forecasts=_verbatim(pack.get("stress:baseline")),
        assumptions=_verbatim(pack.get("assumption:stress.method")),
        interpretations=[],
        challenges_addressed=[],
        disagreements_resolved=[],
        open_questions=["The AI synthesis was unavailable; only deterministic results are shown."],
        **base,
    )


def assess_confidence(
    runs: dict[str, AgentRun],
    analysts: Iterable[str],
    coverage: ReviewCoverage,
    disagreements: list[Disagreement],
    passport: Passport,
) -> ConfidenceAssessment:
    """The senior agent's stated confidence, capped by what the orchestrator observed."""
    senior = runs.get("senior_synthesis")
    stated: ConfidenceLevel | None = None
    rationale = None
    if senior and senior.status == "succeeded" and senior.output:
        stated = senior.output["confidence"]
        rationale = senior.output["confidence_rationale"]
    cap = "high"
    adjustments: list[str] = []

    def lower(level: str, why: str) -> None:
        nonlocal cap
        adjustments.append(why)
        if CONFIDENCE.index(level) < CONFIDENCE.index(cap):
            cap = level

    failed = [a for a in analysts if a not in runs or runs[a].status != "succeeded"]
    if len(failed) >= 2:
        lower("low", f"{len(failed)} specialist agents produced no verified analysis.")
    elif failed:
        lower("medium", f"{title(failed[0])} produced no verified analysis.")
    red = runs.get("red_team")
    if red is None or red.status != "succeeded":
        lower("low", "The conclusions were not red-team reviewed.")
    elif coverage.unreviewed:
        lower(
            "medium",
            f"{len(coverage.unreviewed)} significant assessment(s) were not "
            "challenged by the red team.",
        )
    if stated is None:
        lower("low", "No senior synthesis: only deterministic results are reported.")
    elif senior and senior.verification and senior.verification.unmet_requirements:
        lower(
            "medium", "The senior synthesis left red-team challenges or disagreements unaddressed."
        )
    unresolved = [d.id for d in disagreements if not d.resolved]
    if unresolved:
        lower("medium", f"Unresolved disagreement(s) between agents: {', '.join(unresolved)}.")
    if passport.financial_health.provisional:
        lower("medium", "The Financial Passport is provisional: the data history is thin.")
    adjustments.append("The data is synthetic and the methods are not calibrated on real outcomes.")
    cap_level: ConfidenceLevel = cap  # type: ignore[assignment]
    level = (
        cap_level if stated is None or CONFIDENCE.index(stated) > CONFIDENCE.index(cap) else stated
    )
    return ConfidenceAssessment(
        level=level,
        stated_by_senior_agent=stated,
        senior_rationale=rationale,
        cap=cap_level,
        adjustments=adjustments,
    )


def audit_claims(runs: Iterable[AgentRun], references_resolve: bool) -> ClaimAudit:
    runs = list(runs)
    ok = [r for r in runs if r.status == "succeeded"]
    return ClaimAudit(
        claims_verified=sum(len(r.claims) for r in ok),
        claims_pruned=sum(len(r.verification.pruned) for r in ok if r.verification),
        issues_caught=sum(
            len(issues) for r in runs if r.verification for issues in r.verification.attempts_issues
        ),
        unmet_requirements=[
            f"{r.agent}: {u}"
            for r in ok
            if r.verification
            for u in r.verification.unmet_requirements
        ],
        evidence_references_resolve=references_resolve,
    )
