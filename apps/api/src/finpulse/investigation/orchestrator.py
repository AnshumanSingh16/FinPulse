"""The FinPulse investigation workflow.

    Financial Data
      → Deterministic Analytics → Financial Passport → Early Warning Detection → Stress Testing
      → Evidence Assembly (verified, citable, hashed)
      → Specialized AI Investigation (five agents, in parallel, on verified evidence only)
      → Disagreement Detection & Review Planning (deterministic)
      → Red-Team Challenge (mandatory review of significant risk assessments)
      → Evidence Verification (deterministic audit of every verified claim before synthesis)
      → Senior Financial Intelligence Agent
      → Final Assessment (deterministic assembly, confidence, audit)

Every stage is timed and recorded; every notable event is both logged (structlog, bound to the
investigation id) and kept in the investigation's own event list, so a complete investigation
can be inspected after the fact. Agents only ever receive the verified evidence pack and other
agents' *verified* claims; every claim they return has passed the deterministic verifier.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import Counter
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from finpulse.agents.base import AgentContext, ContextSection, run_agent
from finpulse.agents.catalogue import AGENTS, ANALYSTS
from finpulse.agents.evidence import (
    NEUTRALISED_TAG,
    assemble_evidence_pack,
    run_stress_presets,
)
from finpulse.agents.llm import LLMClient
from finpulse.agents.schemas import AgentRun, Usage
from finpulse.analytics import compute_report
from finpulse.analytics.inputs import FinancialData
from finpulse.core.errors import LLMUnavailableError
from finpulse.early_warning import detect_warnings, load_config, risk_summary
from finpulse.investigation import analysis
from finpulse.investigation.schemas import (
    EventLevel,
    EvidencePackRef,
    Investigation,
    InvestigationEvent,
    StageName,
    StageRecord,
    StageStatus,
)
from finpulse.investigation.timeline import agent_event_data, build_timeline
from finpulse.observability.logging import get_logger
from finpulse.scoring import load_model, with_monthly_change

WORKFLOW_VERSION = "investigation-1.0.0"
DISCLAIMER = (
    "Financial investigation of synthetic data. Numbers come from deterministic engines; AI "
    "agents interpret them, and every AI statement was verified to cite existing evidence and "
    "to state only numbers present in that evidence. Statements typed AI_INTERPRETATION are "
    "judgements. This is not a credit score, credit assessment or lending decision."
)
log = get_logger("finpulse.investigation")
Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Stage:
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    status: StageStatus = "completed"


class Recorder:
    """Collects stage records and events, and mirrors each event to the structured log."""

    def __init__(
        self,
        investigation_id: uuid.UUID,
        entity: str,
        clock: Clock,
        listener: Callable[[Recorder], None] | None = None,
    ) -> None:
        self.clock = clock
        self.listener = listener  # told after every event (live progress)
        self.stages: list[StageRecord] = []
        self.events: list[InvestigationEvent] = []
        self.log = log.bind(investigation_id=str(investigation_id), entity=entity)
        self.current: StageName = "financial_data"

    def event(self, event: str, message: str, level: EventLevel = "info", **data: Any) -> None:
        self.events.append(
            InvestigationEvent(
                at=self.clock(),
                stage=self.current,
                level=level,
                event=event,
                message=message,
                data=data,
            )
        )
        getattr(self.log, level)(event, stage=self.current, message=message, **data)
        if self.listener is not None:
            try:
                self.listener(self)
            except Exception:  # progress reporting must never break an investigation
                self.log.exception("progress_listener_failed")

    @asynccontextmanager
    async def stage(self, name: StageName, title: str) -> AsyncIterator[_Stage]:
        self.current = name
        started, t0 = self.clock(), time.perf_counter()
        self.event("stage_started", title)
        st = _Stage()
        try:
            yield st
        except Exception as exc:
            st.status, st.summary = "failed", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            ms = round((time.perf_counter() - t0) * 1000)
            self.stages.append(
                StageRecord(
                    stage=name,
                    title=title,
                    status=st.status,
                    started_at=started,
                    completed_at=self.clock(),
                    duration_ms=ms,
                    summary=st.summary,
                    details=st.details,
                )
            )
            level: EventLevel = "info" if st.status in ("completed", "skipped") else "warning"
            if st.status == "failed":
                level = "error"
            self.event(
                "stage_" + ("failed" if st.status == "failed" else "completed"),
                st.summary or title,
                level,
                status=st.status,
                duration_ms=ms,
            )


def _agent_event(rec: Recorder, run: AgentRun) -> None:
    v = run.verification
    data: dict[str, Any] = {
        "agent": run.agent,
        "status": run.status,
        "attempts": run.attempts,
        "claims": len(run.claims),
        "issues_caught": sum(len(i) for i in v.attempts_issues) if v else 0,
        "pruned": len(v.pruned) if v else 0,
        "unmet_requirements": len(v.unmet_requirements) if v else 0,
        "stance": (run.output or {}).get("risk_stance"),
        **agent_event_data(run),
    }
    if run.status == "succeeded":
        rec.event(
            "agent_completed",
            f"{run.title}: {len(run.claims)} verified claims after {run.attempts} attempt(s).",
            **data,
        )
    else:
        rec.event(
            "agent_failed",
            f"{run.title}: {run.error.message if run.error else 'failed'}",
            "warning",
            error=run.error.code if run.error else None,
            **data,
        )


class InvestigationOrchestrator:
    def __init__(self, llm: LLMClient, *, clock: Clock = utcnow) -> None:
        self.llm = llm
        self.clock = clock

    async def investigate(
        self,
        data: FinancialData,
        as_of: date,
        *,
        investigation_id: uuid.UUID | None = None,
        listener: Callable[[Recorder], None] | None = None,
    ) -> Investigation:
        investigation_id = investigation_id or uuid.uuid4()
        rec = Recorder(investigation_id, data.display_name, self.clock, listener)
        started, t0 = self.clock(), time.perf_counter()
        ai_mode = getattr(self.llm, "ai_mode", "live")
        rec.event(
            "investigation_started",
            f"Investigating {data.display_name} as of {as_of}"
            + (
                " (demo script: scripted agent answers, not a model)." if ai_mode != "live" else "."
            ),
            entity_id=str(data.entity_id),
            as_of=as_of.isoformat(),
            ai_mode=ai_mode,
        )

        # --- deterministic stages ------------------------------------------------------------
        async with rec.stage("financial_data", "Financial data") as st:
            st.details = {
                "transactions": len(data.transactions),
                "invoices": len(data.invoices),
                "bills": len(data.bills),
                "loans": len(data.loans),
                "counter_sale_days": len(data.counter_sales),
                "first_transaction": data.transactions[0].posted_on.isoformat()
                if data.transactions
                else None,
            }
            st.summary = (
                f"{len(data.transactions)} transactions, {len(data.invoices)} invoices, "
                f"{len(data.bills)} bills, {len(data.loans)} loans."
            )

        async with rec.stage("deterministic_analytics", "Deterministic analytics") as st:
            report = compute_report(data, as_of)
            missing = [m.code for m in report.metrics if m.availability != "available"]
            st.details = {
                "metrics": len(report.metrics),
                "unavailable": missing,
                "complete_months": report.coverage.complete_months,
            }
            st.summary = (
                f"{len(report.metrics) - len(missing)} of {len(report.metrics)} metrics available."
            )

        async with rec.stage("financial_passport", "Financial Passport") as st:
            passport = with_monthly_change(data, as_of, load_model())
            health = analysis.health_of(passport)
            st.details = {k: v for k, v in health.items() if k != "note"}
            st.summary = f"Financial Health {health['score']} ({health['band']})."
            if passport.financial_health.provisional:
                st.status = "completed_with_issues"
                rec.event("passport_provisional", "Passport is provisional (thin data).", "warning")

        async with rec.stage("early_warning_detection", "Early warning detection") as st:
            config = load_config()
            warnings = detect_warnings(data, as_of, config)
            summary = risk_summary(data, as_of, config)
            counts = Counter(w.severity for w in warnings.warnings)
            st.details = {
                "risk_level": summary.risk_level,
                "index": summary.early_warning_index,
                "by_severity": dict(counts),
                "warnings": [f"{w.severity}: {w.title}" for w in warnings.warnings],
            }
            st.summary = summary.headline
            for w in warnings.warnings:
                rec.event(
                    "warning_triggered",
                    f"[{w.severity.upper()}] {w.title}",
                    "warning" if w.severity in ("high", "critical") else "info",
                    warning_id=w.id,
                    rule=w.rule,
                    category=w.category,
                )

        async with rec.stage("stress_testing", "Stress testing") as st:
            stress = run_stress_presets(data, as_of)
            failing = [
                c for c, r in stress.items() if not isinstance(r, str) and r.stressed.failure_point
            ]
            st.details = {
                "scenarios": len(stress),
                "not_applicable": [c for c, r in stress.items() if isinstance(r, str)],
                "scenarios_with_failure_point": failing,
            }
            st.summary = f"{len(stress)} scenarios; funds run out in {len(failing)} of them."

        async with rec.stage("evidence_assembly", "Evidence assembly") as st:
            pack = assemble_evidence_pack(data, as_of, report, passport, warnings, summary, stress)
            by_kind = dict(Counter(i.kind for i in pack.items))
            st.details = {"sha256": pack.sha256, "items": len(pack.items), "by_kind": by_kind}
            st.summary = f"{len(pack.items)} verified evidence items (sha256 {pack.sha256[:12]}…)."
            neutralised = [i.id for i in pack.items if NEUTRALISED_TAG in i.tags]
            if neutralised:
                rec.event(
                    "untrusted_text_neutralised",
                    f"{len(neutralised)} evidence items contained text resembling instructions; "
                    "it was removed before any agent saw it.",
                    "warning",
                    items=neutralised,
                )

        # --- AI stages -------------------------------------------------------------------------
        runs: dict[str, AgentRun] = {}
        async with rec.stage("specialized_investigation", "Specialized AI investigation") as st:

            async def analyse(name: str) -> AgentRun:
                rec.event("agent_started", f"{AGENTS[name].title} started.", agent=name)
                run = await run_agent(AGENTS[name], self.llm, pack)
                _agent_event(rec, run)  # as each finishes, for live progress
                return run

            results = await asyncio.gather(*(analyse(n) for n in ANALYSTS))
            runs.update(zip(ANALYSTS, results, strict=True))
            ok = [r for r in results if r.status == "succeeded"]
            st.details = {
                r.agent: {
                    "status": r.status,
                    "claims": len(r.claims),
                    "stance": (r.output or {}).get("risk_stance"),
                    "error": r.error.code if r.error else None,
                }
                for r in results
            }
            st.summary = (
                f"{len(ok)} of {len(results)} specialist agents produced verified analyses."
            )
            if all(r.error and r.error.code == "llm_unavailable" for r in results):
                st.status = "failed"
                rec.event("llm_unavailable", "The AI model could not be reached.", "error")
                raise LLMUnavailableError(results[0].error.message if results[0].error else None)
            if len(ok) < len(results):
                st.status = "completed_with_issues" if ok else "failed"

        analysts = {n: runs[n] for n in ANALYSTS}
        async with rec.stage(
            "disagreement_detection", "Disagreement detection and review planning"
        ) as st:
            disagreements = analysis.detect_disagreements(analysts, pack, summary.risk_level)
            requests = analysis.select_review_requests(
                analysts, pack, disagreements, summary.risk_level
            )
            for d in disagreements:
                rec.event(
                    "disagreement_detected",
                    d.description,
                    "warning" if d.severity == "major" else "info",
                    id=d.id,
                    kind=d.kind,
                    claims=d.claim_ids,
                )
            for r in requests:
                rec.event(
                    "review_requested",
                    f"Red-team review required for {r.claim_id}: {r.reason}.",
                    claim_id=r.claim_id,
                    agent=r.agent,
                )
            st.details = {"disagreements": len(disagreements), "review_requests": len(requests)}
            st.summary = (
                f"{len(disagreements)} disagreement(s); {len(requests)} assessment(s) sent for "
                "review."
            )

        verified = analysis.succeeded(analysts)
        refs = {"disagreement_id": frozenset(d.id for d in disagreements)}
        disagreement_rows = [
            {
                "id": d.id,
                "kind": d.kind,
                "severity": d.severity,
                "description": d.description,
                "claim_ids": d.claim_ids,
                "evidence_ids": d.evidence_ids,
            }
            for d in disagreements
        ]
        red: AgentRun | None = None
        async with rec.stage("red_team_challenge", "Red-team challenge") as st:
            if not verified:
                st.status, st.summary = "skipped", "No verified analyses to challenge."
            else:
                context = AgentContext(
                    sections=(
                        ContextSection(
                            "Significant assessments requiring review",
                            "Challenge each of these claims at least once (mandatory).",
                            [
                                {
                                    "claim_id": r.claim_id,
                                    "reason": r.reason,
                                    "agent": r.agent,
                                    "statement": r.statement,
                                }
                                for r in requests
                            ],
                        ),
                        ContextSection(
                            "Disagreements between agents",
                            "Detected deterministically by the orchestrator. Assess "
                            "each in `disagreements_assessed`.",
                            disagreement_rows,
                        ),
                    ),
                    known_refs=refs,
                    requirements=analysis.red_team_requirements(requests, disagreements),
                )
                rec.event("agent_started", "Red-Team Agent started.", agent="red_team")
                red = await run_agent(AGENTS["red_team"], self.llm, pack, verified, context)
                runs["red_team"] = red
                _agent_event(rec, red)
            coverage = analysis.review_coverage(requests, red)
            for claim_id in coverage.unreviewed:
                rec.event(
                    "review_missing",
                    f"{claim_id} was not challenged by the red team.",
                    "warning",
                    claim_id=claim_id,
                )
            if red is not None:
                st.status = (
                    "completed"
                    if red.status == "succeeded" and not coverage.unreviewed
                    else ("completed_with_issues" if red.status == "succeeded" else "failed")
                )
                st.summary = (
                    f"{len((red.output or {}).get('challenges', []))} challenge(s); "
                    f"{coverage.reviewed} of {coverage.requested} required reviews done."
                )
            st.details = coverage.model_dump()

        async with rec.stage("evidence_verification", "Evidence verification") as st:
            upstream_runs = [x for x in runs.values() if x.status == "succeeded"]
            if not upstream_runs:
                st.status, st.summary = "skipped", "No verified claims to audit."
            else:
                for audited in upstream_runs:
                    v = audited.verification
                    issues = sum(len(i) for i in v.attempts_issues) if v else 0
                    pruned = len(v.pruned) if v else 0
                    rec.event(
                        "claims_audited",
                        f"{audited.title}: {len(audited.claims)} claim(s) passed the "
                        f"verifier; {pruned} pruned; {issues} issue(s) caught over "
                        f"{audited.attempts} attempt(s).",
                        agent_audited=audited.agent,
                        claims=len(audited.claims),
                        pruned=pruned,
                        issues_caught=issues,
                    )
                up_refs, up_resolve = analysis.evidence_references(upstream_runs, pack)
                up_audit = analysis.audit_claims(upstream_runs, up_resolve)
                st.details = {
                    "agents": len(upstream_runs),
                    "claims_verified": up_audit.claims_verified,
                    "claims_pruned": up_audit.claims_pruned,
                    "issues_caught": up_audit.issues_caught,
                    "evidence_references": len(up_refs),
                    "evidence_references_resolve": up_resolve,
                    "unmet_requirements": up_audit.unmet_requirements,
                }
                st.summary = (
                    f"{up_audit.claims_verified} verified claim(s) from {len(upstream_runs)} "
                    f"agent(s); {up_audit.claims_pruned} statement(s) pruned, "
                    f"{up_audit.issues_caught} issue(s) caught; {len(up_refs)} evidence "
                    + (
                        "references all resolve to the hashed pack."
                        if up_resolve
                        else "references, some of which do not resolve to the pack."
                    )
                )
                if not up_resolve or up_audit.unmet_requirements:
                    st.status = "completed_with_issues"
                    rec.event(
                        "verification_gaps",
                        "Audit found unresolved references or unmet requirements.",
                        "warning",
                        unmet=up_audit.unmet_requirements,
                    )

        senior: AgentRun | None = None
        async with rec.stage("senior_synthesis", "Senior Financial Intelligence Agent") as st:
            if not verified:
                st.status, st.summary = "skipped", "No verified analyses to synthesise."
            else:
                upstream = {
                    **verified,
                    **({"red_team": red} if red and red.status == "succeeded" else {}),
                }
                context = AgentContext(
                    sections=(
                        ContextSection(
                            "Disagreements between agents",
                            "Resolve each in `disagreements_resolved`.",
                            disagreement_rows,
                        ),
                        ContextSection(
                            "Red-team review coverage",
                            "Significant assessments the red team did not challenge "
                            "(treat with caution).",
                            [{"claim_id": c} for c in coverage.unreviewed],
                        ),
                    ),
                    known_refs=refs,
                    requirements=analysis.senior_requirements(disagreements, red),
                )
                rec.event(
                    "agent_started",
                    "Senior Financial Intelligence Agent started.",
                    agent="senior_synthesis",
                )
                senior = await run_agent(
                    AGENTS["senior_synthesis"], self.llm, pack, upstream, context
                )
                runs["senior_synthesis"] = senior
                _agent_event(rec, senior)
                unmet = senior.verification.unmet_requirements if senior.verification else []
                st.status = (
                    "failed"
                    if senior.status != "succeeded"
                    else "completed_with_issues"
                    if unmet
                    else "completed"
                )
                for u in unmet:
                    rec.event("requirement_unmet", u, "warning", agent="senior_synthesis")
                st.summary = (senior.output or {}).get("headline") or (
                    senior.error.message if senior.error else ""
                )
            analysis.mark_resolved(disagreements, senior)

        async with rec.stage("final_assessment", "Final assessment") as st:
            final = analysis.final_assessment(senior, pack, summary, passport)
            confidence = analysis.assess_confidence(
                runs, ANALYSTS, coverage, disagreements, passport
            )
            references, resolve = analysis.evidence_references(runs.values(), pack)
            audit = analysis.audit_claims(runs.values(), resolve)
            if final.source == "deterministic_fallback":
                st.status = "completed_with_issues"
                rec.event(
                    "fallback_assessment",
                    "Senior synthesis unavailable: final assessment "
                    "built from deterministic results only.",
                    "warning",
                )
            st.details = {
                "source": final.source,
                "confidence": confidence.level,
                "claims_verified": audit.claims_verified,
                "claims_pruned": audit.claims_pruned,
                "issues_caught": audit.issues_caught,
                "evidence_references_resolve": audit.evidence_references_resolve,
            }
            st.summary = f"{final.headline} (confidence {confidence.level})."

        ok = [r for r in runs.values() if r.status == "succeeded"]
        status = (
            "failed"
            if not ok
            else "completed"
            if len(ok) == len(AGENTS) and not audit.unmet_requirements
            else "completed_with_gaps"
        )
        duration = round((time.perf_counter() - t0) * 1000)
        usage = Usage(
            input_tokens=sum(r.usage.input_tokens for r in runs.values()),
            output_tokens=sum(r.usage.output_tokens for r in runs.values()),
            calls=sum(r.usage.calls for r in runs.values()),
        )
        rec.event(
            "investigation_completed",
            f"Investigation {status}: {final.headline}",
            status=status,
            confidence=confidence.level,
            duration_ms=duration,
            llm_calls=usage.calls,
        )
        return Investigation(
            investigation_id=investigation_id,
            entity_id=data.entity_id,
            entity=pack.entity,
            as_of=as_of,
            workflow_version=WORKFLOW_VERSION,
            ai_mode=ai_mode,
            status=status,
            started_at=started,
            completed_at=self.clock(),
            duration_ms=duration,
            stages=rec.stages,
            triggered_warnings=analysis.triggered_warnings(
                warnings, runs.get("early_warning_investigation"), pack
            ),
            risk_summary={
                "risk_level": summary.risk_level,
                "early_warning_index": summary.early_warning_index,
                "headline": summary.headline,
                "evidence_id": "risk:summary",
            },
            financial_health=analysis.health_of(passport),
            financial_metrics_used=analysis.metrics_used(runs.values(), pack),
            agent_analyses=analysts,
            disagreements=disagreements,
            review_requests=requests,
            red_team_findings=analysis.red_team_findings(red, coverage) if red else None,
            red_team_run=red,
            senior_synthesis_run=senior,
            final_assessment=final,
            recommendations=(senior.output or {}).get("recommendations", []) if senior else [],
            confidence=confidence,
            evidence_pack=EvidencePackRef(
                sha256=pack.sha256,
                items=len(pack.items),
                by_kind=by_kind,
                engine_versions=pack.engine_versions,
            ),
            evidence_references=references,
            claim_audit=audit,
            usage=usage,
            events=rec.events,
            timeline=build_timeline(rec.stages, rec.events, running=False),
            disclaimer=DISCLAIMER,
        )
