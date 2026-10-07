"""Live progress of investigations running in the background.

``POST /entities/{id}/investigations`` starts one and returns at once; the UI polls
``GET /investigations/{id}/progress``, which is rebuilt from the orchestrator's own events as
they happen (stage started/completed, agent started/completed/failed) — nothing is simulated.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime

from finpulse.agents.llm import LLMClient
from finpulse.analytics.inputs import FinancialData
from finpulse.core.errors import AppError, TooManyRequestsError
from finpulse.investigation.audit import InvestigationAuditor
from finpulse.investigation.orchestrator import InvestigationOrchestrator, Recorder
from finpulse.investigation.schemas import InvestigationProgress, ProgressError
from finpulse.investigation.store import InvestigationStore
from finpulse.investigation.timeline import build_timeline
from finpulse.observability.logging import get_logger

log = get_logger("finpulse.investigation.progress")


def _now() -> datetime:
    return datetime.now(UTC)


class ProgressTracker:
    """Background runs, each owned by one organisation; at most ``max_running`` at a time per
    organisation (every run makes several paid model calls)."""

    def __init__(self, keep: int = 50, max_running: int = 2) -> None:
        self.keep = keep
        self.max_running = max_running
        self._items: dict[uuid.UUID, InvestigationProgress] = {}
        self._orgs: dict[uuid.UUID, uuid.UUID] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._running: dict[uuid.UUID, int] = {}

    def get(self, investigation_id: uuid.UUID, org_id: uuid.UUID) -> InvestigationProgress | None:
        if self._orgs.get(investigation_id) != org_id:
            return None
        return self._items.get(investigation_id)

    def acquire(self, org_id: uuid.UUID) -> None:
        """Reserve a running slot for the organisation, or refuse with 429."""
        if self._running.get(org_id, 0) >= self.max_running:
            raise TooManyRequestsError(
                f"At most {self.max_running} investigations may run at once; wait for one to "
                "finish.",
                code="too_many_investigations",
            )
        self._running[org_id] = self._running.get(org_id, 0) + 1

    def release(self, org_id: uuid.UUID) -> None:
        left = self._running.get(org_id, 0) - 1
        if left > 0:
            self._running[org_id] = left
        else:
            self._running.pop(org_id, None)

    def clear(self) -> int:
        """Forget every run (for the demo reset); running tasks are cancelled."""
        for task in list(self._tasks):
            task.cancel()
        count = len(self._items)
        self._items.clear()
        self._orgs.clear()
        return count

    def start(
        self,
        llm: LLMClient,
        data: FinancialData,
        as_of: date,
        store: InvestigationStore,
        auditor: InvestigationAuditor,
        orchestrator: InvestigationOrchestrator | None = None,
    ) -> InvestigationProgress:
        """Start a run whose slot the caller already holds (``acquire``) and whose audit trail
        has been opened (``auditor.requested``); the slot is released when the run ends."""
        investigation_id = auditor.investigation_id
        now = _now()
        timeline = build_timeline([], [], running=True)
        progress = InvestigationProgress(
            investigation_id=investigation_id,
            entity_id=data.entity_id,
            entity_name=data.display_name,
            as_of=as_of,
            ai_mode=getattr(llm, "ai_mode", "live"),
            status="running",
            started_at=now,
            updated_at=now,
            current_stage=None,
            stages=[],
            agents=timeline.agents,
            timeline=timeline,
            events=[],
        )
        self._items[investigation_id] = progress
        self._orgs[investigation_id] = auditor.org_id
        while len(self._items) > self.keep:
            oldest = next(iter(self._items))
            self._items.pop(oldest)
            self._orgs.pop(oldest, None)
        task = asyncio.create_task(
            self._run(
                orchestrator or InvestigationOrchestrator(auditor.wrap(llm)),
                data,
                as_of,
                store,
                progress,
                auditor,
            )
        )
        self._tasks.add(task)  # keep a reference until it finishes
        task.add_done_callback(self._tasks.discard)
        return progress

    async def _run(
        self,
        orchestrator: InvestigationOrchestrator,
        data: FinancialData,
        as_of: date,
        store: InvestigationStore,
        progress: InvestigationProgress,
        auditor: InvestigationAuditor,
    ) -> None:
        def listen(rec: Recorder) -> None:
            _apply(progress, rec)

        try:
            investigation = await orchestrator.investigate(
                data, as_of, investigation_id=progress.investigation_id, listener=listen
            )
        except AppError as exc:
            progress.status = "failed"
            progress.error = ProgressError(code=exc.instance_code, message=exc.detail or str(exc))
            await auditor.failed(exc)
        except asyncio.CancelledError as exc:  # demo reset
            await auditor.failed(exc)
            raise
        except Exception as exc:  # the task must always end in a reportable state
            log.exception("investigation_task_failed")
            progress.status = "failed"
            progress.error = ProgressError(code="internal_error", message=type(exc).__name__)
            await auditor.failed(exc)
        else:
            store.save(investigation, auditor.org_id)
            progress.status = "completed"
            await auditor.completed(investigation)
        finally:
            self.release(auditor.org_id)
        _refresh(progress, running=False)


def _apply(progress: InvestigationProgress, rec: Recorder) -> None:
    progress.stages = list(rec.stages)
    progress.events = list(rec.events)
    progress.current_stage = rec.current
    _refresh(progress, running=True)


def _refresh(progress: InvestigationProgress, *, running: bool) -> None:
    """Rebuild the eight-step timeline and agent states from the recorded stages and events."""
    progress.timeline = build_timeline(progress.stages, progress.events, running=running)
    progress.agents = progress.timeline.agents
    progress.updated_at = _now()
