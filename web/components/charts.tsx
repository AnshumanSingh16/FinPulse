"use client";

import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { day, inr, tick } from "@/lib/format";

const IN = "var(--color-in)";
const OUT = "var(--color-out)";
const GRID = "var(--color-grid)";
const AXIS = { fontSize: 12, fill: "var(--color-muted)" };

function TipBox({ title, rows }: { title: string; rows: { label: string; value: string; color?: string; dashed?: boolean }[] }) {
  return (
    <div className="rounded-xl border border-line bg-elevated px-3 py-2 text-sm shadow-lg">
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
        {cushion != null && <ReferenceLine y={cushion} stroke="var(--color-gold)" strokeDasharray="4 4" label={{ value: "1 month of costs", position: "insideBottomRight", fontSize: 11, fill: "var(--color-gold)" }} />}
        {today && <ReferenceLine x={today} stroke="var(--color-muted)" label={{ value: "Today", position: "insideTopLeft", fontSize: 11, fill: "var(--color-ink-2)" }} />}
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
          cursor={{ fill: "var(--color-surface-2)" }}
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
        <ReferenceLine y={cushion} stroke="var(--color-gold)" strokeDasharray="4 4" label={{ value: "1 month of costs", position: "insideBottomRight", fontSize: 11, fill: "var(--color-gold)" }} />
        <ReferenceLine y={0} stroke="var(--color-bad)" strokeOpacity={0.4} />
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
        <Line type="stepAfter" dataKey="without" name="If you don't buy" stroke="var(--color-muted)" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
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
        <ReferenceLine y={cushion} stroke="var(--color-gold)" strokeDasharray="4 4" label={{ value: "Your cushion", position: "insideBottomRight", fontSize: 11, fill: "var(--color-gold)" }} />
        <ReferenceLine y={0} stroke="var(--color-bad)" strokeOpacity={0.4} />
        <Tooltip content={({ active, payload, label }) => (active && payload?.length ? <TipBox title={day(String(label))} rows={[{ label: "Expected balance", value: inr(Number(payload[0].value)) }]} /> : null)} />
        <Area type="stepAfter" dataKey="balance" stroke={IN} strokeWidth={2} fill="url(#fcFill)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** White-on-gradient cash line for the home hero: actual (solid) then expected (dashed). */
export function HeroCashChart({ history, outlook, height = 150 }: { history: { date: string; balance: number }[]; outlook: { date: string; balance: number }[]; height?: number }) {
  const today = history[history.length - 1]?.date;
  const data = [
    ...history.map((h) => ({ date: h.date, actual: h.balance, ahead: h.date === today ? h.balance : null })),
    ...outlook.filter((o) => o.date !== today).map((o) => ({ date: o.date, actual: null, ahead: o.balance })),
  ];
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: 6 }}>
        <defs>
          <linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ffffff" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#ffffff" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="date" hide />
        <YAxis hide domain={["dataMin - 100000", "dataMax + 50000"]} />
        {today && <ReferenceLine x={today} stroke="rgba(255,255,255,0.5)" strokeDasharray="2 3" label={{ value: "Today", position: "insideTopRight", fontSize: 10, fill: "rgba(255,255,255,0.85)" }} />}
        <Tooltip
          cursor={{ stroke: "rgba(255,255,255,0.4)" }}
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0].payload as { actual: number | null; ahead: number | null };
            return <TipBox title={day(String(label))} rows={[{ label: p.actual != null ? "Balance" : "Expected", value: inr(p.actual ?? p.ahead) }]} />;
          }}
        />
        <Area type="monotone" dataKey="actual" stroke="#ffffff" strokeWidth={2.5} fill="url(#heroFill)" connectNulls={false} isAnimationActive />
        <Area type="monotone" dataKey="ahead" stroke="#ffffff" strokeOpacity={0.8} strokeWidth={2} strokeDasharray="5 5" fill="none" connectNulls={false} isAnimationActive />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function ScoreHistory({ data }: { data: { label: string; score: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={data} margin={{ top: 16, right: 4, bottom: 0, left: 4 }}>
        <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
        <YAxis hide domain={[0, 100]} />
        <Tooltip cursor={{ fill: "var(--color-surface-2)" }} content={({ active, payload, label }) => (active && payload?.length ? <TipBox title={String(label)} rows={[{ label: "Score", value: String(payload[0].value) }]} /> : null)} />
        <Bar dataKey="score" fill="var(--color-brand)" radius={[6, 6, 0, 0]} label={{ position: "top", fontSize: 11, fill: "var(--color-ink-2)" }} isAnimationActive />
      </BarChart>
    </ResponsiveContainer>
  );
}
