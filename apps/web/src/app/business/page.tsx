import type { Metadata } from "next";
import { ArrowRight, Building2, User } from "lucide-react";
import Link from "next/link";

import { BandBadge, RiskBadge, SyntheticBadge } from "@/components/fp/badges";
import { PageHeader } from "@/components/fp/layout";
import { ApiErrorPanel, EmptyState, toErrorInfo } from "@/components/fp/states";
import { getEntities, getMetrics, getPassport, getRiskSummary } from "@/lib/api/finpulse";
import { formatMetric, formatNumber, titleCase } from "@/lib/format";
import { SEVERITY_ORDER } from "@/lib/severity";

export const metadata: Metadata = { title: "Business risk · Portfolio" };
export const dynamic = "force-dynamic";

async function loadCard(id: string) {
  const [passport, risk, metrics] = await Promise.all([
    getPassport(id),
    getRiskSummary(id),
    getMetrics(id),
  ]);
  return { passport, risk, runway: metrics.metrics.find((m) => m.code === "cash.runway") };
}

export default async function PortfolioPage() {
  let entities;
  try {
    entities = await getEntities();
  } catch (error) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Portfolio" />
        <ApiErrorPanel error={toErrorInfo(error)} what="the entity list" />
      </div>
    );
  }
  const settled = await Promise.allSettled(entities.map((e) => loadCard(e.id)));
  // Highest early-warning risk first: the review queue order.
  const rows = entities
    .map((entity, i) => ({ entity, result: settled[i] }))
    .sort(
      (a, b) =>
        (b.result?.status === "fulfilled" ? b.result.value.risk.early_warning_index : -1) -
        (a.result?.status === "fulfilled" ? a.result.value.risk.early_warning_index : -1),
    );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Business risk module"
        title="Portfolio"
        description="Every entity under review, highest early-warning risk first, with its prototype Financial Health score and cash runway — calculated by FinPulse's deterministic engines from bank, invoice and loan records."
        actions={<SyntheticBadge />}
      />
      {entities.length === 0 ? (
        <EmptyState title="No entities yet">
          Load the synthetic entities with <code>make db-seed</code>.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {rows.map(({ entity, result }) => {
            const Icon = entity.kind === "individual" ? User : Building2;
            return (
              <Link
                key={entity.id}
                href={`/entities/${entity.id}`}
                className="group flex flex-col gap-4 rounded-xl border bg-card p-5 shadow-xs transition hover:border-primary/40 hover:shadow-md"
              >
                <div className="flex items-start gap-3">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
                    <Icon className="size-4 text-muted-foreground" aria-hidden />
                  </span>
                  <div className="min-w-0">
                    <div className="truncate font-semibold">{entity.display_name}</div>
                    <div className="text-xs text-muted-foreground">
                      {titleCase(entity.kind)} · {titleCase(entity.segment)}
                    </div>
                  </div>
                  <ArrowRight
                    className="ml-auto size-4 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-foreground"
                    aria-hidden
                  />
                </div>
                {result?.status === "fulfilled" ? (
                  <PortfolioStats {...result.value} />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Could not load this entity&apos;s results.
                  </p>
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function PortfolioStats({ passport, risk, runway }: Awaited<ReturnType<typeof loadCard>>) {
  const fh = passport.financial_health;
  const worst = SEVERITY_ORDER.filter((s) => risk.counts[s] > 0);
  return (
    <>
      <div className="grid grid-cols-3 gap-3 border-t pt-4">
        <div className="flex flex-col gap-1">
          <span className="text-[11px] text-muted-foreground">Financial Health</span>
          <span className="text-2xl leading-none font-semibold">{formatNumber(fh.score, 0)}</span>
          <BandBadge band={fh.band?.label} />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[11px] text-muted-foreground">Early-warning risk</span>
          <span className="text-2xl leading-none font-semibold">{risk.early_warning_index}</span>
          <RiskBadge level={risk.risk_level} />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[11px] text-muted-foreground">Cash runway</span>
          <span className="text-2xl leading-none font-semibold">
            {runway?.availability === "available"
              ? formatMetric(runway.value, "months")
              : runway?.availability === "not_applicable"
                ? "—"
                : "n/a"}
          </span>
          <span className="text-[11px] text-muted-foreground">
            {runway?.availability === "not_applicable" ? "Not burning cash" : "at recent burn"}
          </span>
        </div>
      </div>
      <p className="line-clamp-2 text-xs text-pretty text-muted-foreground">
        {risk.counts.total} active warning{risk.counts.total === 1 ? "" : "s"}
        {worst.length ? ` (${worst.map((s) => `${risk.counts[s]} ${s}`).join(", ")})` : ""}
      </p>
    </>
  );
}
