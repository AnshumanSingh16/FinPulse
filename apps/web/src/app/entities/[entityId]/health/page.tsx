import type { FinancialMetricsReport, Metric, MetricHistory } from "@finpulse/contracts";
import type { Metadata } from "next";
import Link from "next/link";
import { Fragment } from "react";

import { DivergingBars, TimeSeriesChart, type Reference } from "@/components/charts/time-series";
import { BreakdownBars } from "@/components/fp/breakdown";
import { PageHeader, Panel } from "@/components/fp/layout";
import { ApiErrorPanel, toErrorInfo } from "@/components/fp/states";
import { getMetricHistory, getMetrics } from "@/lib/api/finpulse";
import { evidenceHref } from "@/lib/evidence-link";
import { formatDate, formatMetric, formatPercent, toNumber } from "@/lib/format";
import { entityContext, type EntityPageProps } from "@/lib/page";

export const metadata: Metadata = { title: "Financial Health" };

const HISTORY_CODES = [
  "receivables.outstanding",
  "receivables.days",
  "payables.days",
  "debt.outstanding",
  "debt.service_burden",
  "liquidity.ratio",
  "cash.runway",
  "liquidity.overdraft_utilisation",
];

const SECTIONS = [
  ["revenue", "Revenue & expenses"],
  ["cash-flow", "Cash flow"],
  ["receivables", "Receivables"],
  ["payables", "Payables"],
  ["debt", "Debt"],
  ["liquidity", "Liquidity"],
] as const;

