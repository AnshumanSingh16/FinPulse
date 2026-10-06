import type { DimensionScore, ScoreChange } from "@finpulse/contracts";
import { ChevronDown, Link2 } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { TimeSeriesChart } from "@/components/charts/time-series";
import { BandBadge } from "@/components/fp/badges";
import { Disclaimer, PageHeader, Panel } from "@/components/fp/layout";
import { BandScale, ScoreBar, type BandRange } from "@/components/fp/meter";
import { Sparkline } from "@/components/fp/sparkline";
import { ApiErrorPanel } from "@/components/fp/states";
import { getPassport, getPassportHistory, getPassportModel } from "@/lib/api/finpulse";
import { evidenceHref } from "@/lib/evidence-link";
import { formatDate, formatMetric, formatNumber, formatPercent, toNumber } from "@/lib/format";
import { entityContext, type EntityPageProps } from "@/lib/page";
import { TONE_CLASSES, bandTone } from "@/lib/presentation";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Financial Passport" };

type Band = { code: string; label: string; min_score: string };

function bandRanges(bands: Band[]): BandRange[] {
  const asc = [...bands].sort((a, b) => Number(a.min_score) - Number(b.min_score));
  return asc.map((b, i) => ({
    code: b.code,
    label: b.label,
    min: Number(b.min_score),
    max: i + 1 < asc.length ? Number(asc[i + 1]!.min_score) : 100,
    tone: bandTone(b.code),
  }));
}

function bandFor(score: number | null, ranges: BandRange[]): BandRange | undefined {
  if (score === null) return undefined;
  return [...ranges].reverse().find((r) => score >= r.min);
}

export default async function PassportPage(props: EntityPageProps) {
  const { entityId, asOf } = await entityContext(props);
  let data;
  try {
    const [passport, history, model] = await Promise.all([
      getPassport(entityId, asOf),
      getPassportHistory(entityId, asOf, 12),
      getPassportModel(),
    ]);
    data = { passport, history, model };
  } catch (error) {
    return <ApiErrorPanel error={error} what="the Financial Passport" />;
  }
  const { passport, history, model } = data;
  const fh = passport.financial_health;
  const ranges = bandRanges(model.bands);
  const score = toNumber(fh.score);
  const series = history.points.map((p) => ({ date: p.as_of, score: toNumber(p.score) }));
  const changes = [...history.changes].reverse();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Financial Passport"
        eyebrow={`As of ${formatDate(passport.as_of)} · ${passport.model.name} v${passport.model.version}`}
        description="A multidimensional financial-health profile: six dimensions scored 0–100 from the analytics metrics, combined into a prototype Financial Health score. Every point traces to a metric."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Panel
          className="lg:col-span-2"
          title="Financial Health"
          description="Prototype score — not a credit score."
        >
          <div className="flex flex-col gap-5">
            <div className="flex items-end gap-3">
              <span className="text-6xl leading-none font-semibold tracking-tight">
                {formatNumber(fh.score, 1)}
              </span>
              <span className="mb-1 text-sm text-muted-foreground">/ 100</span>
              <span className="mb-1 ml-auto">
                <BandBadge band={fh.band?.label} size="md" />
              </span>
            </div>
            <BandScale bands={ranges} score={score} />
            <dl className="grid grid-cols-3 gap-3 border-t pt-4 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground">Confidence</dt>
                <dd className="font-medium">{formatNumber(fh.confidence, 2)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Status</dt>
                <dd className="font-medium">{fh.provisional ? "Provisional" : "Established"}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Band</dt>
                <dd className="font-medium">{fh.band?.label ?? "—"}</dd>
              </div>
            </dl>
            {fh.band ? (
              <p className="text-xs text-pretty text-muted-foreground">{fh.band.description}</p>
            ) : null}
          </div>
        </Panel>
        <Panel
          className="lg:col-span-3"
          title="Historical trend"
          description="Financial Health at each month-end, recomputed from the data as it stood then."
        >
          <TimeSeriesChart
            data={series}
            series={[
              { key: "score", label: "Financial Health", color: "var(--chart-1)", area: true },
            ]}
            unit="score"
            domain={[0, 100]}
            references={ranges.filter((r) => r.min > 0).map((r) => ({ y: r.min, label: r.label }))}
            height={250}
          />
        </Panel>
      </div>

      <section className="flex flex-col gap-3" aria-labelledby="dims">
        <h2 id="dims" className="text-sm font-semibold">
          Six dimensions
        </h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {passport.dimensions.map((d) => (
            <DimensionCard
              key={d.code}
              dimension={d}
              trend={history.points.map((p) => toNumber(p.dimensions[d.code]))}
              band={bandFor(toNumber(d.score), ranges)}
              entityId={entityId}
              asOf={asOf}
            />
          ))}
        </div>
      </section>

      <Panel
        title="Explanation of score changes"
        description="Month by month, which factors moved the score — calculated by the scoring engine, not written by AI."
      >
        {changes.length === 0 ? (
          <p className="text-sm text-muted-foreground">No earlier month-end to compare with.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <ol className="flex flex-col divide-y">
              {changes.slice(0, 4).map((c) => (
                <ChangeRow key={c.to_as_of} change={c} />
              ))}
            </ol>
            {changes.length > 4 ? (
              <details className="group">
                <summary className="flex cursor-pointer list-none items-center gap-1 text-xs font-medium text-primary">
                  <ChevronDown className="size-3.5 transition group-open:rotate-180" aria-hidden />
                  Earlier months ({changes.length - 4})
                </summary>
                <ol className="mt-3 flex flex-col divide-y border-t pt-3">
                  {changes.slice(4).map((c) => (
                    <ChangeRow key={c.to_as_of} change={c} />
                  ))}
                </ol>
              </details>
            ) : null}
          </div>
        )}
      </Panel>

      <Disclaimer>{passport.disclaimer}</Disclaimer>
    </div>
  );
}

