"""The audit trail of AI investigations (SECURITY.md).

Every investigation leaves an append-only, hash-chained record of who asked for it, what the AI
was given and returned, what the verifier did with it, and what was concluded:

    investigation_requested   who, which entity and date, live model or demo script
    llm_call (one per call)   agent, attempt, model, SHA-256 of the exact request and response,
                              tokens, duration, error
    evidence_pack             hash and size of the evidence the agents read; any untrusted text
                              that had to be neutralised
    agent_result (per agent)  status, verified claims, statements pruned, verifier issues caught
                              (including prohibited lending-decision language)
    investigation_completed   outcome, deterministic risk level, confidence, SHA-256 of the full
      / _failed               investigation record; and that no decision was made

Each entry's hash covers its content and the previous entry's hash, so any later change or
deletion breaks the chain (``verify_chain``); the database also refuses UPDATE and DELETE. Prompts
and responses are stored as hashes, not text: the inputs are reproducible from the hashed evidence
pack and the versioned prompts, and the verified outputs are in the investigation record.

The first entry is written before any model is called; if it cannot be written, the
investigation does not start (``AuditUnavailableError``).

This module has no database code (the AI layer may not import it; see
tests/security/test_ai_boundaries.py). The PostgreSQL sink lives in
``persistence/repositories/ai_audit.py``.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from pydantic import BaseModel

from finpulse.agents.llm import LLMClient, LLMRequest, LLMResponse
from finpulse.core.errors import AppError, DependencyUnavailableError
from finpulse.investigation.schemas import Investigation
from finpulse.observability.logging import get_logger

log = get_logger("finpulse.audit")
NO_DECISION = "none: advisory analysis for a human analyst; FinPulse makes no lending decision"


class AuditUnavailableError(DependencyUnavailableError):
    code = "audit_unavailable"
    title = "Audit trail unavailable"


class AuditRecord(BaseModel):
    investigation_id: uuid.UUID
    org_id: uuid.UUID
    seq: int
    event: str
    occurred_at: datetime
    actor: str
    request_id: str | None
    payload: dict[str, Any]
    prev_hash: str | None
    hash: str


class AuditTrail(BaseModel):
    investigation_id: uuid.UUID
    entries: list[AuditRecord]
    chain_valid: bool
    broken_at_seq: int | None = None


class AuditSink(Protocol):
    async def append(self, records: list[AuditRecord]) -> None: ...
    async def read(self, org_id: uuid.UUID, investigation_id: uuid.UUID) -> list[AuditRecord]: ...


class MemoryAuditSink:
    """For tests and local development without a database."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    async def append(self, records: list[AuditRecord]) -> None:
        self.records.extend(records)

    async def read(self, org_id: uuid.UUID, investigation_id: uuid.UUID) -> list[AuditRecord]:
        return sorted(
            (
                r
                for r in self.records
                if r.org_id == org_id and r.investigation_id == investigation_id
            ),
            key=lambda r: r.seq,
        )


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def sha256(value: Any) -> str:
    text = value if isinstance(value, str) else canonical(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def entry_hash(record: AuditRecord | dict[str, Any]) -> str:
    r = record if isinstance(record, dict) else record.model_dump(mode="json")
    content = {
        k: r[k]
        for k in (
            "investigation_id",
            "org_id",
            "seq",
            "event",
            "occurred_at",
            "actor",
            "request_id",
            "payload",
        )
    }
    return sha256(f"{r['prev_hash'] or ''}\n{canonical(content)}")


def verify_chain(records: list[AuditRecord]) -> int | None:
    """The seq of the first entry that does not verify, or None if the chain is intact."""
    prev: str | None = None
    for expected_seq, r in enumerate(records, start=1):
        if r.seq != expected_seq or r.prev_hash != prev or entry_hash(r) != r.hash:
            return r.seq
        prev = r.hash
    return None


@dataclass
class InvestigationAuditor:
    """Collects one investigation's audit entries and writes them to the sink."""

    sink: AuditSink
    org_id: uuid.UUID
    investigation_id: uuid.UUID
    actor: str
    request_id: str | None
    pending: list[AuditRecord] = field(default_factory=list)
    seq: int = 0
    last_hash: str | None = None

    def _add(self, event: str, payload: dict[str, Any]) -> None:
        self.seq += 1
        draft = {
            "investigation_id": self.investigation_id,
            "org_id": self.org_id,
            "seq": self.seq,
            "event": event,
            "occurred_at": datetime.now(UTC),
            "actor": self.actor,
            "request_id": self.request_id,
            "payload": json.loads(canonical(payload)),
            "prev_hash": self.last_hash,
        }
        record = AuditRecord(**draft, hash="")
        record = record.model_copy(update={"hash": entry_hash(record)})
        self.last_hash = record.hash
        self.pending.append(record)

    async def _flush(self) -> None:
        records, self.pending = self.pending, []
        await self.sink.append(records)

    async def requested(self, entity_id: uuid.UUID, as_of: date, mode: str, model: str) -> None:
        """Written before any model call; the investigation must not start if this fails."""
        self._add(
            "investigation_requested",
            {"entity_id": entity_id, "as_of": as_of, "mode": mode, "model": model},
        )
        try:
            await self._flush()
        except Exception as exc:  # any storage failure: refuse to run unaudited
            log.error("audit_write_failed", stage="requested", error=type(exc).__name__)
            raise AuditUnavailableError(
                "The audit trail could not be written, so the investigation was not started."
            ) from exc

    def wrap(self, llm: LLMClient) -> AuditingLLM:
        return AuditingLLM(llm, self)

    async def completed(self, inv: Investigation) -> None:
        self._add(
            "evidence_pack",
            {
                **inv.evidence_pack.model_dump(mode="json"),
                "neutralised_items": [
                    i
                    for e in inv.events
                    if e.event == "untrusted_text_neutralised"
                    for i in e.data.get("items", [])
                ],
            },
        )
        runs = [*inv.agent_analyses.values(), inv.red_team_run, inv.senior_synthesis_run]
        for run in runs:
            if run is None:
                continue
            v = run.verification
            codes = [i.code for attempt in (v.attempts_issues if v else []) for i in attempt]
            self._add(
                "agent_result",
                {
                    "agent": run.agent,
                    "status": run.status,
                    "model": run.model,
                    "attempts": run.attempts,
                    "claims_verified": len(run.claims),
                    "statements_pruned": len(v.pruned) if v else 0,
                    "issues_caught": len(codes),
                    "prohibited_decisions_caught": codes.count("prohibited_decision"),
                    "unmet_requirements": v.unmet_requirements if v else [],
                    "error": run.error.code if run.error else None,
                },
            )
        fa = inv.final_assessment
        self._add(
            "investigation_completed",
            {
                "status": inv.status,
                "ai_mode": inv.ai_mode,
                "final_assessment_source": fa.source,
                "risk_level_deterministic": fa.risk_level,
                "confidence": inv.confidence.level,
                "claims_verified": inv.claim_audit.claims_verified,
                "claims_pruned": inv.claim_audit.claims_pruned,
                "evidence_references_resolve": inv.claim_audit.evidence_references_resolve,
                "record_sha256": sha256(inv.model_dump(mode="json")),
                "decision": NO_DECISION,
            },
        )
        await self._safe_flush("completed")

    async def failed(self, exc: BaseException) -> None:
        code = exc.instance_code if isinstance(exc, AppError) else "internal_error"
        self._add("investigation_failed", {"error": code, "decision": NO_DECISION})
        await self._safe_flush("failed")

    async def _safe_flush(self, stage: str) -> None:
        try:
            await self._flush()
        except Exception as exc:  # the run already happened; record loudly, don't hide it
            log.error("audit_write_failed", stage=stage, error=type(exc).__name__)


class AuditingLLM:
    """Records every model call in the audit trail; the answer passes through unchanged."""

    def __init__(self, inner: LLMClient, auditor: InvestigationAuditor) -> None:
        self.inner = inner
        self.auditor = auditor
        self.model = inner.model
        self.ai_mode = getattr(inner, "ai_mode", "live")
        self._attempts: dict[str, int] = defaultdict(int)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        agent = request.metadata.get("agent", "")
        self._attempts[agent] += 1
        payload: dict[str, Any] = {
            "agent": agent,
            "call": self._attempts[agent],
            "model": self.model,
            "request_sha256": sha256(
                {"system": request.system, "messages": request.messages, "schema": request.schema}
            ),
        }
        started = time.perf_counter()
        try:
            response = await self.inner.complete(request)
        except Exception as exc:
            payload |= {
                "error": exc.instance_code if isinstance(exc, AppError) else type(exc).__name__,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            }
            self.auditor._add("llm_call", payload)
            raise
        payload |= {
            "response_model": response.model,
            "response_sha256": sha256(response.text),
            "stop_reason": response.stop_reason,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }
        self.auditor._add("llm_call", payload)
        return response
