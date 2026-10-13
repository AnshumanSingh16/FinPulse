"use client";

import { useState } from "react";
import {
  Area,
  ComposedChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatINR } from "@/lib/format";
import type { RentVsBuyYear } from "@/lib/personal/finance/decisions";
import type { PlanYear } from "@/lib/personal/finance/plan";
import type { YearlyAmortization } from "@/lib/personal/finance/loan";
import type { ScenarioResult } from "@/lib/personal/finance/scenarios";
import { cn } from "@/lib/utils";

const axis = {
  stroke: "var(--chart-axis)",
  tickLine: false,
  tick: { fill: "var(--chart-ink-muted)", fontSize: 11 },
} as const;
const compact = (v: number) => formatINR(v, { compact: true });

type Series = { key: string; label: string; color: string };

function Legend({ series }: { series: Series[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {series.map((s) => (
        <span key={s.key} className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-sm" style={{ background: s.color }} />
          {s.label}
        </span>
      ))}
    </div>
  );
}

function TooltipBox({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; value: string; color?: string }[];
}) {
  return (
    <div
      className="min-w-44 rounded-lg border px-3 py-2 text-xs shadow-md"
      style={{ background: "var(--card)" }}
    >
      <div className="mb-1 font-medium text-muted-foreground">{title}</div>
      {rows.map((r) => (
        <div key={r.label} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            {r.color ? (
              <span className="inline-block size-2 rounded-sm" style={{ background: r.color }} />
            ) : null}
            {r.label}
          </span>
          <span className="tabular font-semibold text-foreground">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

function ChartFrame({
  legend,
  table,
  children,
  height,
}: {
  legend?: React.ReactNode;
  table: React.ReactNode;
  children: React.ReactElement;
  height: number;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        {legend ?? <span />}
        <div
          className="flex rounded-md border p-0.5 text-[11px]"
          role="group"
          aria-label="Chart or table"
        >
          {(["chart", "table"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              aria-pressed={view === v}
              className={cn(
                "rounded px-2 py-0.5 capitalize",
                view === v ? "bg-muted font-medium" : "text-muted-foreground",
              )}
            >
              {v}
            </button>
          ))}
        </div>
      </div>
      {view === "chart" ? (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            {children}
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="max-h-72 overflow-auto rounded-lg border">{table}</div>
      )}
    </div>
  );
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="tabular w-full text-xs">
      <thead className="sticky top-0 bg-muted text-muted-foreground">
        <tr>
          {head.map((h, i) => (
            <th key={h} className={cn("px-3 py-1.5 font-medium", i ? "text-right" : "text-left")}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-t">
            {r.map((c, j) => (
              <td key={j} className={cn("px-3 py-1.5", j ? "text-right" : "text-left")}>
                {c}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Yearly principal vs interest: how the EMI splits over the loan's life. */
export function AmortizationChart({ yearly }: { yearly: YearlyAmortization[] }) {
  const series: Series[] = [
    { key: "principalPaid", label: "Principal repaid", color: "var(--chart-1)" },
    { key: "interestPaid", label: "Interest paid", color: "var(--chart-2)" },
  ];
  return (
    <ChartFrame
      height={240}
      legend={<Legend series={series} />}
      table={
        <Table
          head={["Year", "Principal", "Interest", "Balance at year end"]}
          rows={yearly.map((y) => [
            y.year,
            formatINR(y.principalPaid),
            formatINR(y.interestPaid),
            formatINR(y.closingBalance),
          ])}
        />
      }
    >
      <BarChart data={yearly} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={2}>
        <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
        <XAxis
          dataKey="year"
          {...axis}
          tickFormatter={(v) => `Y${v}`}
          interval="preserveStartEnd"
        />
        <YAxis {...axis} width={56} tickFormatter={compact} axisLine={false} />
        <Tooltip
          cursor={{ fill: "var(--muted)", opacity: 0.4 }}
          content={({ active, payload, label }) =>
            active && payload?.length ? (
              <TooltipBox
                title={`Year ${label}`}
                rows={series.map((s) => ({
                  label: s.label,
                  value: formatINR(Number(payload.find((p) => p.dataKey === s.key)?.value ?? 0)),
                  color: s.color,
                }))}
              />
            ) : null
          }
        />
        <Bar
          dataKey="principalPaid"
          stackId="a"
          fill="var(--chart-1)"
          stroke="var(--chart-surface)"
          strokeWidth={1}
        />
        <Bar
          dataKey="interestPaid"
          stackId="a"
          fill="var(--chart-2)"
          stroke="var(--chart-surface)"
          strokeWidth={1}
          radius={[4, 4, 0, 0]}
        />
      </BarChart>
    </ChartFrame>
  );
}

/** Monthly surplus (or deficit) in each scenario: one measure, one axis. */
export function ScenarioSurplusChart({ results }: { results: ScenarioResult[] }) {
  const data = results.map((r) => ({
    name: r.params.name,
    value: r.monthlySurplus,
    label: r.label,
  }));
  return (
    <ChartFrame
      height={Math.max(180, data.length * 38)}
      table={
        <Table
          head={["Scenario", "Monthly surplus", "Savings after 12 months"]}
          rows={results.map((r) => [
            r.params.name,
            formatINR(r.monthlySurplus),
            formatINR(r.savingsAfterHorizon),
          ])}
        />
      }
    >
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
        <XAxis type="number" {...axis} tickFormatter={compact} />
        <YAxis
          type="category"
          dataKey="name"
          {...axis}
          width={150}
          axisLine={false}
          tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
        />
        <ReferenceLine x={0} stroke="var(--chart-axis)" />
        <Tooltip
          cursor={{ fill: "var(--muted)", opacity: 0.4 }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <TooltipBox
                title={String(payload[0]!.payload.name)}
                rows={[{ label: "Monthly surplus", value: formatINR(Number(payload[0]!.value)) }]}
              />
            ) : null
          }
        />
        <Bar dataKey="value" radius={4} barSize={18}>
          {data.map((d) => (
            <Cell key={d.name} fill={d.value < 0 ? "var(--chart-negative)" : "var(--chart-1)"} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

/** Liquid savings month by month: baseline vs one chosen scenario. */
export function SavingsTrajectoryChart({
  baseline,
  scenario,
}: {
  baseline: ScenarioResult;
  scenario: ScenarioResult;
}) {
  const data = baseline.trajectory.map((p, i) => ({
    month: p.month,
    baseline: p.savings,
    scenario: scenario.trajectory[i]?.savings ?? null,
  }));
  const series: Series[] = [
    { key: "baseline", label: "Baseline", color: "var(--chart-1)" },
    { key: "scenario", label: scenario.params.name, color: "var(--chart-2)" },
  ];
  return (
    <ChartFrame
      height={240}
      legend={<Legend series={series} />}
      table={
        <Table
          head={["Month", "Baseline", scenario.params.name]}
          rows={data.map((d) => [d.month, formatINR(d.baseline), formatINR(d.scenario)])}
        />
      }
    >
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
        <XAxis dataKey="month" {...axis} tickFormatter={(v) => (v === 0 ? "Now" : `M${v}`)} />
        <YAxis {...axis} width={56} tickFormatter={compact} axisLine={false} />
        <ReferenceLine y={0} stroke="var(--chart-negative)" strokeDasharray="4 3" />
        <Tooltip
          cursor={{ stroke: "var(--chart-axis)" }}
          content={({ active, payload, label }) =>
            active && payload?.length ? (
              <TooltipBox
                title={Number(label) === 0 ? "Right after purchase" : `Month ${label}`}
                rows={series.map((s) => ({
                  label: s.label,
                  value: formatINR(Number(payload.find((p) => p.dataKey === s.key)?.value ?? 0)),
                  color: s.color,
                }))}
              />
            ) : null
          }
        />
        <Line
          type="monotone"
          dataKey="baseline"
          stroke="var(--chart-1)"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, stroke: "var(--chart-surface)", strokeWidth: 2 }}
        />
        <Line
          type="monotone"
          dataKey="scenario"
          stroke="var(--chart-2)"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, stroke: "var(--chart-surface)", strokeWidth: 2 }}
        />
      </LineChart>
    </ChartFrame>
  );
}

/** Where take-home pay goes after the purchase. Magnitude bars in one hue (not a categorical chart). */
export function IncomeAllocation({
  rows,
  income,
}: {
  rows: { label: string; value: number }[];
  income: number;
}) {
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((r) => {
        const share = income > 0 ? Math.max(0, r.value) / income : 0;
        return (
          <li key={r.label} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span className="text-muted-foreground">{r.label}</span>
              <span className={cn("tabular font-medium", r.value < 0 && "text-text-critical")}>
                {formatINR(r.value)}{" "}
                <span className="text-muted-foreground">
                  · {income > 0 ? `${Math.round((r.value / income) * 100)}%` : "—"}
                </span>
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full",
                  r.value < 0 ? "bg-chart-negative" : "bg-chart-1",
                )}
                style={{ width: `${Math.min(100, share * 100)}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** The goal plan year by year: money set aside vs loans owed, with the goals bought each year. */
export function PlanTimelineChart({ years }: { years: PlanYear[] }) {
  const data = years.map((y) => ({
    year: y.month.slice(0, 4),
    saved: y.reserve + y.freeSavings + y.goalFunds,
    loans: y.loanOutstanding,
    bought: y.goalsBought,
  }));
  const series: Series[] = [
    { key: "saved", label: "Savings set aside", color: "var(--chart-1)" },
    { key: "loans", label: "Loans for goals", color: "var(--chart-2)" },
  ];
  const marks = data.filter((d) => d.bought.length);
  return (
    <ChartFrame
      height={260}
      legend={<Legend series={series} />}
      table={
        <Table
          head={["End of", "Savings set aside", "Loans for goals", "Goals reached"]}
          rows={data.map((d) => [
            d.year,
            formatINR(d.saved),
            formatINR(d.loans),
            d.bought.join(", ") || "—",
          ])}
        />
      }
    >
      <LineChart data={data} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
        <XAxis dataKey="year" {...axis} minTickGap={16} />
        <YAxis {...axis} width={56} tickFormatter={compact} axisLine={false} />
        <ReferenceLine y={0} stroke="var(--chart-axis)" />
        {marks.map((m) => (
          <ReferenceLine
            key={m.year}
            x={m.year}
            stroke="var(--chart-ink-muted)"
            strokeDasharray="3 3"
            label={{
              value: "●",
              position: "top",
              fill: "var(--chart-ink-muted)",
              fontSize: 10,
            }}
          />
        ))}
        <Tooltip
          cursor={{ stroke: "var(--chart-axis)" }}
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const row = data.find((d) => d.year === label);
            return (
              <TooltipBox
                title={`End of ${label}${row?.bought.length ? ` · reached: ${row.bought.join(", ")}` : ""}`}
                rows={series.map((s) => ({
                  label: s.label,
                  value: formatINR(Number(payload.find((p) => p.dataKey === s.key)?.value ?? 0)),
                  color: s.color,
                }))}
              />
            );
          }}
        />
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            stroke={s.color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: "var(--chart-surface)", strokeWidth: 2 }}
          />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

/** Rent vs buy: what each path is worth at the end of every year. */
export function RentBuyChart({ years }: { years: RentVsBuyYear[] }) {
  const series: Series[] = [
    { key: "buyerWealth", label: "Buy: home equity + investments", color: "var(--chart-1)" },
    { key: "renterWealth", label: "Rent: investments", color: "var(--chart-2)" },
  ];
  return (
    <ChartFrame
      height={260}
      legend={<Legend series={series} />}
      table={
        <Table
          head={["Year", "Buy", "Rent", "Home value", "Loan left", "Rent / month"]}
          rows={years.map((y) => [
            y.year,
            formatINR(y.buyerWealth),
            formatINR(y.renterWealth),
            formatINR(y.homeValue),
            formatINR(y.loanBalance),
            formatINR(y.rent),
          ])}
        />
      }
    >
      <LineChart data={years} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
        <XAxis dataKey="year" {...axis} tickFormatter={(v) => `Y${v}`} />
        <YAxis {...axis} width={56} tickFormatter={compact} axisLine={false} />
        <Tooltip
          cursor={{ stroke: "var(--chart-axis)" }}
          content={({ active, payload, label }) =>
            active && payload?.length ? (
              <TooltipBox
                title={`After ${label} year(s)`}
                rows={series.map((s) => ({
                  label: s.label,
                  value: formatINR(Number(payload.find((p) => p.dataKey === s.key)?.value ?? 0)),
                  color: s.color,
                }))}
              />
            ) : null
          }
        />
        {series.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            stroke={s.color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: "var(--chart-surface)", strokeWidth: 2 }}
          />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

/** The range of outcomes across simulated futures: the middle 80% as a band, the median as a line. */
export function FanChart({
  fan,
}: {
  fan: { month: string; p10: number; p50: number; p90: number }[];
}) {
  const data = fan.map((f) => ({
    year: f.month.slice(0, 4),
    band: [f.p10, f.p90],
    p50: f.p50,
    p10: f.p10,
    p90: f.p90,
  }));
  const series: Series[] = [
    { key: "p50", label: "Typical future (median)", color: "var(--chart-1)" },
    {
      key: "band",
      label: "Middle 80% of futures",
      color: "color-mix(in oklab, var(--chart-1) 22%, transparent)",
    },
  ];
  return (
    <ChartFrame
      height={260}
      legend={<Legend series={series} />}
      table={
        <Table
          head={["End of", "Bad (10th pct)", "Typical", "Good (90th pct)"]}
          rows={data.map((d) => [d.year, formatINR(d.p10), formatINR(d.p50), formatINR(d.p90)])}
        />
      }
    >
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
        <XAxis dataKey="year" {...axis} minTickGap={16} />
        <YAxis {...axis} width={56} tickFormatter={compact} axisLine={false} />
        <ReferenceLine y={0} stroke="var(--chart-axis)" />
        <Tooltip
          cursor={{ stroke: "var(--chart-axis)" }}
          content={({ active, label }) => {
            const row = data.find((d) => d.year === label);
            return active && row ? (
              <TooltipBox
                title={`End of ${label}: savings set aside`}
                rows={[
                  { label: "Good future (90th pct)", value: formatINR(row.p90) },
                  { label: "Typical", value: formatINR(row.p50), color: "var(--chart-1)" },
                  { label: "Bad future (10th pct)", value: formatINR(row.p10) },
                ]}
              />
            ) : null;
          }}
        />
        <Area
          type="monotone"
          dataKey="band"
          stroke="none"
          fill="var(--chart-1)"
          fillOpacity={0.18}
          isAnimationActive={false}
          activeDot={false}
        />
        <Line
          type="monotone"
          dataKey="p50"
          stroke="var(--chart-1)"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
          activeDot={{ r: 4, stroke: "var(--chart-surface)", strokeWidth: 2 }}
        />
      </ComposedChart>
    </ChartFrame>
  );
}
