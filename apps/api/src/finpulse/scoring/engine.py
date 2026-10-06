"""Score a Financial Passport from an analytics report. Pure and deterministic.

Arithmetic (all Decimal, rounded only for display):

    factor points      = interpolate(metric value, factor curve)                  0–100
    dimension score    = Σ points_f × w_f / Σ w_f        over factors that could be scored
    health score       = Σ score_d × W_d / Σ W_d         over dimensions that could be scored
    contribution_f     = points_f × (w_f / Σ w_f) × (W_d / Σ W_d)
    health score       = Σ contribution_f                (exactly — every point is traceable)
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

from finpulse.analytics.schemas import FinancialMetricsReport, Metric
from finpulse.scoring.config import DimensionConfig, FactorConfig, ScoringModel
from finpulse.scoring.format import format_points, format_value, signed
from finpulse.scoring.schemas import (
    Band,
    ChangeDriver,
    DimensionChange,
    DimensionScore,
    Driver,
    FactorScore,
    FactorStatus,
    FinancialHealth,
    ModelRef,
    Passport,
    ScoreChange,
)

NEUTRAL = Decimal(50)
STRENGTH_MIN_POINTS = Decimal(70)
CONCERN_MAX_POINTS = Decimal(50)
TOP_DRIVERS = 3
CHANGE_DRIVERS = 5
MIN_CHANGE_IMPACT = Decimal("0.05")


def q(value: Decimal, places: str = "0.1") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def interpolate(x: Decimal, breakpoints: Sequence[tuple[Decimal, Decimal]]) -> Decimal:
    """Straight-line interpolation between breakpoints, flat beyond the ends."""
    (x0, y0), (xn, yn) = breakpoints[0], breakpoints[-1]
    if x <= x0:
        return y0
    if x >= xn:
        return yn
    for (a, fa), (b, fb) in pairwise(breakpoints):
        if a <= x <= b:
            return fa + (fb - fa) * (x - a) / (b - a)
    raise AssertionError("unreachable: breakpoints are increasing")  # pragma: no cover


def model_ref(model: ScoringModel) -> ModelRef:
    return ModelRef(
        id=model.model.id,
        version=model.model.version,
        name=model.model.name,
        config_sha256=model.sha256,
    )


# --- factors and dimensions ---------------------------------------------------------------------


class _RawFactor:
    """A factor before weights are re-normalised."""

    def __init__(self, cfg: FactorConfig, metric: Metric, model: ScoringModel) -> None:
        self.cfg, self.metric = cfg, metric
        self.points: Decimal | None = None
        self.effective_weight = Decimal(0)
        self.status: FactorStatus = "excluded"
        self.confidence = Decimal(0)
        if metric.availability == "available" and metric.value is not None:
            self.points = interpolate(metric.value, cfg.breakpoints)
            self.status = "scored"
            self.confidence = getattr(model.confidence, metric.confidence or "low")
        elif metric.availability == "not_applicable" and cfg.not_applicable_points is not None:
            self.points = cfg.not_applicable_points
            self.status = "scored_not_applicable"
            self.confidence = Decimal(1)  # we know it does not apply


def _explain(raw: _RawFactor, effective_weight: Decimal) -> str:
    m = raw.metric
    share = f"{q(effective_weight * 100, '1')}% of the dimension"
    if raw.status == "scored" and raw.points is not None:
        return (
            f"{m.name} of {format_value(m.value, m.unit)} scores {format_points(raw.points)}/100 "
            f"({share})."
        )
    if raw.status == "scored_not_applicable" and raw.points is not None:
        reason = m.notes[0].rstrip(".") if m.notes else "Not applicable"
        return f"{m.name}: {reason}, so it scores {format_points(raw.points)}/100 ({share})."
    reason = m.notes[0] if m.notes else "No value."
    return f"{m.name} not scored: {reason} Its weight is shared among the other factors."


def _dimension(
    code: str, cfg: DimensionConfig, metrics: dict[str, Metric], model: ScoringModel
) -> tuple[DimensionScore, list[_RawFactor]]:
    raws = [_RawFactor(f, metrics[f.metric], model) for f in cfg.factors]
    scored_weight = sum((r.cfg.weight for r in raws if r.points is not None), Decimal(0))
    factors: list[FactorScore] = []
    total = Decimal(0)
    for raw in raws:
        eff = raw.cfg.weight / scored_weight if raw.points is not None else Decimal(0)
        raw.effective_weight = eff
        contribution = (raw.points or Decimal(0)) * eff
        total += contribution
        factors.append(
            FactorScore(
                metric_code=raw.metric.code,
                metric_name=raw.metric.name,
                metric_value=raw.metric.value,
                metric_unit=raw.metric.unit,
                metric_period=raw.metric.period,
                metric_availability=raw.metric.availability,
                metric_confidence=raw.metric.confidence,
                status=raw.status,
                points=None if raw.points is None else q(raw.points),
                weight=raw.cfg.weight,
                effective_weight=q(eff, "0.0001"),
                contribution_to_dimension=q(contribution, "0.01"),
                contribution_to_overall=Decimal(0),  # filled once dimension weights are known
                explanation=_explain(raw, eff),
            )
        )
    confidence = sum((r.cfg.weight * r.confidence for r in raws), Decimal(0))
    score = total if scored_weight > 0 else None
    summary = _dimension_summary(cfg.name, score, raws)
    return (
        DimensionScore(
            code=code,
            name=cfg.name,
            description=cfg.description,
            score=None if score is None else q(score),
            weight=cfg.weight,
            effective_weight=Decimal(0),
            confidence=q(confidence, "0.01"),
            factors=factors,
            summary=summary,
        ),
        raws,
    )


def _dimension_summary(name: str, score: Decimal | None, raws: list[_RawFactor]) -> str:
    if score is None:
        return f"{name}: not enough data to score."
    scored = [(r.points, r.cfg.metric, r) for r in raws if r.points is not None]
    text = f"{name} {format_points(score)}/100."
    if len(scored) > 1:
        best_points, _, best = max(scored, key=lambda t: (t[0], t[1]))
        worst_points, _, worst = min(scored, key=lambda t: (t[0], t[1]))
        if best is not worst:
            text += (
                f" Strongest: {best.metric.name.lower()} ({format_points(best_points)}); "
                f"weakest: {worst.metric.name.lower()} ({format_points(worst_points)})."
            )
    return text


# --- passport -----------------------------------------------------------------------------------


def score_passport(report: FinancialMetricsReport, model: ScoringModel) -> Passport:
    metrics = {m.code: m for m in report.metrics}
    built = [_dimension(code, cfg, metrics, model) for code, cfg in model.dimensions.items()]
    scored_weight = sum((d.weight for d, _ in built if d.score is not None), Decimal(0))

    dimensions: list[DimensionScore] = []
    drivers: list[Driver] = []
    overall = Decimal(0)
    for dim, raws in built:
        dim_eff = dim.weight / scored_weight if dim.score is not None else Decimal(0)
        factor_scores = []
        for raw, fs in zip(raws, dim.factors, strict=True):
            f_eff = raw.effective_weight
            contribution = (raw.points or Decimal(0)) * f_eff * dim_eff
            overall += contribution
            factor_scores.append(
                fs.model_copy(update={"contribution_to_overall": q(contribution, "0.0001")})
            )
            if raw.points is None:
                continue
            impact = (raw.points - NEUTRAL) * f_eff * dim_eff
            value = format_value(raw.metric.value, raw.metric.unit)
            if raw.points >= STRENGTH_MIN_POINTS:
                drivers.append(
                    Driver(
                        kind="strength",
                        dimension=dim.name,
                        metric_code=raw.cfg.metric,
                        impact=q(impact, "0.01"),
                        text=f"{raw.cfg.strength} ({raw.metric.name.lower()}: {value}).",
                    )
                )
            elif raw.points < CONCERN_MAX_POINTS:
                drivers.append(
                    Driver(
                        kind="concern",
                        dimension=dim.name,
                        metric_code=raw.cfg.metric,
                        impact=q(impact, "0.01"),
                        text=f"{raw.cfg.concern} ({raw.metric.name.lower()}: {value}).",
                    )
                )
        dimensions.append(
            dim.model_copy(
                update={"effective_weight": q(dim_eff, "0.0001"), "factors": factor_scores}
            )
        )

    confidence = sum(
        (d.weight * d.confidence for d in dimensions), Decimal(0)
    )  # configured weights: a dimension we could not score counts as zero confidence
    score = q(overall) if scored_weight > 0 else None
    band_cfg = model.band_for(score) if score is not None else None
    strengths = sorted(
        (d for d in drivers if d.kind == "strength"), key=lambda d: (-d.impact, d.metric_code)
    )
    concerns = sorted(
        (d for d in drivers if d.kind == "concern"), key=lambda d: (d.impact, d.metric_code)
    )
    return Passport(
        entity=report.entity,
        as_of=report.as_of,
        model=model_ref(model),
        financial_health=FinancialHealth(
            score=score,
            band=Band(code=band_cfg.code, label=band_cfg.label, description=band_cfg.description)
            if band_cfg
            else None,
            confidence=q(confidence, "0.01"),
            provisional=confidence < model.confidence.provisional_below,
        ),
        dimensions=dimensions,
        strengths=strengths[:TOP_DRIVERS],
        concerns=concerns[:TOP_DRIVERS],
        analytics_engine_version=report.engine_version,
        disclaimer=model.model.disclaimer,
    )


# --- explaining a change ------------------------------------------------------------------------


def explain_change(
    previous: Passport, current: Passport, limit: int = CHANGE_DRIVERS
) -> ScoreChange | None:
    """Attribute the change in score between two passports to individual factors.

    Each factor's impact is the change in its contribution to the overall score, so the impacts
    of all factors add up to the change in score (before display rounding)."""
    a, b = previous.financial_health, current.financial_health
    if a.score is None or b.score is None or a.band is None or b.band is None:
        return None
    before = {(d.code, f.metric_code): f for d in previous.dimensions for f in d.factors}
    movers: list[ChangeDriver] = []
    for dim in current.dimensions:
        for f in dim.factors:
            old = before[(dim.code, f.metric_code)]
            impact = f.contribution_to_overall - old.contribution_to_overall
            if abs(impact) < MIN_CHANGE_IMPACT:
                continue
            direction = "rose" if (f.metric_value or 0) > (old.metric_value or 0) else "fell"
            if f.metric_value == old.metric_value:
                direction = "was unchanged"
            movers.append(
                ChangeDriver(
                    dimension=dim.name,
                    metric_code=f.metric_code,
                    metric_name=f.metric_name,
                    from_value=old.metric_value,
                    to_value=f.metric_value,
                    from_points=old.points,
                    to_points=f.points,
                    impact=q(impact, "0.01"),
                    text=(
                        f"{dim.name}: {f.metric_name.lower()} {direction} "
                        f"({format_value(old.metric_value, old.metric_unit)} → "
                        f"{format_value(f.metric_value, f.metric_unit)}), "
                        f"{signed(impact)} points"
                    ),
                )
            )
    movers.sort(key=lambda m: (-abs(m.impact), m.metric_code))
    delta = b.score - a.score
    verb = "rose" if delta > 0 else "fell" if delta < 0 else "was unchanged"
    summary = f"Financial health {verb} from {a.score} to {b.score} ({signed(delta)})."
    if a.band.code != b.band.code:
        summary += f" Band moved from {a.band.label} to {b.band.label}."
    if movers:
        summary += " Main drivers: " + "; ".join(m.text for m in movers[:3]) + "."
    old_dims = {d.code: d for d in previous.dimensions}
    return ScoreChange(
        from_as_of=previous.as_of,
        to_as_of=current.as_of,
        from_score=a.score,
        to_score=b.score,
        delta=q(delta),
        from_band=a.band.code,
        to_band=b.band.code,
        dimensions=[
            DimensionChange(
                code=d.code,
                name=d.name,
                from_score=old_dims[d.code].score,
                to_score=d.score,
                delta=None
                if d.score is None or old_dims[d.code].score is None
                else q(d.score - (old_dims[d.code].score or Decimal(0))),
            )
            for d in current.dimensions
        ],
        drivers=movers[:limit],
        summary=summary,
    )
