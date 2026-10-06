"""Render the scoring configuration as Markdown, so the published methodology
(docs/FINANCIAL_PASSPORT.md) is generated from — and tested against — the real configuration."""

from __future__ import annotations

from decimal import Decimal

from finpulse.analytics.registry import CATALOGUE
from finpulse.scoring.config import ScoringModel

START, END = "<!-- generated:factors:start -->", "<!-- generated:factors:end -->"


def _num(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _pct(value: Decimal) -> str:
    return f"{_num(value * 100)}%"


def render_factor_tables(model: ScoringModel) -> str:
    lines = [START, ""]
    for code, d in model.dimensions.items():
        lines += [
            f"### {d.name} — {_pct(d.weight)} of the score (`{code}`)",
            "",
            d.description,
            "",
            "| Metric | Weight | Curve (metric value → points) | If not applicable |",
            "|---|---|---|---|",
        ]
        for f in d.factors:
            unit = CATALOGUE[f.metric].unit
            curve = " · ".join(f"{_num(x)} → {_num(y)}" for x, y in f.breakpoints)
            na = (
                f"{_num(f.not_applicable_points)} points"
                if f.not_applicable_points is not None
                else "excluded"
            )
            lines.append(
                f"| `{f.metric}` ({CATALOGUE[f.metric].name}, {unit}) | {_pct(f.weight)} "
                f"| {curve} | {na} |"
            )
        lines.append("")
    lines += [
        "### Bands",
        "",
        "| Score | Band | Meaning |",
        "|---|---|---|",
        *(f"| ≥ {_num(b.min_score)} | {b.label} | {b.description} |" for b in model.bands),
        "",
        END,
    ]
    return "\n".join(lines)


def generated_block(document: str) -> str:
    return document[document.index(START) : document.index(END) + len(END)]


def main() -> None:
    """``python -m finpulse.scoring.methodology <doc.md>``: rewrite the generated block."""
    import sys
    from pathlib import Path

    from finpulse.scoring.config import load_model

    if len(sys.argv) != 2:
        sys.exit("usage: python -m finpulse.scoring.methodology <path to FINANCIAL_PASSPORT.md>")
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(generated_block(text), render_factor_tables(load_model())))


if __name__ == "__main__":
    main()