export default async function HealthPage(props: EntityPageProps) {
  const { entityId, asOf } = await entityContext(props);
  let report: FinancialMetricsReport;
  let history: MetricHistory;
  try {
    [report, history] = await Promise.all([
      getMetrics(entityId, asOf),
      getMetricHistory(entityId, asOf, HISTORY_CODES, 12),
    ]);
  } catch (error) {
    return <ApiErrorPanel error={toErrorInfo(error)} what="financial metrics" />;
  }
  const m = (code: string) => report.metrics.find((x) => x.code === code);
  const series = (code: string) => report.series.find((s) => s.code === code)?.points ?? [];
  const monthly = series("revenue.monthly").map((p, i) => ({
    date: p.period.start,
    revenue: toNumber(p.value),
    expenses: toNumber(series("expenses.monthly")[i]?.value),
  }));
  const net = series("cashflow.net_monthly").map((p) => ({
    date: p.period.start,
    net: toNumber(p.value),
  }));
  const balance = series("cash.balance").map((p) => ({
    date: p.period.end,
    balance: toNumber(p.value),
  }));
  const hist = (code: string) =>
    history.points.map((p) => ({ date: p.as_of, [code]: toNumber(p.values[code]) }));
  const tile = (code: string) => <MetricTile metric={m(code)} entityId={entityId} asOf={asOf} />;
  const recv = m("receivables.outstanding");
  const debt = m("debt.outstanding");
  const liq = m("liquidity.ratio");
  const rc = recv?.components ?? {};
  const dc = debt?.components ?? {};
  const lc = liq?.components ?? {};

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Financial Health"
        eyebrow={`As of ${formatDate(report.as_of)} · analytics engine ${report.engine_version}`}
        description="Revenue, expenses, cash flow, receivables, payables, debt and liquidity — every value calculated by the deterministic analytics engine from bank, invoice, bill and loan records. Histories are recomputed as of each month-end."
      />
      <nav aria-label="Sections" className="-mx-1 flex gap-1 overflow-x-auto pb-1">
        {SECTIONS.map(([id, label]) => (
          <a
            key={id}
            href={`#${id}`}
            className="rounded-full border bg-card px-3 py-1 text-xs font-medium whitespace-nowrap text-muted-foreground hover:text-foreground"
          >
            {label}
          </a>
        ))}
      </nav>

      <Section
        id="revenue"
        title="Revenue & expenses"
        tiles={[
          tile("revenue.monthly"),
          tile("revenue.growth"),
          tile("expenses.monthly"),
          tile("expenses.growth"),
        ]}
      >
        <Panel
          title="Monthly revenue and expenses"
          description="Excluding GST. Revenue: invoices issued plus walk-in sales; expenses: purchases billed plus operating cash costs."
        >
          <TimeSeriesChart
            data={monthly}
            unit="INR"
            series={[
              { key: "revenue", label: "Revenue", color: "var(--chart-1)" },
              { key: "expenses", label: "Expenses", color: "var(--chart-2)" },
            ]}
            height={260}
          />
        </Panel>
      </Section>

      <Section
        id="cash-flow"
        title="Cash flow"
        tiles={[
          tile("cashflow.net_monthly"),
          tile("cashflow.net_margin"),
          tile("cashflow.positive_months"),
          tile("cash.balance"),
        ]}
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Panel
            title="Net cash flow by month"
            description="All money in minus all money out, including loan disbursements and repayments."
          >
            <DivergingBars data={net} dataKey="net" label="Net cash flow" unit="INR" />
          </Panel>
          <Panel
            title="Month-end cash balance"
            description="Across all accounts; negative means the overdraft is in use."
          >
            <TimeSeriesChart
              data={balance}
              unit="INR"
              series={[
                { key: "balance", label: "Cash balance", color: "var(--chart-1)", area: true },
              ]}
              zeroLine
            />
          </Panel>
        </div>
      </Section>

      <Section
        id="receivables"
        title="Receivables"
        tiles={[
          tile("receivables.outstanding"),
          tile("receivables.days"),
          tile("customers.concentration"),
        ]}
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Panel
            title="Receivables outstanding"
            description="Unpaid invoice balances at each month-end."
            className="lg:col-span-2"
          >
            <TimeSeriesChart
              data={hist("receivables.outstanding")}
              unit="INR"
              series={[
                { key: "receivables.outstanding", label: "Receivables", color: "var(--chart-1)" },
              ]}
            />
          </Panel>
          <Panel
            title="Ageing"
            description={
              recv?.availability === "available"
                ? `${formatPercent(rc.overdue_share as string)} overdue · ${rc.open_documents} open invoices`
                : undefined
            }
          >
            {recv?.availability === "available" ? (
              <BreakdownBars
                rows={[
                  ["Not yet due", "not_yet_due"],
                  ["1–30 days late", "overdue_1_30_days"],
                  ["31–60 days late", "overdue_31_60_days"],
                  ["61–90 days late", "overdue_61_90_days"],
                  ["90+ days late", "overdue_over_90_days"],
                ].map(([label, key]) => ({ label: label!, value: rc[key!] as string }))}
              />
            ) : (
              <NotAvailable metric={recv} />
            )}
          </Panel>
          <Panel
            title="Receivable days (DSO)"
            description="How many days of credit sales are waiting to be collected."
            className="lg:col-span-3"
          >
            <TimeSeriesChart
              data={hist("receivables.days")}
              unit="days"
              series={[
                { key: "receivables.days", label: "Receivable days", color: "var(--chart-1)" },
              ]}
              height={200}
            />
          </Panel>
        </div>
      </Section>

      <Section
        id="payables"
        title="Payables"
        tiles={[
          tile("payables.days"),
          tile("suppliers.concentration"),
          tile("payments.consistency"),
        ]}
      >
        <Panel
          title="Payable days (DPO)"
          description="Unpaid supplier bills relative to purchases in the last 90 days, at each month-end."
        >
          {m("payables.days")?.availability === "available" ? (
            <TimeSeriesChart
              data={hist("payables.days")}
              unit="days"
              series={[{ key: "payables.days", label: "Payable days", color: "var(--chart-2)" }]}
              height={200}
            />
          ) : (
            <NotAvailable metric={m("payables.days")} />
          )}
        </Panel>
      </Section>

      <Section
        id="debt"
        title="Debt"
        tiles={[
          tile("debt.outstanding"),
          tile("debt.service_burden"),
          tile("debt.leverage"),
          tile("debt.new_loans_6m"),
        ]}
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Panel
            title="Debt outstanding"
            description="Loan principal still owed at each month-end."
            className="lg:col-span-2"
          >
            <TimeSeriesChart
              data={hist("debt.outstanding")}
              unit="INR"
              series={[
                { key: "debt.outstanding", label: "Debt outstanding", color: "var(--chart-1)" },
              ]}
            />
          </Panel>
          <Panel
            title="By lender"
            description={
              debt?.availability === "available" ? `${dc.loans ?? 0} loan(s)` : undefined
            }
          >
            {debt?.availability === "available" ? (
              <BreakdownBars
                rows={Object.entries(dc)
                  .filter(([k]) => k.startsWith("lender:"))
                  .map(([k, v]) => ({ label: k.slice(7), value: v as string }))}
              />
            ) : (
              <NotAvailable metric={debt} />
            )}
          </Panel>
          <Panel
            title="Debt-service burden"
            description="Instalments due ÷ operating receipts over 3 months."
            className="lg:col-span-3"
          >
            <TimeSeriesChart
              data={hist("debt.service_burden")}
              unit="ratio"
              series={[
                {
                  key: "debt.service_burden",
                  label: "Debt-service burden",
                  color: "var(--chart-2)",
                },
              ]}
              height={200}
            />
          </Panel>
        </div>
      </Section>

      <Section
        id="liquidity"
        title="Liquidity"
        tiles={[
          tile("liquidity.ratio"),
          tile("cash.runway"),
          tile("buffer.months"),
          tile("liquidity.overdraft_utilisation"),
        ]}
      >
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Panel
            title="Liquidity ratio"
            description="Cash + receivables ÷ short-term obligations, at each month-end."
            className="lg:col-span-2"
          >
            <TimeSeriesChart
              data={hist("liquidity.ratio")}
              unit="ratio"
              code="liquidity.ratio"
              series={[
                { key: "liquidity.ratio", label: "Liquidity ratio", color: "var(--chart-1)" },
              ]}
              references={[{ y: 1, label: "1× — obligations covered" } satisfies Reference]}
            />
          </Panel>
          <Panel
            title="Composition"
            description="At this date, from the liquidity ratio's components."
          >
            {liq?.availability === "available" ? (
              <div className="flex flex-col gap-3">
                <div>
                  <div className="mb-1 text-[11px] font-medium text-muted-foreground uppercase">
                    Assets
                  </div>
                  <BreakdownBars
                    rows={[
                      { label: "Cash", value: lc.cash as string },
                      { label: "Receivables", value: lc.receivables as string },
                    ]}
                  />
                </div>
                <div>
                  <div className="mb-1 text-[11px] font-medium text-muted-foreground uppercase">
                    Obligations
                  </div>
                  <BreakdownBars
                    color="var(--chart-2)"
                    rows={[
                      { label: "Payables", value: lc.payables as string },
                      { label: "Overdraft drawn", value: lc.overdraft_drawn as string },
                      { label: "Overdue instalments", value: lc.overdue_instalments as string },
                      {
                        label: "Principal due ≤12m",
                        value: lc.loan_principal_due_12_months as string,
                      },
                    ]}
                  />
                </div>
              </div>
            ) : (
              <NotAvailable metric={liq} />
            )}
          </Panel>
          <Panel
            title="Cash runway"
            description="Months of available funds at the recent burn; gaps are months when the entity was not burning cash."
            className="lg:col-span-3"
          >
            <TimeSeriesChart
              data={hist("cash.runway")}
              unit="months"
              series={[{ key: "cash.runway", label: "Cash runway", color: "var(--chart-1)" }]}
              height={200}
            />
          </Panel>
        </div>
      </Section>
    </div>
  );
}

