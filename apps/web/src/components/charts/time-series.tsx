"use client";

import { useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatAxis, formatINR, formatMetric, formatMonth, formatMonthShort } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Point = { date: string } & Record<string, number | null | string>;
export type Series = { key: string; label: string; color: string; area?: boolean };
export type Reference = { y: number; label: string };

type Common = {
  data: Point[];
  unit: string;
  code?: string;
  height?: number;
  /** Shown above the chart as the table/chart toggle's partner. */
  title?: string;
};

function valueText(v: unknown, unit: string, code?: string): string {
  return typeof v === "number" ? formatMetric(v, unit, { code }) : "—";
}

/** Tooltip: values lead, series names follow, keyed by a short line in the series colour. */
function ChartTooltip({
  active,
  payload,
  label,
  series,
  unit,
  code,
}: {
  active?: boolean;
  payload?: readonly { dataKey?: unknown; value?: unknown }[];
  label?: unknown;
  series: Series[];
  unit: string;
  code?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="bg-popover min-w-40 rounded-lg border px-3 py-2 text-xs shadow-md"
      style={{ background: "var(--card)" }}
    >
      <div className="mb-1 font-medium text-muted-foreground">{formatMonth(String(label))}</div>
      {series.map((s) => {
        const item = payload.find((p) => p.dataKey === s.key);
        return (
          <div key={s.key} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-muted-foreground">
              <span className="inline-block h-0.5 w-3 rounded" style={{ background: s.color }} />
              {s.label}
            </span>
            <span className="tabular font-semibold text-foreground">
              {valueText(item?.value, unit, code)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {series.map((s) => (
        <span key={s.key} className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} />
          {s.label}
        </span>
      ))}
    </div>
  );
}

function DataTable({
  data,
  series,
  unit,
  code,
}: {
  data: Point[];
  series: Series[];
  unit: string;
  code?: string;
}) {
  return (
    <div className="max-h-72 overflow-auto rounded-lg border">
      <table className="tabular w-full text-xs">
        <thead className="sticky top-0 bg-muted text-muted-foreground">
          <tr>
            <th className="px-3 py-1.5 text-left font-medium">Month</th>
            {series.map((s) => (
              <th key={s.key} className="px-3 py-1.5 text-right font-medium">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((p) => (
            <tr key={p.date} className="border-t">
              <td className="px-3 py-1.5">{formatMonth(p.date)}</td>
              {series.map((s) => (
                <td key={s.key} className="px-3 py-1.5 text-right">
                  {valueText(p[s.key], unit, code)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Frame({
  series,
  table,
  children,
  legend = true,
}: {
  series: Series[];
  table: React.ReactNode;
  children: React.ReactNode;
  legend?: boolean;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        {legend ? <Legend series={series} /> : <span />}
        <div className="flex rounded-md border p-0.5 text-[11px]" role="group" aria-label="View">
          {(["chart", "table"] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setView(v)}
              aria-pressed={view === v}
              className={cn(
                "rounded px-2 py-0.5 capitalize",
                view === v ? "bg-muted font-medium text-foreground" : "text-muted-foreground",
              )}
            >
              {v}
            </button>
          ))}
        </div>
      </div>
      {view === "chart" ? children : table}
    </div>
  );
}

const AXIS = { stroke: "var(--chart-axis)", tickLine: false, axisLine: false } as const;

/** Monthly line/area chart, one y-axis, crosshair tooltip, end-point label on the lead series. */
export function TimeSeriesChart({
  data,
  series,
  unit,
  code,
  height = 220,
  references = [],
  zeroLine = false,
  domain,
}: Common & {
  series: Series[];
  references?: Reference[];
  zeroLine?: boolean;
  domain?: [number, number];
}) {
  const lead = series[0]?.key ?? "";
  // Direct label on the lead series' last point only (selective labelling).
  let lastIndex = -1;
  data.forEach((p, i) => {
    if (typeof p[lead] === "number") lastIndex = i;
  });
  const endLabel = (props: unknown) => {
    const { x, y, index, value } = props as {
      x?: number;
      y?: number;
      index?: number;
      value?: unknown;
    };
    if (index !== lastIndex || typeof value !== "number" || x === undefined || y === undefined)
      return <g />;
    const text =
      unit === "INR" ? formatINR(value, { compact: true }) : valueText(value, unit, code);
    return (
      <text x={x + 8} y={y} dy={4} fontSize={11} fontWeight={600} fill="var(--foreground)">
        {text}
      </text>
    );
  };
  return (
    <Frame
      series={series}
      table={<DataTable data={data} series={series} unit={unit} code={code} />}
    >
      <div style={{ height }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 64, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />
            <XAxis dataKey="date" tickFormatter={formatMonthShort} minTickGap={24} {...AXIS} />
            <YAxis
              width={56}
              tickFormatter={(v: number) => formatAxis(v, unit, code)}
              {...AXIS}
              domain={domain ?? ["auto", "auto"]}
            />
            {zeroLine ? <ReferenceLine y={0} stroke="var(--chart-axis)" /> : null}
            {references.map((r) => (
              <ReferenceLine
                key={r.label}
                y={r.y}
                stroke="var(--chart-axis)"
                label={{
                  value: r.label,
                  position: "insideTopRight",
                  fill: "var(--chart-ink-muted)",
                  fontSize: 11,
                }}
              />
            ))}
            <Tooltip
              cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1 }}
              content={(p) => (
                <ChartTooltip
                  active={p.active}
                  payload={p.payload}
                  label={p.label}
                  series={series}
                  unit={unit}
                  code={code}
                />
              )}
            />
            {series.map((s) =>
              s.area ? (
                <Area
                  key={s.key}
                  dataKey={s.key}
                  name={s.label}
                  type="linear"
                  stroke={s.color}
                  strokeWidth={2}
                  fill={s.color}
                  fillOpacity={0.1}
                  connectNulls={false}
                  dot={false}
                  label={s.key === lead ? endLabel : undefined}
                  activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              ) : (
                <Line
                  key={s.key}
                  dataKey={s.key}
                  name={s.label}
                  type="linear"
                  stroke={s.color}
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                  label={s.key === lead ? endLabel : undefined}
                  activeDot={{ r: 4, stroke: "var(--card)", strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              ),
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Frame>
  );
}

/** Monthly columns diverging around zero (e.g. net cash flow): blue in, red out. */
export function DivergingBars({
  data,
  dataKey,
  label,
  unit,
  height = 220,
}: Common & { dataKey: string; label: string }) {
  const series: Series[] = [{ key: dataKey, label, color: "var(--chart-1)" }];
  return (
    <Frame
      series={series}
      legend={false}
      table={<DataTable data={data} series={series} unit={unit} />}
    >
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-sm bg-chart-1" /> Net inflow
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-sm bg-chart-negative" /> Net outflow
        </span>
      </div>
      <div style={{ height }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ top: 12, right: 12, bottom: 0, left: 0 }}
            barCategoryGap={4}
          >
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="date" tickFormatter={formatMonthShort} minTickGap={24} {...AXIS} />
            <YAxis width={56} tickFormatter={(v: number) => formatAxis(v, unit)} {...AXIS} />
            <ReferenceLine y={0} stroke="var(--chart-axis)" />
            <Tooltip
              cursor={{ fill: "var(--muted)", opacity: 0.5 }}
              content={(p) => (
                <ChartTooltip
                  active={p.active}
                  payload={p.payload}
                  label={p.label}
                  series={series}
                  unit={unit}
                />
              )}
            />
            <Bar dataKey={dataKey} maxBarSize={24} shape={RoundedEndBar} isAnimationActive={false}>
              {data.map((p) => (
                <Cell
                  key={p.date}
                  fill={Number(p[dataKey]) < 0 ? "var(--chart-negative)" : "var(--chart-1)"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Frame>
  );
}

/** 4px rounded data-end, square at the baseline — for bars on either side of zero. */
function RoundedEndBar(props: unknown) {
  const { x, y, width, height, fill } = props as {
    x: number;
    y: number;
    width: number;
    height: number;
    fill: string;
  };
  if (!width || !height) return <g />;
  const h = Math.abs(height);
  const top = height < 0 ? y + height : y;
  const r = Math.min(4, width / 2, h);
  const negative = height < 0 || (props as { value?: number }).value! < 0;
  const d = negative
    ? `M${x},${top} h${width} v${h - r} a${r},${r} 0 0 1 -${r},${r} h-${width - 2 * r} a${r},${r} 0 0 1 -${r},-${r} z`
    : `M${x},${top + h} v-${h - r} a${r},${r} 0 0 1 ${r},-${r} h${width - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} z`;
  return <path d={d} fill={fill} />;
}

export { Legend as ChartLegend };
