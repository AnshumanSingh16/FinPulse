"""Keeps recent investigations so they can be inspected after the request (e.g. during a demo).

In memory (bounded, most recent first) and, if ``INVESTIGATIONS_DIR`` is set, also written as
one JSON file per investigation. Persistence to PostgreSQL is a later phase.

Every investigation belongs to the organisation that ran it; lookups for another organisation
behave exactly as if it did not exist.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from pathlib import Path

from finpulse.investigation.schemas import Investigation, InvestigationSummary
from finpulse.observability.logging import get_logger

log = get_logger("finpulse.investigation.store")


class InvestigationStore:
    def __init__(self, keep: int = 50, directory: Path | None = None) -> None:
        self.keep = keep
        self.directory = directory
        self._items: OrderedDict[uuid.UUID, tuple[uuid.UUID, Investigation]] = OrderedDict()

    def save(self, investigation: Investigation, org_id: uuid.UUID) -> None:
        self._items[investigation.investigation_id] = (org_id, investigation)
        self._items.move_to_end(investigation.investigation_id)
        while len(self._items) > self.keep:
            self._items.popitem(last=False)
        if self.directory is not None:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                path = self.directory / f"{investigation.investigation_id}.json"
                path.write_text(investigation.model_dump_json(indent=2), encoding="utf-8")
                log.info("investigation_saved", path=str(path))
            except OSError as exc:  # never lose the response over a disk problem
                log.warning("investigation_save_failed", error=str(exc))

    def get(self, investigation_id: uuid.UUID, org_id: uuid.UUID) -> Investigation | None:
        found = self._items.get(investigation_id)
        return found[1] if found and found[0] == org_id else None

    def clear(self) -> int:
        """Forget every kept investigation (for the demo reset). Files on disk are left alone."""
        count = len(self._items)
        self._items.clear()
        return count

    def summaries(self, org_id: uuid.UUID) -> list[InvestigationSummary]:
        return [
            InvestigationSummary.of(inv)
            for org, inv in reversed(self._items.values())
            if org == org_id
        ]