function Section({
  id,
  title,
  tiles,
  children,
}: {
  id: string;
  title: string;
  tiles: React.ReactNode[];
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="flex scroll-mt-6 flex-col gap-3">
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tiles.map((t, i) => (
          <Fragment key={i}>{t}</Fragment>
        ))}
      </div>
      {children}
    </section>
  );
}

function MetricTile({
  metric,
  entityId,
  asOf,
}: {
  metric?: Metric;
  entityId: string;
  asOf?: string;
}) {
  if (!metric) return null;
  const available = metric.availability === "available";
  return (
    <Link
      href={evidenceHref(entityId, `metric:${metric.code}`, { asOf })}
      title={metric.method}
      className="group flex min-w-0 flex-col gap-1 rounded-xl border bg-card px-4 py-3 shadow-xs transition hover:border-primary/40"
    >
      <span className="truncate text-xs font-medium text-muted-foreground">{metric.name}</span>
      <span className="text-xl leading-tight font-semibold">
        {available ? formatMetric(metric.value, metric.unit, { code: metric.code }) : "—"}
      </span>
      <span className="truncate text-[11px] text-muted-foreground">
        {available
          ? `${metric.period.label.replace(/_/g, " ")} · ${metric.confidence} confidence`
          : metric.availability === "not_applicable"
            ? "Not applicable"
            : "Insufficient data"}
      </span>
    </Link>
  );
}

function NotAvailable({ metric }: { metric?: Metric }) {
  return (
    <p className="text-sm text-muted-foreground">
      {metric?.availability === "not_applicable" ? "Not applicable" : "Not available"}
      {metric?.notes?.[0] ? `: ${metric.notes[0]}` : "."}
    </p>
  );
}
