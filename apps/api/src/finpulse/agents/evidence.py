"""The evidence pack: every verified backend output an agent may use, as citable items.

Built deterministically from the analytics metrics, the Financial Passport, the early-warning
engine and the stress-testing engine — no language model is involved. Each item has a stable
id (e.g. ``metric:receivables.days``, ``warning:EW-233FAE5A17``, ``stress:revenue_down_20``) and
a *kind* that fixes how a statement resting on it must be labelled:

    fact               recorded facts about the entity and its data (record counts, dates)
    calculated_metric  values calculated by the deterministic engines (metrics, scores, warnings)
    forecast           projected outcomes of hypothetical stress scenarios
    assumption         assumptions behind a calculation or projection

Agents read these items and cite their ids; the verifier checks every claim against them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from finpulse.analytics import ENGINE_VERSION as ANALYTICS_VERSION
from finpulse.analytics import compute_report
from finpulse.analytics.inputs import FinancialData
from finpulse.analytics.schemas import EntityRef, FinancialMetricsReport, Metric
from finpulse.core.errors import UnprocessableError
from finpulse.early_warning import detect_warnings, risk_summary
from finpulse.early_warning import load_config as load_warning_config
from finpulse.early_warning.engine import ENGINE_VERSION as WARNING_VERSION
from finpulse.early_warning.schemas import RiskSummary
from finpulse.scoring import load_model, with_monthly_change
from finpulse.scoring.format import format_value
from finpulse.scoring.schemas import Passport
from finpulse.stress import ENGINE_VERSION as STRESS_VERSION
from finpulse.stress import PRESETS, StressTestRequest, run_stress_test
from finpulse.stress.schemas import Projection, StressTestResult

PACK_VERSION = "1.0.0"
EvidenceKind = Literal["fact", "calculated_metric", "forecast", "assumption"]
EvidenceSource = Literal["data", "analytics", "passport", "early_warning", "stress"]
Value = Decimal | int | str | bool | None


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: EvidenceKind
    source: EvidenceSource
    title: str
    text: str = Field(description="A deterministic statement of the item, numbers as displayed")
    values: dict[str, Value] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, description="For selecting items per agent")

    def for_prompt(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "values": {k: str(v) if isinstance(v, Decimal) else v for k, v in self.values.items()},
        }


class EvidencePack(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity: EntityRef
    as_of: date
    pack_version: str
    engine_versions: dict[str, str]
    sha256: str = Field(description="Hash of the items: identical inputs give identical packs")
    items: list[EvidenceItem]

    def get(self, item_id: str) -> EvidenceItem | None:
        return self._index().get(item_id)

    def _index(self) -> dict[str, EvidenceItem]:
        cache: dict[str, EvidenceItem] | None = getattr(self, "_cache", None)
        if cache is None:
            cache = {i.id: i for i in self.items}
            object.__setattr__(self, "_cache", cache)
        return cache

    def select(self, *patterns: str) -> list[EvidenceItem]:
        """Items whose id equals a pattern, or starts with it when the pattern ends with '*'."""
        out = []
        for item in self.items:
            for p in patterns:
                if (p.endswith("*") and item.id.startswith(p[:-1])) or item.id == p:
                    out.append(item)
                    break
        return out


# --- helpers ------------------------------------------------------------------------------------


def fmt(value: Decimal | None, unit: str) -> str:
    return format_value(value, unit)  # type: ignore[arg-type]


def _hash(items: list[EvidenceItem]) -> str:
    payload = json.dumps([i.model_dump(mode="json") for i in items], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


# --- builders -----------------------------------------------------------------------------------


def _facts(data: FinancialData, report: FinancialMetricsReport) -> Iterable[EvidenceItem]:
    c = report.coverage
    yield EvidenceItem(
        id="fact:entity",
        kind="fact",
        source="data",
        title="Entity",
        text=f"{data.display_name}: {data.kind} ({data.segment}), amounts in {data.currency}.",
        values={"name": data.display_name, "kind": data.kind, "segment": data.segment},
    )
    yield EvidenceItem(
        id="fact:data_coverage",
        kind="fact",
        source="data",
        title="Data coverage",
        text=(
            f"Bank transactions from {c.first_transaction_on} to {c.last_transaction_on}: "
            f"{c.transaction_count} transactions over {c.complete_months} complete months; "
            f"{c.invoice_count} sales invoices, {c.bill_count} supplier bills, {c.loan_count} "
            f"loans, {c.counter_sale_days} days of walk-in sales; "
            f"{c.uncategorised_transactions} uncategorised transactions."
        ),
        values=c.model_dump(mode="json"),
    )
    limit = sum(a.overdraft_limit_minor for a in data.accounts)
    yield EvidenceItem(
        id="fact:accounts",
        kind="fact",
        source="data",
        title="Bank accounts",
        text=f"{len(data.accounts)} bank account(s); total overdraft limit "
        f"{fmt(Decimal(limit) / 100, 'INR')}.",
        values={"accounts": len(data.accounts), "overdraft_limit": Decimal(limit) / 100},
    )
    yield EvidenceItem(
        id="fact:data_sources",
        kind="fact",
        source="data",
        title="What FinPulse can and cannot see",
        text=(
            "FinPulse uses the entity's bank transactions, invoices, bills, loan schedules and "
            "walk-in sales only. It has no credit-bureau data, so loans that a bureau records "
            "but that leave no trace in these records are invisible, and vice versa. All data "
            "is synthetic."
        ),
    )


def _metrics(report: FinancialMetricsReport) -> Iterable[EvidenceItem]:
    for m in report.metrics:
        yield _metric_item(m)


def _metric_item(m: Metric) -> EvidenceItem:
    values: dict[str, Value] = {"value": m.value, "unit": m.unit, "period": m.period.label}
    for k, v in m.components.items():
        if isinstance(v, Decimal | int | str) or v is None:
            values[k] = v
    if m.availability == "available":
        text = (
            f"{m.name}: {fmt(m.value, m.unit)} ({m.period.label}, {m.period.start} to "
            f"{m.period.end}; confidence {m.confidence})."
        )
    else:
        text = f"{m.name}: not available ({m.availability}: {'; '.join(m.notes)})."
    return EvidenceItem(
        id=f"metric:{m.code}",
        kind="calculated_metric",
        source="analytics",
        title=m.name,
        text=f"{text} Method: {m.method}",
        values=values,
        tags=[m.family],
    )


def _passport(p: Passport) -> Iterable[EvidenceItem]:
    fh = p.financial_health
    yield EvidenceItem(
        id="passport:overall",
        kind="calculated_metric",
        source="passport",
        title="Financial Health (prototype)",
        text=(
            f"Financial Health {fmt(fh.score, 'score')} — band "
            f"{fh.band.label if fh.band else 'n/a'}, confidence {fh.confidence}"
            f"{' (provisional)' if fh.provisional else ''}. "
            "A prototype financial-health profile, not a credit score."
        ),
        values={
            "score": fh.score,
            "band": fh.band.label if fh.band else None,
            "confidence": fh.confidence,
            "provisional": fh.provisional,
        },
    )
    for d in p.dimensions:
        yield EvidenceItem(
            id=f"passport:dimension:{d.code}",
            kind="calculated_metric",
            source="passport",
            title=f"Passport dimension: {d.name}",
            text=f"{d.name}: {fmt(d.score, 'score')} (weight {fmt(d.weight, 'ratio')}). "
            f"{d.summary}",
            values={"score": d.score, "weight": d.weight, "confidence": d.confidence},
            tags=[d.code],
        )
        for f in d.factors:
            yield EvidenceItem(
                id=f"passport:factor:{d.code}:{f.metric_code}",
                kind="calculated_metric",
                source="passport",
                title=f"{d.name} factor: {f.metric_name}",
                text=f.explanation,
                values={
                    "metric_value": f.metric_value,
                    "points": f.points,
                    "weight": f.weight,
                    "contribution_to_overall": f.contribution_to_overall,
                    "status": f.status,
                },
                tags=[d.code],
            )
    change = p.change_from_previous_month
    if change is not None:
        yield EvidenceItem(
            id="passport:change",
            kind="calculated_metric",
            source="passport",
            title="Financial Health change since the previous month-end",
            text=change.summary,
            values={
                "from_as_of": change.from_as_of.isoformat(),
                "from_score": change.from_score,
                "to_score": change.to_score,
                "delta": change.delta,
            },
        )
    yield EvidenceItem(
        id="assumption:passport.method",
        kind="assumption",
        source="passport",
        title="Passport methodology",
        text=(
            f"Scores follow the configured model {p.model.id} v{p.model.version}: judgement-based "
            "weights and curves, not validated against real repayment outcomes. "
            f"{p.disclaimer}"
        ),
    )


def _warnings(summary: RiskSummary, data: FinancialData, as_of: date) -> Iterable[EvidenceItem]:
    config = load_warning_config()
    report = detect_warnings(data, as_of, config)
    for w in report.warnings:
        t = w.threshold
        yield EvidenceItem(
            id=f"warning:{w.id}",
            kind="calculated_metric",
            source="early_warning",
            title=f"Early warning ({w.severity}): {w.title}",
            text=(
                f"[{w.severity.upper()}] {w.title}. {w.description} Measure: {t.measure} = "
                f"{t.observed} (threshold {t.operator} {t.value} for {t.tier}). Trend: {w.trend}; "
                f"status: {w.status}; present at every month-end since {w.first_detected_on}."
            ),
            values={
                "rule": w.rule,
                "category": w.category,
                "severity": w.severity,
                "affected_metric": w.affected_metric.code,
                "current_value": w.current_value,
                "previous_value": w.previous_value,
                "change": w.change,
                "change_pct": w.change_pct,
                "observed": t.observed,
                "threshold": t.value,
                "first_detected_on": w.first_detected_on.isoformat(),
            },
            tags=[w.category, w.rule],
        )
        for ev in w.evidence:
            yield EvidenceItem(
                id=f"warning:{w.id}:{ev.id}",
                kind="calculated_metric",
                source="early_warning",
                title=f"Evidence for {w.title}: {ev.id}",
                text=ev.text,
                values={
                    k: (str(v) if not isinstance(v, Decimal | int | str) and v is not None else v)
                    for k, v in ev.values.items()
                },
                tags=[w.category, w.rule],
            )
    yield EvidenceItem(
        id="risk:summary",
        kind="calculated_metric",
        source="early_warning",
        title="Early-warning risk summary",
        text=summary.headline,
        values={
            "risk_level": summary.risk_level,
            "early_warning_index": summary.early_warning_index,
            "warnings": summary.counts.total,
            "first_warning_on": summary.first_warning_on.isoformat()
            if summary.first_warning_on
            else None,
        },
    )
    trend = summary.trend
    yield EvidenceItem(
        id="risk:trend",
        kind="calculated_metric",
        source="early_warning",
        title="Early-warning trend",
        text=(
            f"Compared with {trend.compared_with}: {trend.direction}; index "
            f"{trend.previous_index} → {summary.early_warning_index}. New: "
            f"{', '.join(trend.new) or 'none'}; resolved: {', '.join(trend.resolved) or 'none'}; "
            f"escalated: {', '.join(trend.escalated) or 'none'}."
        ),
        values={"direction": trend.direction, "previous_index": trend.previous_index},
    )
    yield EvidenceItem(
        id="risk:timeline",
        kind="calculated_metric",
        source="early_warning",
        title="Early-warning level at each month-end",
        text="; ".join(f"{p.as_of}: {p.level} ({p.index})" for p in summary.timeline),
        values={p.as_of.isoformat(): p.level for p in summary.timeline},
    )
    yield EvidenceItem(
        id="assumption:early_warning.method",
        kind="assumption",
        source="early_warning",
        title="Early-warning methodology",
        text=(
            f"Warnings come from {config.config.name} v{config.config.version}: deterministic "
            "rules with judgement-based thresholds, not calibrated against real outcomes. A "
            "condition that is present but not worsening is reported one severity lower. "
            f"{config.config.disclaimer}"
        ),
    )


def _stress(data: FinancialData, as_of: date) -> Iterable[EvidenceItem]:
    model = load_model()
    baseline_done = False
    for code, (name, _) in PRESETS.items():
        try:
            r: StressTestResult = run_stress_test(
                data,
                as_of,
                StressTestRequest(preset=code),
                model,
            )
        except UnprocessableError as exc:
            yield EvidenceItem(
                id=f"stress:{code}",
                kind="forecast",
                source="stress",
                title=f"Stress scenario: {name}",
                text=f"Not applicable to this entity: {exc.detail}",
                values={"applicable": False},
                tags=["scenario"],
            )
            continue
        if not baseline_done:
            baseline_done = True
            for ev in r.evidence:
                if ev.kind == "baseline":
                    yield EvidenceItem(
                        id=f"assumption:stress.{ev.id}",
                        kind="assumption",
                        source="stress",
                        title=f"Stress-test baseline: {ev.id.removeprefix('baseline.')}",
                        text=ev.text,
                        values=dict(ev.values),
                    )
            yield EvidenceItem(
                id="assumption:stress.method",
                kind="assumption",
                source="stress",
                title="Stress-test method",
                text=(
                    f"Projections run {r.horizon_months} months from {r.projection_start}, "
                    f"deterministically, from a 3-month baseline; no seasonality or second-order "
                    f"effects. {r.disclaimer}"
                ),
            )
            yield EvidenceItem(
                id="stress:baseline",
                kind="forecast",
                source="stress",
                title="Baseline projection (no shock)",
                text=_projection_text("Baseline", r.baseline),
                values=_projection_values(r.baseline),
                tags=["baseline"],
            )
        s, b = r.stressed, r.baseline
        fail = f"funds run out around {s.failure_point.date}" if s.failure_point else "no failure"
        yield EvidenceItem(
            id=f"stress:{code}",
            kind="forecast",
            source="stress",
            title=f"Stress scenario: {r.scenario.name}",
            text=(
                f"{r.scenario.name}: risk {r.risk_change.baseline} → {r.risk_change.scenario}; "
                f"closing cash {fmt(b.closing_balance, 'INR')} → {fmt(s.closing_balance, 'INR')}; "
                f"{fail}; projected Financial Health "
                f"{fmt(r.health_impact.baseline_projected_score, 'score')} → "
                f"{fmt(r.health_impact.scenario_score, 'score')}."
            ),
            values={
                "applicable": True,
                **_projection_values(s),
                "baseline_closing_balance": b.closing_balance,
                "risk_baseline": r.risk_change.baseline,
                "risk_scenario": r.risk_change.scenario,
                "health_baseline_projected": r.health_impact.baseline_projected_score,
                "health_scenario": r.health_impact.scenario_score,
                "health_change": r.health_impact.change,
            },
            tags=["scenario"],
        )
        for ev in r.evidence:
            if ev.kind == "baseline":
                continue
            yield EvidenceItem(
                id=f"stress:{code}:{ev.id}",
                kind="assumption" if ev.kind == "shock" else "forecast",
                source="stress",
                title=f"{r.scenario.name}: {ev.id}",
                text=ev.text,
                values=dict(ev.values),
                tags=["scenario_detail"],
            )


def _projection_text(label: str, p: Projection) -> str:
    fail = f"funds run out around {p.failure_point.date}" if p.failure_point else "no failure"
    return (
        f"{label}: revenue {fmt(p.revenue, 'INR')}, expenses {fmt(p.expenses, 'INR')}, net cash "
        f"flow {fmt(p.net_cash_flow, 'INR')}, closing cash {fmt(p.closing_balance, 'INR')}, "
        f"lowest {fmt(p.minimum_balance, 'INR')}; runway {fmt(p.cash_runway_months, 'months')}; "
        f"risk {p.risk.level}; {fail}."
    )


def _projection_values(p: Projection) -> dict[str, Value]:
    return {
        "revenue": p.revenue,
        "expenses": p.expenses,
        "net_cash_flow": p.net_cash_flow,
        "closing_balance": p.closing_balance,
        "minimum_balance": p.minimum_balance,
        "liquidity_ratio": p.liquidity_ratio,
        "cash_runway_months": p.cash_runway_months,
        "risk_level": p.risk.level,
        "failure_date": p.failure_point.date.isoformat() if p.failure_point else None,
        "financial_health": p.financial_health_score,
    }


def build_evidence_pack(data: FinancialData, as_of: date) -> EvidencePack:
    """Every verified backend output for one entity at one date. Pure and deterministic."""
    report = compute_report(data, as_of)
    passport = with_monthly_change(data, as_of, load_model())
    summary = risk_summary(data, as_of, load_warning_config())
    items = [
        *_facts(data, report),
        *_metrics(report),
        *_passport(passport),
        *_warnings(summary, data, as_of),
        *_stress(data, as_of),
    ]
    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate evidence ids")
    return EvidencePack(
        entity=report.entity,
        as_of=as_of,
        pack_version=PACK_VERSION,
        engine_versions={
            "analytics": ANALYTICS_VERSION,
            "early_warning": WARNING_VERSION,
            "stress": STRESS_VERSION,
            "passport_model": f"{passport.model.id}@{passport.model.version}",
        },
        sha256=_hash(items),
        items=items,
    )
