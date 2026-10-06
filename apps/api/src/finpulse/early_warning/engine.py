"""Entry points: the warnings for one entity as of one date, and the risk summary built on them.

Pure and deterministic — the same data, date and configuration always give the same warnings,
IDs and timestamps. No I/O, no clock, no LLM: whether a warning exists is decided here, by the
configured rules. The AI layer may later explain and investigate warnings, never create them.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from finpulse.analytics.inputs import FinancialData
from finpulse.analytics.schemas import EntityRef
from finpulse.early_warning.config import SEVERITIES, EarlyWarningConfig, Severity
from finpulse.early_warning.rules import RULES, Outcome, rank
from finpulse.early_warning.schemas import (
    Category,
    CategoryRisk,
    ConfigRef,
    EarlyWarning,
    RiskLevel,
    RiskSummary,
    RiskTrend,
    RuleOutcome,
    SeverityCounts,
    Status,
    Threshold,
    TimelinePoint,
    WarningBrief,
    WarningsReport,
)
from finpulse.early_warning.snapshots import History, months_back
from finpulse.scoring.history import history_dates, previous_month_end

ENGINE_VERSION = "1.0.0"
IST = timezone(timedelta(hours=5, minutes=30))
CATEGORY_LABELS: dict[Category, str] = {
    "revenue": "Revenue",
    "expenses": "Expenses",
    "cash": "Cash",
    "liquidity": "Liquidity",
    "receivables": "Receivables & collections",
    "debt": "Debt",
    "concentration": "Concentration",
    "transactions": "Transactions",
    "volatility": "Volatility",
}
CATEGORY_ORDER = list(CATEGORY_LABELS)
LEVEL_LABELS: dict[RiskLevel, str] = {
    "none": "No",
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "critical": "Critical",
}


class Evaluator:
    """Runs every rule at any date, memoising per date (history and streaks revisit dates)."""

    def __init__(self, data: FinancialData, config: EarlyWarningConfig) -> None:
        self.data = data
        self.config = config
        self.history = History(data)
        self._cache: dict[date, dict[str, Outcome]] = {}

    def outcomes(self, at: date) -> dict[str, Outcome]:
        if at not in self._cache:
            self._cache[at] = {
                code: rule.run(self.history, at, self.config.params(code))
                for code, rule in RULES.items()
            }
        return self._cache[at]

    def triggered(self, at: date) -> dict[str, Outcome]:
        return {c: o for c, o in self.outcomes(at).items() if o.state == "triggered"}

    def in_data(self, at: date) -> bool:
        return self.history.first_date is not None and at >= self.history.first_date


# --- warnings -----------------------------------------------------------------------------------


def _streak(ev: Evaluator, code: str, as_of: date) -> tuple[date, Severity | None]:
    """When the current unbroken run of month-ends with this warning began, and the severity at
    the previous month-end (None if it was not present)."""
    first = as_of
    previous: Severity | None = None
    current = previous_month_end(as_of)
    for i in range(ev.config.summary.streak_months):
        if not ev.in_data(current):
            break
        outcome = ev.outcomes(current)[code]
        if outcome.state != "triggered":
            break
        if i == 0:
            previous = outcome.severity
        first = current
        current = previous_month_end(current)
    return first, previous


def _status(severity: Severity, previous: Severity | None) -> Status:
    if previous is None:
        return "new"
    if rank(severity) > rank(previous):
        return "escalated"
    if rank(severity) < rank(previous):
        return "easing"
    return "ongoing"


def warning_id(entity_id: object, rule: str, first: date) -> str:
    digest = hashlib.sha256(f"{entity_id}|{rule}|{first.isoformat()}".encode()).hexdigest()
    return f"EW-{digest[:10].upper()}"


def _warning(ev: Evaluator, outcome: Outcome, as_of: date) -> EarlyWarning:
    rule = RULES[outcome.rule]
    f = outcome.finding
    if f is None or not outcome.severity or not outcome.tier or outcome.tier_value is None:
        raise ValueError(f"{outcome.rule}: not a triggered outcome")
    first, previous = _streak(ev, outcome.rule, as_of)
    persistent = not f.deteriorating
    change = f.current - f.previous if f.current is not None and f.previous is not None else None
    change_pct = (
        (change / abs(f.previous)).quantize(Decimal("0.0001"))
        if change is not None and f.previous
        else None
    )
    tiers = ev.config.params(outcome.rule).tiers
    return EarlyWarning(
        id=warning_id(ev.data.entity_id, outcome.rule, first),
        rule=outcome.rule,
        category=rule.category,
        severity=outcome.severity,
        title=(f.persistent_title or f.title) if persistent else f.title,
        description=f.description,
        affected_metric=f.metric or rule.metric_ref(),
        current_value=f.current,
        previous_value=f.previous,
        change=change,
        change_pct=change_pct,
        current_period=f.current_period,
        previous_period=f.previous_period,
        threshold=Threshold(
            measure=f.measure_label,
            observed=f.measure,
            operator=">=" if rule.direction == "above" else "<=",
            value=outcome.tier_value,
            unit=f.measure_unit,
            tier=outcome.tier,
            tiers={s: v for s, v in tiers.defined()},
            scale=f.scale,
            direction=rule.direction,
        ),
        trend="persistent" if persistent else "deteriorating",
        status=_status(outcome.severity, previous),
        first_detected_on=first,
        detected_at=datetime.combine(as_of, time(23, 59, 59), IST),
        evidence=f.evidence,
    )


def _sort_key(w: EarlyWarning) -> tuple[int, int, str]:
    return (-rank(w.severity), CATEGORY_ORDER.index(w.category), w.rule)


def _entity(data: FinancialData) -> EntityRef:
    return EntityRef(
        id=data.entity_id, display_name=data.display_name, kind=data.kind, segment=data.segment
    )


def config_ref(config: EarlyWarningConfig) -> ConfigRef:
    return ConfigRef(id=config.config.id, version=config.config.version, sha256=config.sha256)


def _warnings(ev: Evaluator, as_of: date) -> list[EarlyWarning]:
    return sorted((_warning(ev, o, as_of) for o in ev.triggered(as_of).values()), key=_sort_key)


def detect_warnings(
    data: FinancialData, as_of: date, config: EarlyWarningConfig, evaluator: Evaluator | None = None
) -> WarningsReport:
    ev = evaluator or Evaluator(data, config)
    return WarningsReport(
        entity=_entity(data),
        as_of=as_of,
        engine_version=ENGINE_VERSION,
        config=config_ref(config),
        warnings=_warnings(ev, as_of),
        rules=[
            RuleOutcome(rule=code, category=RULES[code].category, state=o.state, reason=o.reason)
            for code, o in ev.outcomes(as_of).items()
        ],
        disclaimer=config.config.disclaimer,
    )


# --- risk summary -------------------------------------------------------------------------------


def _counts(severities: list[Severity]) -> SeverityCounts:
    return SeverityCounts(**{s: severities.count(s) for s in SEVERITIES}, total=len(severities))


def _level(severities: list[Severity], config: EarlyWarningConfig) -> tuple[RiskLevel, int]:
    points = config.summary.points
    index = min(100, sum(getattr(points, s) for s in severities))
    if not severities:
        return "none", index
    by_index = config.summary.levels.grade(Decimal(index), "above")
    worst = max(severities, key=rank)
    level: Severity = worst if by_index is None or rank(worst) >= rank(by_index) else by_index
    return level, index


def _point(ev: Evaluator, at: date) -> TimelinePoint:
    found = ev.triggered(at)
    severities = [o.severity for o in found.values() if o.severity]
    level, index = _level(severities, ev.config)
    return TimelinePoint(
        as_of=at, level=level, index=index, counts=_counts(severities), rules=sorted(found)
    )


def _headline(
    level: RiskLevel,
    counts: SeverityCounts,
    cats: list[CategoryRisk],
    first: date | None,
    as_of: date,
) -> str:
    if counts.total == 0:
        return f"No early warnings: no rule threshold is crossed as of {as_of:%d %b %Y}."
    parts = [f"{getattr(counts, s)} {s}" for s in reversed(SEVERITIES) if getattr(counts, s)]
    names = [c.label.lower() for c in cats[:3]]
    text = (
        f"{LEVEL_LABELS[level]} early-warning risk: {counts.total} warning(s) "
        f"({', '.join(parts)}), mainly in {', '.join(names)}."
    )
    if first is not None and first < as_of:
        text += f" Warnings have been present at every month-end since {first:%d %b %Y}."
    return text


def risk_summary(data: FinancialData, as_of: date, config: EarlyWarningConfig) -> RiskSummary:
    ev = Evaluator(data, config)
    warnings = _warnings(ev, as_of)
    severities = [w.severity for w in warnings]
    level, index = _level(severities, config)
    counts = _counts(severities)

    by_cat: dict[Category, list[EarlyWarning]] = {}
    for w in warnings:
        by_cat.setdefault(w.category, []).append(w)
    categories = sorted(
        (
            CategoryRisk(
                category=c,
                label=CATEGORY_LABELS[c],
                severity=max((w.severity for w in ws), key=rank),
                warnings=len(ws),
                rules=[w.rule for w in ws],
            )
            for c, ws in by_cat.items()
        ),
        key=lambda c: (-rank(c.severity), -c.warnings, CATEGORY_ORDER.index(c.category)),
    )

    first_date = data.transactions[0].posted_on if data.transactions else as_of
    dates = history_dates(as_of, config.summary.timeline_months, first_date)
    timeline = [_point(ev, d) for d in dates]

    first_warning: date | None = None
    for point in reversed(timeline):
        if point.counts.total == 0:
            break
        first_warning = point.as_of

    then = months_back(as_of, config.summary.compare_months)
    if ev.in_data(then):
        before = ev.triggered(then)
        now = ev.triggered(as_of)
        prev_sev = [o.severity for o in before.values() if o.severity]
        prev_level, prev_index = _level(prev_sev, config)
        moved = {
            c: rank(now[c].severity) - rank(before[c].severity)  # type: ignore[arg-type]
            for c in now
            if c in before
        }
        escalated = [c for c, step in moved.items() if step > 0]
        eased = [c for c, step in moved.items() if step < 0]
        direction = (
            "worsening" if index > prev_index else "improving" if index < prev_index else "stable"
        )
        trend = RiskTrend(
            compared_with=then,
            previous_level=prev_level,
            previous_index=prev_index,
            direction=direction,
            new=sorted(set(now) - set(before)),
            resolved=sorted(set(before) - set(now)),
            escalated=sorted(escalated),
            eased=sorted(eased),
        )
    else:
        trend = RiskTrend(
            compared_with=None,
            previous_level=None,
            previous_index=None,
            direction="unknown",
            new=[],
            resolved=[],
            escalated=[],
            eased=[],
        )

    outcomes = ev.outcomes(as_of).values()
    return RiskSummary(
        entity=_entity(data),
        as_of=as_of,
        engine_version=ENGINE_VERSION,
        config=config_ref(config),
        risk_level=level,
        early_warning_index=index,
        headline=_headline(level, counts, categories, first_warning, as_of),
        counts=counts,
        categories=categories,
        top_warnings=[
            WarningBrief(
                id=w.id,
                rule=w.rule,
                category=w.category,
                severity=w.severity,
                title=w.title,
                first_detected_on=w.first_detected_on,
            )
            for w in warnings[: config.summary.top_warnings]
        ],
        trend=trend,
        first_warning_on=first_warning,
        timeline=timeline,
        rules_evaluated=sum(1 for o in outcomes if o.state in ("triggered", "clear")),
        rules_triggered=len(warnings),
        disclaimer=config.config.disclaimer,
    )
