"""Runs the agents in dependency order: the five analysts in parallel, then the red team on
their verified findings, then the senior synthesis on everything verified.

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
from finpulse.agents.schemas import AgentRun, IntelligenceReport, Usage
from finpulse.core.errors import LLMUnavailableError, NotFoundError

DISCLAIMER = (
    "AI-generated analysis of deterministic results calculated from synthetic data. Every "
    "statement was checked by a deterministic verifier: it cites the evidence it rests on, and "
    "every number it states appears in that evidence. Interpretations (AI_INTERPRETATION) are "
    "judgements, not facts. This is not a credit score, credit assessment or lending decision."
)


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


async def run_pipeline(llm: LLMClient, pack: EvidencePack) -> IntelligenceReport:
    runs = await run_agents(llm, pack)
    senior = runs.get("senior_synthesis")
    succeeded = [r for r in runs.values() if r.status == "succeeded"]
    status = "complete" if len(succeeded) == len(runs) else "failed" if not succeeded else "partial"
    return IntelligenceReport(
        entity=pack.entity,
        as_of=pack.as_of,
        status=status,
        evidence_pack_sha256=pack.sha256,
        evidence_items=len(pack.items),
        agents=runs,
        synthesis=senior.output if senior and senior.status == "succeeded" else None,
        usage=Usage(
            input_tokens=sum(r.usage.input_tokens for r in runs.values()),
            output_tokens=sum(r.usage.output_tokens for r in runs.values()),
            calls=sum(r.usage.calls for r in runs.values()),
        ),
        disclaimer=DISCLAIMER,
    )
