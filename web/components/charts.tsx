"use client";

import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { day, inr, tick } from "@/lib/format";

const IN = "#2a78d6";
const OUT = "#eb6834";
const GRID = "#eceee9";
const AXIS = { fontSize: 12, fill: "#87938c" };

function TipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string; dashed?: boolean }[] }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2 text-sm shadow-lg">
      <p className="mb-1 font-medium">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-center gap-2 text-ink-2">
          {r.color && <span className="inline-block h-0.5 w-3" style={{ background: r.color, opacity: r.dashed ? 0.6 : 1 }} />}
          {r.label}: <span className="num font-medium text-ink">{r.value}</span>
        </p>
      ))}
    </div>
  );
}

/** Bank balance: the last 90 days (solid) joined to the next 90 (dashed projection). */
export function CashChart({ history, outlook, cushion, height = 180 }: { history: { date: string; balance: number }[]; outlook: { date: string; balance: number }[]; cushion?: number; height?: number }) {
  const today = history[history.length - 1]?.date;
  const data = [
    ...history.map((h) => ({ date: h.date, actual: h.balance, ahead: h.date === today ? h.balance : null })),
    ...outlook.filter((o) => o.date !== today).map((o) => ({ date: o.date, actual: null, ahead: o.balance })),
  ];
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="cashFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={IN} stopOpacity={0.18} />
            <stop offset="100%" stopColor={IN} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="date" tickFormatter={day} tick={AXIS} axisLine={false} tickLine={false} minTickGap={40} />
        <YAxis tickFormatter={tick} tick={AXIS} axisLine={false} tickLine={false} width={52} />
        {cushion != null && <ReferenceLine y={cushion} stroke="#9a5b05" strokeDasharray="4 4" label={{ value: "1 month of costs", position: "insideBottomRight", fontSize: 11, fill: "#9a5b05" }} />}
        {today && <ReferenceLine x={today} stroke="#87938c" label={{ value: "Today", position: "insideTopLeft", fontSize: 11, fill: "#4b5a52" }} />}
        <Tooltip
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as { actual: number | null; ahead: number | null };
            const v = p.actual ?? p.ahead;
            return <TipBox title={day(String(label))} rows={[{ label: p.actual != null ? "Balance" : "Expected", value: inr(v) }]} />;
          }}
        />
        <Area type="stepAfter" dataKey="actual" stroke={IN} strokeWidth={2} fill="url(#cashFill)" connectNulls={false} isAnimationActive={false} />
        <Area type="stepAfter" dataKey="ahead" stroke={IN} strokeWidth={2} strokeDasharray="5 4" fill="none" connectNulls={false} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function SalesCostsChart({ data }: { data: { month: string; sales: number; costs: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} barGap={2} barCategoryGap="28%" margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="month" tick={AXIS} axisLine={false} tickLine={false} />
        <YAxis tickFormatter={tick} tick={AXIS} axisLine={false} tickLine={false} width={52} />
        <Tooltip
          cursor={{ fill: "#f2f3f0" }}
          content={({ active, payload, label }) =>
            active && payload?.length ? (
              <TipBox
                title={String(label)}
                rows={[
                  { label: "Sales", value: inr(payload[0].payload.sales), color: IN },
                  { label: "Running costs", value: inr(payload[0].payload.costs), color: OUT },
                ]}
              />
            ) : null
          }
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 13, paddingTop: 6 }} formatter={(v) => <span className="text-ink-2">{v}</span>} />
        <Bar dataKey="sales" name="Sales" fill={IN} radius={[4, 4, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="costs" name="Running costs" fill={OUT} radius={[4, 4, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Balance with vs without a purchase, for one scenario. */
export function PurchaseChart({ series, cushion }: { series: { date: string; with: number; without: number }[]; cushion: number }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={series} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="date" tickFormatter={day} tick={AXIS} axisLine={false} tickLine={false} minTickGap={40} />
        <YAxis tickFormatter={tick} tick={AXIS} axisLine={false} tickLine={false} width={52} />
        <ReferenceLine y={cushion} stroke="#9a5b05" strokeDasharray="4 4" label={{ value: "1 month of costs", position: "insideBottomRight", fontSize: 11, fill: "#9a5b05" }} />
        <ReferenceLine y={0} stroke="#b42318" strokeOpacity={0.4} />
        <Tooltip
          content={({ active, payload, label }) =>
            active && payload?.length ? (
              <TipBox
                title={day(String(label))}
                rows={[
                  { label: "If you buy", value: inr(payload[0].payload.with), color: IN },
                  { label: "If you don't", value: inr(payload[0].payload.without), color: "#87938c", dashed: true },
                ]}
              />
            ) : null
          }
        />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 13, paddingTop: 6 }} formatter={(v) => <span className="text-ink-2">{v}</span>} />
        <Line type="stepAfter" dataKey="without" name="If you don't buy" stroke="#87938c" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
        <Line type="stepAfter" dataKey="with" name="If you buy" stroke={IN} strokeWidth={2.5} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ForecastChart({ series, cushion }: { series: { date: string; balance: number }[]; cushion: number }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={series} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="fcFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={IN} stopOpacity={0.16} />
            <stop offset="100%" stopColor={IN} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="date" tickFormatter={day} tick={AXIS} axisLine={false} tickLine={false} minTickGap={40} />
        <YAxis tickFormatter={tick} tick={AXIS} axisLine={false} tickLine={false} width={52} />
        <ReferenceLine y={cushion} stroke="#9a5b05" strokeDasharray="4 4" label={{ value: "Your cushion", position: "insideBottomRight", fontSize: 11, fill: "#9a5b05" }} />
        <ReferenceLine y={0} stroke="#b42318" strokeOpacity={0.4} />
        <Tooltip content={({ active, payload, label }) => (active && payload?.length ? <TipBox title={day(String(label))} rows={[{ label: "Expected balance", value: inr(Number(payload[0].value)) }]} /> : null)} />
        <Area type="stepAfter" dataKey="balance" stroke={IN} strokeWidth={2} fill="url(#fcFill)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
