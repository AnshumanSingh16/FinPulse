"""Runs a chosen agent and the agents it depends on (the five analysts in parallel, then the
red team on their verified findings, then the senior synthesis), for the single-agent endpoint.
The full financial investigation workflow is ``finpulse.investigation.orchestrator``.

A failed agent never stops the others: it is reported with its error, and the agents that
depend on it are told it produced nothing. The red team and the senior agent are skipped only
if every analyst failed. If the model could not be reached at all, the whole request fails
with ``llm_unavailable`` rather than returning a report made only of failures.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from finpulse.agents.base import AgentSpec, run_agent
from finpulse.agents.catalogue import AGENTS, ANALYSTS
from finpulse.agents.evidence import EvidencePack
from finpulse.agents.llm import LLMClient
from finpulse.agents.schemas import AgentRun
from finpulse.core.errors import LLMUnavailableError, NotFoundError


def dependency_closure(names: Iterable[str]) -> list[str]:
    """The agents needed to run ``names``, in a valid run order."""
    needed: set[str] = set()

    def add(name: str) -> None:
        if name not in AGENTS:
            raise NotFoundError(
                f"Unknown agent {name!r}.", code="agent_not_found", extra={"known": sorted(AGENTS)}
            )
        if name in needed:
            return
        for dep in AGENTS[name].depends_on:
            add(dep)
        needed.add(name)

    for n in names:
        add(n)
    return [n for n in AGENTS if n in needed]  # AGENTS is in dependency order


def _skipped(spec: AgentSpec, pack: EvidencePack, reason: str) -> AgentRun:
    from finpulse.agents.schemas import AgentErrorInfo

    return AgentRun(
        agent=spec.name,
        title=spec.title,
        status="skipped",
        output=None,
        prompt_version=spec.prompt_version,
        evidence_items=len(spec.select(pack)),
        error=AgentErrorInfo(code="skipped", message=reason),
    )


async def run_agents(
    llm: LLMClient, pack: EvidencePack, names: Iterable[str] | None = None
) -> dict[str, AgentRun]:
    order = dependency_closure(names or AGENTS)
    runs: dict[str, AgentRun] = {}
    analysts = [n for n in order if n in ANALYSTS]
    results = await asyncio.gather(*(run_agent(AGENTS[n], llm, pack) for n in analysts))
    runs.update(zip(analysts, results, strict=True))
    _raise_if_unreachable(runs.values())

    for name in (n for n in order if n not in ANALYSTS):
        spec = AGENTS[name]
        upstream = {d: runs[d] for d in spec.depends_on if d in runs}
        verified = {d: r for d, r in upstream.items() if r.status == "succeeded"}
        if not any(r.status == "succeeded" for d, r in upstream.items() if d in ANALYSTS):
            runs[name] = _skipped(spec, pack, "No analyst agent produced verified findings.")
            continue
        runs[name] = await run_agent(spec, llm, pack, verified)
        _raise_if_unreachable([runs[name]])
    return runs


def _raise_if_unreachable(runs: Iterable[AgentRun]) -> None:
    runs = list(runs)
    if runs and all(r.error is not None and r.error.code == "llm_unavailable" for r in runs):
        raise LLMUnavailableError(runs[0].error.message if runs[0].error else None)
