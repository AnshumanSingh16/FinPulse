import type { EarlyWarning, WarningEvidence } from "@finpulse/contracts";
import { ArrowRight, ChevronDown, FileSearch } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { TimeSeriesChart } from "@/components/charts/time-series";
import { RiskBadge, SeverityBadge, ToneBadge } from "@/components/fp/badges";
import { Disclaimer, KeyValue, PageHeader, Panel } from "@/components/fp/layout";
import { RiskTimeline } from "@/components/fp/risk-timeline";
import { ApiErrorPanel, EmptyState, toErrorInfo } from "@/components/fp/states";
import { getRiskSummary, getWarnings } from "@/lib/api/finpulse";
import { evidenceHref } from "@/lib/evidence-link";
import { formatDate, formatMetric, formatPercent, titleCase, toNumber } from "@/lib/format";
import { entityContext, one, type EntityPageProps } from "@/lib/page";
import { TONE_CLASSES, label, severityTone } from "@/lib/presentation";
import { SEVERITY_ORDER } from "@/lib/severity";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Early Warning Center" };

export default async function WarningsPage(props: EntityPageProps) {
  const { entityId, asOf, search } = await entityContext(props);
  let data;
  try {
    const [warnings, risk] = await Promise.all([
      getWarnings(entityId, asOf),
      getRiskSummary(entityId, asOf),
    ]);
    data = { warnings, risk };
  } catch (error) {
    return <ApiErrorPanel error={toErrorInfo(error)} what="early warnings" />;
  }
  const { warnings, risk } = data;
  const selectedId = one(search.warning);
  const selected = warnings.warnings.find((w) => w.id === selectedId) ?? warnings.warnings[0];
  const href = (id: string) => {
    const q = new URLSearchParams();
    if (asOf) q.set("asOf", asOf);
    q.set("warning", id);
    return `?${q.toString()}`;
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Early Warning Center"
        eyebrow={`As of ${formatDate(warnings.as_of)} · ${warnings.config.id} v${warnings.config.version}`}
        description="Deterioration detected by deterministic rules that compare the entity with its own earlier state. No AI decides whether a warning exists."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryTile title="Risk level">
          <div className="flex items-center gap-2">
            <span className="text-2xl font-semibold">{label(risk.risk_level)}</span>
            <RiskBadge level={risk.risk_level} />
          </div>
          <span className="text-xs text-muted-foreground">
            Early-warning index {risk.early_warning_index}/100
          </span>
        </SummaryTile>
        <SummaryTile title="Active warnings by severity">
          <div className="grid grid-cols-4 gap-2">
            {SEVERITY_ORDER.map((s) => (
              <div key={s} className="flex flex-col items-start gap-1">
                <span className="text-2xl leading-none font-semibold">{risk.counts[s]}</span>
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <span className={cn("size-2 rounded-full", TONE_CLASSES[severityTone(s)].dot)} />
                  {label(s)}
                </span>
              </div>
            ))}
          </div>
        </SummaryTile>
        <SummaryTile title="First signs">
          <span className="text-2xl font-semibold">
            {risk.first_warning_on ? formatDate(risk.first_warning_on) : "None"}
          </span>
          <span className="text-xs text-muted-foreground">Warnings at every month-end since</span>
        </SummaryTile>
        <SummaryTile
          title={`Trend vs ${risk.trend.compared_with ? formatDate(risk.trend.compared_with) : "earlier"}`}
        >
          <span className="text-2xl font-semibold capitalize">{risk.trend.direction}</span>
          <span className="text-xs text-pretty text-muted-foreground">
            {risk.trend.new.length} new · {risk.trend.resolved.length} resolved ·{" "}
            {risk.trend.escalated.length} escalated
          </span>
        </SummaryTile>
      </div>

      <Panel
        title="Timeline"
        description="Early-warning index and level at each month-end, recomputed from the data as it stood then."
      >
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <TimeSeriesChart
              data={risk.timeline.map((p) => ({ date: p.as_of, index: p.index }))}
              series={[
                { key: "index", label: "Early-warning index", color: "var(--chart-2)", area: true },
              ]}
              unit="count"
              domain={[0, 100]}
              height={200}
            />
          </div>
          <div className="flex flex-col justify-center lg:col-span-2">
            <RiskTimeline points={risk.timeline} />
          </div>
        </div>
      </Panel>

      {warnings.warnings.length === 0 ? (
        <EmptyState title="No active warnings">
          No rule threshold is crossed as of {formatDate(warnings.as_of)}.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          <Panel
            className="lg:col-span-2"
            title={`Active warnings (${warnings.warnings.length})`}
            bodyClassName="p-0 sm:p-0"
          >
            <ul className="divide-y">
              {warnings.warnings.map((w) => (
                <li key={w.id}>
                  <Link
                    href={href(w.id)}
                    scroll={false}
                    aria-current={w.id === selected?.id ? "true" : undefined}
                    className={cn(
                      "flex flex-col gap-1.5 border-l-2 px-4 py-3 hover:bg-muted/50",
                      w.id === selected?.id
                        ? "border-l-primary bg-muted/60"
                        : "border-l-transparent",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <SeverityBadge severity={w.severity} />
                      <span className="text-[11px] text-muted-foreground">
                        {titleCase(w.category)}
                      </span>
                      <span className="ml-auto text-[11px] text-muted-foreground">
                        {titleCase(w.status)}
                      </span>
                    </div>
                    <span className="text-sm font-medium">{w.title}</span>
                    <span className="tabular text-xs text-muted-foreground">
                      {w.affected_metric.name}:{" "}
                      {formatMetric(w.previous_value, w.affected_metric.unit, {
                        code: w.affected_metric.code,
                      })}{" "}
                      →{" "}
                      <span className="font-medium text-foreground">
                        {formatMetric(w.current_value, w.affected_metric.unit, {
                          code: w.affected_metric.code,
                        })}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Panel>
          {selected ? <WarningDetail warning={selected} entityId={entityId} asOf={asOf} /> : null}
        </div>
      )}

      <details className="group rounded-xl border bg-card">
        <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-3 text-sm font-medium">
          All rules evaluated ({warnings.rules.length})
          <ChevronDown className="size-4 transition group-open:rotate-180" aria-hidden />
        </summary>
        <div className="overflow-x-auto border-t">
          <table className="w-full text-xs">
            <thead className="bg-muted text-muted-foreground">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Rule</th>
                <th className="px-4 py-2 text-left font-medium">Category</th>
                <th className="px-4 py-2 text-left font-medium">State</th>
                <th className="px-4 py-2 text-left font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {warnings.rules.map((r) => (
                <tr key={r.rule} className="border-t">
                  <td className="px-4 py-2 font-mono">{r.rule}</td>
                  <td className="px-4 py-2">{titleCase(r.category)}</td>
                  <td className="px-4 py-2">
                    <ToneBadge
                      tone={
                        r.state === "triggered"
                          ? "warning"
                          : r.state === "clear"
                            ? "good"
                            : "neutral"
                      }
                      icon={null}
                    >
                      {titleCase(r.state)}
                    </ToneBadge>
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">{r.reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <Disclaimer>{warnings.disclaimer}</Disclaimer>
    </div>
  );
}

function SummaryTile({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border bg-card p-4 shadow-xs sm:p-5">
      <span className="text-xs font-medium text-muted-foreground">{title}</span>
      {children}
    </div>
  );
}

function WarningDetail({
  warning: w,
  entityId,
  asOf,
}: {
  warning: EarlyWarning;
  entityId: string;
  asOf?: string;
}) {
  const t = w.threshold;
  const m = w.affected_metric;
  const tiers = Object.entries(t.tiers);
  return (
    <Panel
      className="lg:col-span-3"
      title={
        <span className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={w.severity} size="md" />
          <span className="text-base">{w.title}</span>
        </span>
      }
      description={`${w.id} · rule ${w.rule} · first detected ${formatDate(w.first_detected_on)} · ${titleCase(w.status)} · ${w.trend}`}
      actions={
        <Link
          href={evidenceHref(entityId, `warning:${w.id}`, { asOf })}
          className="flex items-center gap-1 text-xs font-medium text-primary"
        >
          <FileSearch className="size-3.5" aria-hidden /> Evidence
        </Link>
      }
    >
      <div className="flex flex-col gap-5">
        <section className="flex flex-col gap-1.5">
          <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            Explanation
          </h3>
          <p className="text-sm text-pretty">{w.description}</p>
          {w.trend === "persistent" ? (
            <p className="text-xs text-muted-foreground">
              Persistent: the condition is present but not getting worse, so it is reported one
              severity lower than its tier.
            </p>
          ) : null}
        </section>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <section className="flex flex-col gap-2 rounded-lg border p-3">
            <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Affected metric
            </h3>
            <div className="text-sm font-medium">
              {m.name} <code className="text-[11px] text-muted-foreground">{m.code}</code>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="tabular text-sm text-muted-foreground">
                {formatMetric(w.previous_value, m.unit, { code: m.code })}
              </span>
              <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
              <span className="tabular text-xl font-semibold">
                {formatMetric(w.current_value, m.unit, { code: m.code })}
              </span>
              {w.change_pct ? (
                <span className="tabular text-xs text-muted-foreground">
                  ({formatPercent(w.change_pct, { signed: true })})
                </span>
              ) : null}
            </div>
            <KeyValue
              items={[
                [
                  "Now",
                  `${formatDate(w.current_period.start)}${w.current_period.end !== w.current_period.start ? ` – ${formatDate(w.current_period.end)}` : ""}`,
                ],
                [
                  "Compared with",
                  w.previous_period
                    ? `${formatDate(w.previous_period.start)}${w.previous_period.end !== w.previous_period.start ? ` – ${formatDate(w.previous_period.end)}` : ""}`
                    : "—",
                ],
              ]}
            />
          </section>
          <section className="flex flex-col gap-2 rounded-lg border p-3">
            <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Threshold
            </h3>
            <p className="text-xs text-muted-foreground">{t.measure}</p>
            <div className="tabular text-sm">
              Observed <span className="font-semibold">{formatMetric(t.observed, t.unit)}</span>{" "}
              {t.operator === ">=" ? "≥" : "≤"}{" "}
              <span className="font-semibold">{formatMetric(t.value, t.unit)}</span> (
              {label(t.tier)} tier)
            </div>
            <ol className="grid grid-cols-4 gap-1">
              {tiers.map(([tier, value]) => (
                <li
                  key={tier}
                  className={cn(
                    "flex flex-col rounded-md border px-1.5 py-1 text-[11px]",
                    tier === t.tier
                      ? TONE_CLASSES[severityTone(tier)].badge
                      : "text-muted-foreground",
                  )}
                >
                  <span className="font-medium">{label(tier)}</span>
                  <span className="tabular">
                    {t.operator === ">=" ? "≥" : "≤"} {formatMetric(value, t.unit)}
                  </span>
                </li>
              ))}
            </ol>
            {toNumber(t.scale) !== 1 ? (
              <p className="text-[11px] text-muted-foreground">
                Configured tiers shown; for this entity they are scaled ×{t.scale} for its normal
                revenue volatility (the crossed value above is already scaled).
              </p>
            ) : null}
          </section>
        </div>

        <section className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            Evidence ({w.evidence.length})
          </h3>
          <ul className="flex flex-col gap-2">
            {w.evidence.map((e) => (
              <EvidenceRow
                key={e.id}
                evidence={e}
                entityId={entityId}
                warningId={w.id}
                asOf={asOf}
              />
            ))}
          </ul>
        </section>
      </div>
    </Panel>
  );
}

function rawValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  const n =
    typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v)
      ? Number(v)
      : typeof v === "number"
        ? v
        : null;
  if (n !== null && Math.abs(n) >= 1000)
    return n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  return String(v);
}

function EvidenceRow({
  evidence: e,
  entityId,
  warningId,
  asOf,
}: {
  evidence: WarningEvidence;
  entityId: string;
  warningId: string;
  asOf?: string;
}) {
  const values = Object.entries(e.values ?? {});
  return (
    <li className="rounded-lg border p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm text-pretty">{e.text}</p>
        <Link
          href={evidenceHref(entityId, `warning:${warningId}:${e.id}`, { asOf })}
          className="shrink-0 font-mono text-[11px] text-muted-foreground hover:text-primary"
        >
          {e.id}
        </Link>
      </div>
      {values.length ? (
        <dl className="tabular mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] sm:grid-cols-3">
          {values.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-2 border-b border-dashed py-0.5">
              <dt className="truncate text-muted-foreground">{k}</dt>
              <dd className="font-medium">{rawValue(v)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {e.sources?.length || e.metric_codes?.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
          {e.metric_codes?.map((c) => (
            <Link
              key={c}
              href={evidenceHref(entityId, `metric:${c}`, { asOf })}
              className="rounded border px-1.5 py-0.5 font-mono hover:text-primary"
            >
              {c}
            </Link>
          ))}
          {e.sources?.map((s) => (
            <span key={s.table + s.description} className="rounded border px-1.5 py-0.5">
              {s.record_count} {s.table.replace(/_/g, " ")} · {s.description}
            </span>
          ))}
        </div>
      ) : null}
    </li>
  );
}
