"""Deterministic identifiers: the same scenario and seed always yield the same UUIDs, so a
re-seeded database is identical row for row and tests can refer to stable ids."""

from __future__ import annotations

import uuid

NAMESPACE = uuid.UUID("6f1c2b0e-5d7a-4c1e-9b8f-2a4e6d0c9f17")


class IdFactory:
    def __init__(self, scenario_code: str, seed: int) -> None:
        self._prefix = f"{scenario_code}/{seed}"

    def __call__(self, kind: str, key: str | int) -> uuid.UUID:
        return uuid.uuid5(NAMESPACE, f"{self._prefix}/{kind}/{key}")


DEMO_ORG_ID = uuid.uuid5(NAMESPACE, "organization/finpulse-demo")
