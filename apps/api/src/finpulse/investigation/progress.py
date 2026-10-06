"""Live progress of investigations running in the background.

``POST /entities/{id}/investigations`` starts one and returns at once; the UI polls
``GET /investigations/{id}/progress``, which is rebuilt from the orchestrator's own events as
they happen (stage started/completed, agent started/completed/failed) — nothing is simulated.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime

from finpulse.agents.catalogue import AGENTS
from finpulse.agents.llm import LLMClient
from finpulse.analytics.inputs import FinancialData
from finpulse.core.errors import AppError
from finpulse.investigation.orchestrator import InvestigationOrchestrator, Recorder
from finpulse.investigation.schemas import AgentProgress, InvestigationProgress, ProgressError
from finpulse.investigation.store import InvestigationStore
from finpulse.observability.logging import get_logger

log = get_logger("finpulse.investigation.progress")
SKIPPED_STAGES = {"red_team_challenge": ["red_team"], "senior_synthesis": ["senior_synthesis"]}


def _now() -> datetime:
    return datetime.now(UTC)


class ProgressTracker:
    def __init__(self, keep: int = 50) -> None:
        self.keep = keep
        self._items: dict[uuid.UUID, InvestigationProgress] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def get(self, investigation_id: uuid.UUID) -> InvestigationProgress | None:
        return self._items.get(investigation_id)

    def start(
        self,
        llm: LLMClient,
        data: FinancialData,
        as_of: date,
        store: InvestigationStore,
        orchestrator: InvestigationOrchestrator | None = None,
    ) -> InvestigationProgress:
        investigation_id = uuid.uuid4()
        now = _now()
        progress = InvestigationProgress(
            investigation_id=investigation_id,
            entity_id=data.entity_id,
            entity_name=data.display_name,
            as_of=as_of,
            status="running",
            started_at=now,
            updated_at=now,
            current_stage=None,
            stages=[],
            agents=[AgentProgress(agent=n, title=s.title) for n, s in AGENTS.items()],
            events=[],
        )
        self._items[investigation_id] = progress
        while len(self._items) > self.keep:
            self._items.pop(next(iter(self._items)))
        task = asyncio.create_task(
            self._run(orchestrator or InvestigationOrchestrator(llm), data, as_of, store, progress)
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
        except Exception as exc:  # the task must always end in a reportable state
            log.exception("investigation_task_failed")
            progress.status = "failed"
            progress.error = ProgressError(code="internal_error", message=type(exc).__name__)
        else:
            store.save(investigation)
            progress.status = "completed"
        progress.updated_at = _now()


def _apply(progress: InvestigationProgress, rec: Recorder) -> None:
    progress.stages = list(rec.stages)
    progress.events = list(rec.events)
    progress.current_stage = rec.current
    progress.updated_at = _now()
    agents = {a.agent: a for a in progress.agents}
    event = rec.events[-1]
    name = event.data.get("agent")
    if event.event == "agent_started" and name in agents:
        agents[name].state = "running"
    elif event.event in ("agent_completed", "agent_failed") and name in agents:
        a = agents[name]
        a.state = "succeeded" if event.event == "agent_completed" else "failed"
        a.claims = event.data.get("claims")
        a.attempts = event.data.get("attempts")
        a.error = event.data.get("error")
    elif event.event == "stage_completed" and event.data.get("status") == "skipped":
        for n in SKIPPED_STAGES.get(event.stage, []):
            agents[n].state = "skipped"
