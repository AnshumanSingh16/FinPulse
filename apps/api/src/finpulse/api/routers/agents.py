"""The agentic AI layer.

Agents read the evidence pack — the verified outputs of the deterministic engines — and never
calculate financial facts themselves. Every statement they return has passed the deterministic
verifier: it cites evidence ids, and each number it states appears in the cited evidence.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Path
from pydantic import BaseModel, ConfigDict, Field

from finpulse.agents.catalogue import AGENTS
from finpulse.agents.evidence import EvidencePack, build_evidence_pack
from finpulse.agents.orchestrator import dependency_closure, run_agents, run_pipeline
from finpulse.agents.schemas import AgentInfo, AgentRun, IntelligenceReport
from finpulse.api.deps import DataSourceDep, LLMDep, OrgDep
from finpulse.api.routers.entities import AsOf, EntityId
from finpulse.services.entities import load_entity, resolve_as_of

router = APIRouter(prefix="/api/v1", tags=["agents"])


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: date | None = Field(default=None, description="Defaults to the end of the data")


class SingleAgentResponse(BaseModel):
    result: AgentRun
    dependencies: dict[str, AgentRun] = Field(
        description="Upstream agents that had to run first (the red team and the senior agent "
        "work from the analysts' verified findings)"
    )


async def _pack(
    source: DataSourceDep, org_id: OrgDep, entity_id: EntityId, as_of: date | None
) -> EvidencePack:
    data = await load_entity(source, org_id, entity_id)
    return build_evidence_pack(data, resolve_as_of(data, as_of))


@router.get(
    "/entities/{entity_id}/evidence-pack",
    response_model=EvidencePack,
    summary="The verified evidence the agents read (deterministic; no AI involved)",
)
async def evidence_pack(
    entity_id: EntityId, source: DataSourceDep, org_id: OrgDep, as_of: AsOf = None
) -> EvidencePack:
    return await _pack(source, org_id, entity_id, as_of)


@router.post(
    "/entities/{entity_id}/intelligence",
    response_model=IntelligenceReport,
    summary="Run all seven agents and return the verified intelligence report",
)
async def intelligence(
    entity_id: EntityId,
    source: DataSourceDep,
    org_id: OrgDep,
    llm: LLMDep,
    request: Annotated[AgentRequest | None, Body()] = None,
) -> IntelligenceReport:
    pack = await _pack(source, org_id, entity_id, request.as_of if request else None)
    return await run_pipeline(llm, pack)


@router.post(
    "/entities/{entity_id}/agents/{agent_name}",
    response_model=SingleAgentResponse,
    summary="Run one agent (and any agents whose findings it needs)",
)
async def run_one(
    entity_id: EntityId,
    agent_name: Annotated[str, Path(description='e.g. "risk_investigation"')],
    source: DataSourceDep,
    org_id: OrgDep,
    llm: LLMDep,
    request: Annotated[AgentRequest | None, Body()] = None,
) -> SingleAgentResponse:
    dependency_closure([agent_name])  # 404 for an unknown agent before any work
    pack = await _pack(source, org_id, entity_id, request.as_of if request else None)
    runs = await run_agents(llm, pack, [agent_name])
    result = runs.pop(agent_name)
    return SingleAgentResponse(result=result, dependencies=runs)


@router.get(
    "/meta/agents",
    response_model=list[AgentInfo],
    tags=["meta"],
    summary="The agents, their dependencies, prompt versions and output schemas",
)
async def agent_catalogue() -> list[AgentInfo]:
    return [spec.info() for spec in AGENTS.values()]
