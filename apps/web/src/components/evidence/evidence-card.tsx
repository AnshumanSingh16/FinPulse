import type { EvidenceItem, Metric } from "@finpulse/contracts";
import { Database } from "lucide-react";
import Link from "next/link";

import { StatementTypeBadge } from "@/components/fp/badges";
import { formatMetric, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

const KIND_TYPE: Record<string, string> = {
  fact: "FACT",
  calculated_metric: "CALCULATED_METRIC",
  forecast: "FORECAST",
  assumption: "ASSUMPTION",
};

export const SOURCE_LABEL: Record<string, string> = {
  data: "Source data",
  analytics: "Analytics engine",
  passport: "Financial Passport",
  early_warning: "Early warning engine",
  stress: "Stress-test engine",
};

const grouped = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 4 });

/** Values exactly as the engine emitted them; numeric strings only get digit grouping. */
function showValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  const s = String(v);
  return /^-?\d+(\.\d+)?$/.test(s) ? grouped.format(Number(s)) : s;
}

export function EvidenceCard({
  item,
  metric,
  focused = false,
  href,
  citedBy,
}: {
  item: EvidenceItem;
  metric?: Metric;
  focused?: boolean;
  href?: string;
  citedBy?: React.ReactNode;
}) {
  const values = Object.entries(item.values ?? {});
  return (
    <article
      id={item.id}
      className={cn(
        "flex scroll-mt-24 flex-col gap-3 rounded-lg border bg-card p-4",
        focused && "border-primary/60 ring-2 ring-primary/15",
      )}
    >
      <header className="flex flex-wrap items-center gap-2">
        <StatementTypeBadge type={KIND_TYPE[item.kind] ?? ""} />
        <span className="text-[11px] text-muted-foreground">
          {SOURCE_LABEL[item.source] ?? item.source}
        </span>
        {href ? (
          <Link
            href={href}
            className="ml-auto font-mono text-[11px] text-muted-foreground hover:text-primary"
          >
            {item.id}
          </Link>
        ) : (
          <span className="ml-auto font-mono text-[11px] text-muted-foreground">{item.id}</span>
        )}
      </header>
      <div>
        <h3 className="text-sm font-semibold">{item.title}</h3>
        <p className="mt-1 text-sm text-pretty text-muted-foreground">{item.text}</p>
      </div>
      {metric ? (
        <div className="flex flex-col gap-2 rounded-md bg-muted/40 p-3 text-xs">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="tabular text-base font-semibold text-foreground">
              {formatMetric(metric.value, metric.unit, { code: metric.code })}
            </span>
            <span className="text-muted-foreground">
              {metric.period.label} · {metric.confidence} confidence
            </span>
          </div>
          <p className="text-pretty">
            <span className="font-medium">Method. </span>
            {metric.method}
          </p>
          {Object.keys(metric.components ?? {}).length ? (
            <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-0.5">
              {Object.entries(metric.components ?? {}).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="truncate text-muted-foreground">{titleCase(k)}</dt>
                  <dd className="tabular text-right">{showValue(v)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {metric.sources?.length ? (
            <ul className="flex flex-col gap-1 border-t pt-2">
              {metric.sources.map((s, i) => (
                <li key={i} className="flex items-start gap-1.5 text-muted-foreground">
                  <Database className="mt-0.5 size-3 shrink-0" aria-hidden />
                  <span>
                    {s.description} · <span className="tabular">{s.record_count}</span> record
                    {s.record_count === 1 ? "" : "s"} in <code>{s.table}</code>
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : values.length ? (
        <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-0.5 rounded-md bg-muted/40 p-3 text-xs">
          {values.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="truncate text-muted-foreground">{titleCase(k)}</dt>
              <dd className="tabular min-w-0 text-right break-words">{showValue(v)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {citedBy}
    </article>
  );
}
