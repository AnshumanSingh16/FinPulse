"""Stress testing: simulate hypothetical shocks against an entity.

Outcomes are calculated by the deterministic projection engine (``finpulse.stress``); nothing
is estimated by a language model.
"""

from __future__ import annotations

from fastapi import APIRouter

from finpulse.api.deps import DataSourceDep, OrgDep
from finpulse.api.routers.entities import EntityId
from finpulse.scoring import load_model
from finpulse.services.entities import load_entity, resolve_as_of
from finpulse.stress import PRESETS, SHOCKS, StressTestRequest, run_stress_test
from finpulse.stress.schemas import PresetOut, ScenarioCatalogue, ShockTypeOut, StressTestResult

router = APIRouter(prefix="/api/v1", tags=["stress testing"])


@router.post(
    "/entities/{entity_id}/stress-test",
    response_model=StressTestResult,
    summary="Run a stress test: baseline vs. scenario projection",
    description=(
        "Give either a `preset` (see `GET /api/v1/meta/stress-scenarios`) or a list of `shocks`, "
        "each `{type, ...parameters}`. Shocks are applied together."
    ),
)
async def stress_test(
    entity_id: EntityId, request: StressTestRequest, source: DataSourceDep, org_id: OrgDep
) -> StressTestResult:
    data = await load_entity(source, org_id, entity_id)
    return run_stress_test(data, resolve_as_of(data, request.as_of), request, load_model())


@router.get(
    "/meta/stress-scenarios",
    response_model=ScenarioCatalogue,
    tags=["meta"],
    summary="Shock types (with parameter schemas) and preset scenarios",
)
async def stress_scenarios() -> ScenarioCatalogue:
    return ScenarioCatalogue(
        shock_types=[
            ShockTypeOut(
                type=code,
                name=shock.name,
                description=shock.description,
                parameters_schema=shock.Params.model_json_schema(),
            )
            for code, shock in SHOCKS.items()
        ],
        presets=[
            PresetOut(code=code, name=name, shocks=shocks)
            for code, (name, shocks) in PRESETS.items()
        ],
    )