function DimensionCard({
  dimension: d,
  trend,
  band,
  entityId,
  asOf,
}: {
  dimension: DimensionScore;
  trend: (number | null)[];
  band?: BandRange;
  entityId: string;
  asOf?: string;
}) {
  const tone = band?.tone ?? "neutral";
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-xs sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">{d.name}</h3>
          <p className="text-[11px] text-muted-foreground">
            Weight {formatPercent(d.weight, { digits: 0 })} · confidence{" "}
            {formatNumber(d.confidence, 2)}
          </p>
        </div>
        <Sparkline values={trend} width={84} height={28} domain={[0, 100]} />
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-3xl leading-none font-semibold">{formatNumber(d.score, 1)}</span>
        {band ? (
          <span className={cn("text-xs font-medium", TONE_CLASSES[tone].text)}>{band.label}</span>
        ) : null}
      </div>
      <ScoreBar value={toNumber(d.score)} tone={tone} />
      <p className="text-xs text-pretty text-muted-foreground">{d.summary}</p>
      <details className="group rounded-lg border">
        <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-xs font-medium">
          Factors &amp; evidence ({d.factors.length})
          <ChevronDown className="size-3.5 transition group-open:rotate-180" aria-hidden />
        </summary>
        <ul className="flex flex-col divide-y border-t">
          {d.factors.map((f) => (
            <li key={f.metric_code} className="flex flex-col gap-1 px-3 py-2.5">
              <div className="flex items-start justify-between gap-2">
                <Link
                  href={evidenceHref(entityId, `metric:${f.metric_code}`, { asOf })}
                  className="inline-flex items-center gap-1 text-xs font-medium hover:text-primary"
                >
                  <Link2 className="size-3" aria-hidden />
                  {f.metric_name}
                </Link>
                <span className="tabular text-xs font-semibold">
                  {f.points === null ? "—" : `${formatNumber(f.points, 0)} pts`}
                </span>
              </div>
              <div className="tabular flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
                <span>
                  Value {formatMetric(f.metric_value, f.metric_unit, { code: f.metric_code })}
                </span>
                <span>Weight {formatPercent(f.effective_weight, { digits: 0 })}</span>
                <span>Adds {formatNumber(f.contribution_to_overall, 1)} to overall</span>
              </div>
              <p className="text-[11px] text-pretty text-muted-foreground">{f.explanation}</p>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function ChangeRow({ change: c }: { change: ScoreChange }) {
  const delta = toNumber(c.delta) ?? 0;
  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-sm font-medium">
          {formatDate(c.from_as_of)} → {formatDate(c.to_as_of)}
        </span>
        <span className="tabular text-sm">
          {formatNumber(c.from_score, 1)} → {formatNumber(c.to_score, 1)}{" "}
          <span
            className={cn(
              "font-semibold",
              delta < 0
                ? "text-status-critical"
                : delta > 0
                  ? "text-text-good"
                  : "text-muted-foreground",
            )}
          >
            ({formatNumber(c.delta, 1, true)})
          </span>
        </span>
        {c.from_band !== c.to_band ? (
          <span className="text-xs text-muted-foreground">
            band {c.from_band} → {c.to_band}
          </span>
        ) : null}
      </div>
      {c.drivers.length ? (
        <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
          {c.drivers.slice(0, 4).map((d) => (
            <li key={d.dimension + d.metric_code} className="flex items-start gap-2 text-xs">
              <span
                className={cn(
                  "tabular mt-px w-12 shrink-0 text-right font-semibold",
                  (toNumber(d.impact) ?? 0) < 0 ? "text-status-critical" : "text-text-good",
                )}
              >
                {formatNumber(d.impact, 1, true)}
              </span>
              <span className="text-muted-foreground">{d.text}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">{c.summary}</p>
      )}
    </li>
  );
}
