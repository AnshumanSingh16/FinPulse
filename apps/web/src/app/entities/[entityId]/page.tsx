import { ArrowRight, ThumbsDown, ThumbsUp } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { BandBadge, RiskBadge, SeverityBadge } from "@/components/fp/badges";
import { Disclaimer, PageHeader, Panel } from "@/components/fp/layout";
import { RiskTimeline } from "@/components/fp/risk-timeline";
import { Sparkline } from "@/components/fp/sparkline";
import { StatTile } from "@/components/fp/stat";
import { ApiErrorPanel, EmptyState } from "@/components/fp/states";
import { sectionHref } from "@/components/shell/nav";
import {
  getMetricHistory,
  getMetrics,
  getPassport,
  getPassportHistory,
  getRiskSummary,
  getWarnings,
} from "@/lib/api/finpulse";
import { formatDate, formatMetric, formatNumber, toNumber } from "@/lib/format";
import { entityContext, type EntityPageProps } from "@/lib/page";
import { deltaTone, label } from "@/lib/presentation";

export const metadata: Metadata = { title: "Overview" };

export default async function OverviewPage(props: EntityPageProps) {
  const { entityId, asOf } = await entityContext(props);
  let data;
  try {
    const [passport, history, risk, warnings, metrics, metricHistory] = await Promise.all([
      getPassport(entityId, asOf),
      getPassportHistory(entityId, asOf, 12),
      getRiskSummary(entityId, asOf),
      getWarnings(entityId, asOf),
      getMetrics(entityId, asOf),
      getMetricHistory(entityId, asOf, ["cash.runway", "liquidity.ratio"], 4),
    ]);
    data = { passport, history, risk, warnings, metrics, metricHistory };
  } catch (error) {
    return <ApiErrorPanel error={error} what="the overview" />;
  }
  const { passport, history, risk, warnings, metrics, metricHistory } = data;
  const fh = passport.financial_health;
  const change = passport.change_from_previous_month;
  const metric = (code: string) => metrics.metrics.find((m) => m.code === code);
  const runway = metric("cash.runway");
  const liquidity = metric("liquidity.ratio");
  const earlier = metricHistory.points[0];
  // "Was X on date": both values come from the API; the UI compares, never subtracts.
  const delta = (code: string, unit: string) => {
    const now = toNumber(metric(code)?.value);
    const then = toNumber(earlier?.values[code]);
    if (now === null || then === null || !earlier || earlier.as_of === metrics.as_of) return null;
    return {
      text: `was ${formatMetric(then, unit, { code })}`,
      tone: deltaTone(code, now === then ? 0 : now > then ? 1 : -1),
      caption: `on ${formatDate(earlier.as_of)}`,
    };
  };
  const link = (slug: string) => sectionHref(entityId, slug, asOf);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Overview"
        description={risk.headline}
        eyebrow={`As of ${formatDate(passport.as_of)}`}
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          hero
          label="Financial Health (prototype)"
          value={formatNumber(fh.score, 1)}
          badge={<BandBadge band={fh.band?.label} />}
          delta={
            change
              ? {
                  text: `${formatNumber(change.delta, 1, true)} pts`,
                  tone: (toNumber(change.delta) ?? 0) >= 0 ? "good" : "critical",
                  caption: `since ${formatDate(change.from_as_of)}`,
                }
              : null
          }
          trend={
            <Sparkline values={history.points.map((p) => toNumber(p.score))} domain={[0, 100]} />
          }
          sub={
            <>
              Out of 100 · confidence {formatNumber(fh.confidence, 2)}
              {fh.provisional ? " · provisional" : ""}
            </>
          }
        />
        <StatTile
          label="Early-warning risk"
          value={label(risk.risk_level)}
          badge={<RiskBadge level={risk.risk_level} />}
          sub={
            <>
              Index {risk.early_warning_index}/100 · {risk.counts.total} active warning
              {risk.counts.total === 1 ? "" : "s"}
              {risk.trend.direction !== "unknown"
                ? ` · ${risk.trend.direction} vs ${formatDate(risk.trend.compared_with)}`
                : ""}
            </>
          }
        />
        <StatTile
          label="Cash runway"
          value={
            runway?.availability === "available"
              ? formatMetric(runway.value, "months")
              : runway?.availability === "not_applicable"
                ? "Not burning"
                : "n/a"
          }
          delta={runway?.availability === "available" ? delta("cash.runway", "months") : null}
          sub={
            runway?.availability === "not_applicable"
              ? "Money in covers money out over the last 3 months."
              : "Available funds incl. undrawn overdraft ÷ average monthly burn."
          }
        />
        <StatTile
          label="Liquidity ratio"
          value={formatMetric(liquidity?.value, "ratio", { code: "liquidity.ratio" })}
          delta={delta("liquidity.ratio", "ratio")}
          sub="Cash + receivables ÷ short-term obligations. Below 1× means obligations exceed liquid assets."
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Panel
          className="lg:col-span-3"
          title="Major warnings"
          description="Detected by deterministic rules, most severe first."
          actions={
            <Link
              href={link("warnings")}
              className="flex items-center gap-1 text-xs font-medium text-primary"
            >
              Early Warning Center <ArrowRight className="size-3" aria-hidden />
            </Link>
          }
          bodyClassName="p-0 sm:p-0"
        >
          {warnings.warnings.length === 0 ? (
            <div className="p-5">
              <EmptyState title="No active warnings">
                No rule threshold is crossed as of this date.
              </EmptyState>
            </div>
          ) : (
            <ul className="divide-y">
              {warnings.warnings.slice(0, 5).map((w) => (
                <li key={w.id}>
                  <Link
                    href={`${link("warnings")}${asOf ? "&" : "?"}warning=${w.id}`}
                    className="flex items-start gap-3 px-4 py-3 hover:bg-muted/50 sm:px-5"
                  >
                    <SeverityBadge severity={w.severity} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{w.title}</div>
                      <p className="line-clamp-2 text-xs text-muted-foreground">{w.description}</p>
                    </div>
                    <span className="hidden shrink-0 text-[11px] text-muted-foreground sm:block">
                      since {formatDate(w.first_detected_on)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel
          className="lg:col-span-2"
          title="Risk trajectory"
          description="Early-warning level at each month-end."
        >
          <RiskTimeline points={risk.timeline} />
          {risk.first_warning_on ? (
            <p className="mt-3 text-xs text-muted-foreground">
              Warnings present at every month-end since {formatDate(risk.first_warning_on)}.
            </p>
          ) : null}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DriverList
          title="Top financial strengths"
          icon={<ThumbsUp className="size-4 text-text-good" aria-hidden />}
          items={passport.strengths.slice(0, 4)}
          empty="No factor scores clearly above neutral."
        />
        <DriverList
          title="Top risks"
          icon={<ThumbsDown className="size-4 text-status-critical" aria-hidden />}
          items={passport.concerns.slice(0, 4)}
          empty="No factor scores clearly below neutral."
        />
      </div>

      {change ? (
        <Panel
          title="Why the score moved"
          description={`Financial Health ${formatNumber(change.from_score, 1)} → ${formatNumber(change.to_score, 1)} since ${formatDate(change.from_as_of)}`}
          actions={
            <Link
              href={link("passport")}
              className="flex items-center gap-1 text-xs font-medium text-primary"
            >
              Financial Passport <ArrowRight className="size-3" aria-hidden />
            </Link>
          }
        >
          <p className="text-sm text-pretty">{change.summary}</p>
        </Panel>
      ) : null}

      <Disclaimer>{passport.disclaimer}</Disclaimer>
    </div>
  );
}

function DriverList({
  title,
  icon,
  items,
  empty,
}: {
  title: string;
  icon: React.ReactNode;
  items: { text: string; dimension: string; metric_code: string; impact: string }[];
  empty: string;
}) {
  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          {icon}
          {title}
        </span>
      }
      description="From the Financial Passport's factor scores."
    >
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {items.map((d, i) => (
            <li key={d.metric_code + i} className="flex gap-3">
              <span className="tabular mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-semibold">
                {i + 1}
              </span>
              <div className="min-w-0">
                <p className="text-sm text-pretty">{d.text}</p>
                <p className="text-[11px] text-muted-foreground">
                  {label(d.dimension)} · <code>{d.metric_code}</code>
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}
