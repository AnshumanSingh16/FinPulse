"""Early warnings and the risk summary.

Warnings are detected by the deterministic early-warning engine from the entity's records at
request time, using the versioned rule configuration. No language model decides whether a
warning exists; the AI layer will later explain and investigate these warnings, not create them.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from finpulse.api.deps import DataSourceDep, OrgDep
from finpulse.api.routers.entities import AsOf, EntityId
from finpulse.early_warning import RULES, detect_warnings, load_config, risk_summary
from finpulse.early_warning.config import SEVERITIES, Severity
from finpulse.early_warning.engine import config_ref
from finpulse.early_warning.schemas import (
    Category,
    RiskSummary,
    RuleCatalogue,
    RuleInfo,
    WarningsReport,
)
from finpulse.services.entities import load_entity, resolve_as_of

router = APIRouter(prefix="/api/v1", tags=["early-warning"])


@router.get(
    "/entities/{entity_id}/warnings",
    response_model=WarningsReport,
    summary="Early-warning signals detected by deterministic rules",
)
async def warnings(
    entity_id: EntityId,
    source: DataSourceDep,
    org_id: OrgDep,
    as_of: AsOf = None,
    min_severity: Annotated[
        Severity | None, Query(description="Only warnings at least this severe")
    ] = None,
    category: Annotated[Category | None, Query(description="Only this category")] = None,
) -> WarningsReport:
    data = await load_entity(source, org_id, entity_id)
    report = detect_warnings(data, resolve_as_of(data, as_of), load_config())
    if min_severity is None and category is None:
        return report
    floor = SEVERITIES.index(min_severity) if min_severity else 0
    kept = [
        w
        for w in report.warnings
        if SEVERITIES.index(w.severity) >= floor and (category is None or w.category == category)
    ]
    return report.model_copy(update={"warnings": kept})


@router.get(
    "/entities/{entity_id}/risk-summary",
    response_model=RiskSummary,
    summary="Overall early-warning risk: level, index, categories, trend and 12-month timeline",
)
async def summary(
    entity_id: EntityId, source: DataSourceDep, org_id: OrgDep, as_of: AsOf = None
) -> RiskSummary:
    data = await load_entity(source, org_id, entity_id)
    return risk_summary(data, resolve_as_of(data, as_of), load_config())


@router.get(
    "/meta/early-warning-rules",
    response_model=RuleCatalogue,
    tags=["meta"],
    summary="The early-warning rules and their configured thresholds",
)
async def rule_catalogue() -> RuleCatalogue:
    config = load_config()
    return RuleCatalogue(
        config=config_ref(config),
        name=config.config.name,
        disclaimer=config.config.disclaimer,
        severity_points=config.summary.points.model_dump(),
        risk_levels={s: v for s, v in config.summary.levels.defined()},
        rules=[
            RuleInfo(
                code=code,
                category=rule.category,
                about=rule.about,
                affected_metric=rule.metric_ref(),
                direction=rule.direction,
                parameters=config.params(code).model_dump(mode="json"),
            )
            for code, rule in RULES.items()
        ],
    )
