"""A readable, terminal-friendly rendering of an investigation, for demos and debugging."""

from __future__ import annotations

from typing import Any

from finpulse.investigation.schemas import Investigation

LABELS = {
    "facts": "FACT",
    "calculated_metrics": "CALCULATED METRIC",
    "forecasts": "FORECAST",
    "assumptions": "ASSUMPTION",
    "interpretations": "AI INTERPRETATION",
}
MARK = {"completed": "✓", "completed_with_issues": "!", "failed": "✗", "skipped": "–"}


def _claim(c: dict[str, Any]) -> str:
    refs = ", ".join(c.get("evidence_ids", []) + c.get("based_on_claims", []))
    return f"{c['statement']}  [{refs}]"


def render(inv: Investigation, *, events: bool = False) -> str:
    fa = inv.final_assessment
    out: list[str] = []
    add = out.append
    add(f"INVESTIGATION {inv.investigation_id}")
    add(
        f"{inv.entity.display_name} as of {inv.as_of} — {inv.status} "
        f"({inv.duration_ms / 1000:.1f} s, {inv.usage.calls} model calls)"
    )
    add("")
    add("WORKFLOW")
    for s in inv.stages:
        add(f"  {MARK[s.status]} {s.title:<46} {s.duration_ms:>6} ms  {s.summary}")
    add("")
    add(f"TRIGGERED WARNINGS ({len(inv.triggered_warnings)})")
    for w in inv.triggered_warnings:
        how = (
            f"investigated: {', '.join(w.investigation_claim_ids)}"
            if w.investigated
            else "not investigated"
        )
        add(f"  [{w.severity.upper()}] {w.title} ({w.evidence_id}) — {how}")
    add("")
    add(f"METRICS USED ({len(inv.financial_metrics_used)})")
    for m in inv.financial_metrics_used:
        add(f"  {m.code} = {m.value} {m.unit} — cited by {', '.join(m.cited_by)}")
    add("")
    add("AGENT ANALYSES")
    for run in [*inv.agent_analyses.values(), inv.red_team_run, inv.senior_synthesis_run]:
        if run is None:
            continue
        stance = (run.output or {}).get("risk_stance", "")
        v = run.verification
        caught = sum(len(i) for i in v.attempts_issues) if v else 0
        add(
            f"  {run.title:<36} {run.status:<9} {('stance ' + stance) if stance else '':<16} "
            f"{len(run.claims):>2} claims, {run.attempts} attempt(s), {caught} issue(s) caught"
            + (f" — {run.error.code}" if run.error else "")
        )
    add("")
    add(f"DISAGREEMENTS ({len(inv.disagreements)})")
    for d in inv.disagreements:
        state = "resolved" if d.resolved else "UNRESOLVED"
        add(f"  {d.id} [{d.severity}] {d.description} — {state}")
    if inv.red_team_findings:
        rt = inv.red_team_findings
        add("")
        add(
            f"RED TEAM — {len(rt.challenges)} challenge(s); required reviews "
            f"{rt.coverage.reviewed}/{rt.coverage.requested}"
            + (
                f"; unreviewed: {', '.join(rt.coverage.unreviewed)}"
                if rt.coverage.unreviewed
                else ""
            )
        )
        for ch in rt.challenges:
            add(f"  → {ch['target_claim_id']} [{ch['severity']}] {ch['challenge_summary']}")
    add("")
    add(
        f"FINAL ASSESSMENT ({fa.source}) — early-warning risk {fa.risk_level}, "
        f"Financial Health {fa.financial_health.get('score')} ({fa.financial_health.get('band')})"
    )
    add(f"  {fa.headline}")
    if fa.overall_assessment:
        add(f"  AI INTERPRETATION: {_claim(fa.overall_assessment)}")
    for key, label in LABELS.items():
        for c in getattr(fa, key):
            add(f"  {label}: {_claim(c)}")
    for ch in fa.challenges_addressed:
        add(f"  CHALLENGE {ch['target_claim_id']} {ch['resolution']}: {_claim(ch['explanation'])}")
    for q in fa.open_questions:
        add(f"  OPEN QUESTION: {q}")
    add("")
    add("RECOMMENDATIONS")
    for r in inv.recommendations:
        add(f"  [{r['priority']}] {r['action']} — {_claim(r['rationale'])}")
    c = inv.confidence
    add("")
    add(
        f"CONFIDENCE: {c.level} (senior agent: {c.stated_by_senior_agent}; "
        f"orchestrator cap: {c.cap})"
    )
    for adjustment in c.adjustments:
        add(f"  - {adjustment}")
    audit = inv.claim_audit
    add("")
    add(
        f"AUDIT: {audit.claims_verified} verified claims, {audit.claims_pruned} pruned, "
        f"{audit.issues_caught} issue(s) caught by the verifier, evidence references resolve: "
        f"{'yes' if audit.evidence_references_resolve else 'NO'}"
    )
    for u in audit.unmet_requirements:
        add(f"  unmet: {u}")
    if events:
        add("")
        add(f"EVENTS ({len(inv.events)})")
        t0 = inv.started_at
        for e in inv.events:
            add(
                f"  +{(e.at - t0).total_seconds():7.2f}s {e.level:<7} {e.stage:<26} "
                f"{e.event}: {e.message}"
            )
    return "\n".join(out)
