"use client";

import { AlertTriangle, ChevronDown } from "lucide-react";
import { useContext, useEffect, useState } from "react";
import { Area, Bar, CartesianGrid, Cell, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { DataVersion } from "@/components/data-version";
import { Card, cx, Loading } from "@/components/ui";
import { get } from "@/lib/api";
import { inr, short, tick } from "@/lib/format";
import { useT } from "@/lib/i18n";

interface Period {
  period: string;
  label: string;
  start: string;
  end: string;
  kind: "actual" | "forecast" | "mixed";
  partial: boolean;
  covers: [string, string];
  money_in: number;
  money_out: number;
  opening: number;
  closing: number;
  lowest: number;
  lowest_date: string;
  items: { date: string; label: string; amount: number; source: string; kind: string }[];
}
interface Data {
  status: string;
  message?: string;
  by: "month" | "quarter";
  as_of: string;
  today: number;
  safety: number;
  approved: boolean;
  daily: { date: string; balance: number; kind: "actual" | "forecast" }[];
  periods: Period[];
  method: string;
}

const fmtDay = (iso: string, lang: string) => new Date(iso + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short" });
const fmtMonth = (iso: string, lang: string) => new Date(iso + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { month: "short", year: "2-digit" });

function periodName(p: Period, by: string, lang: string) {
  if (by === "quarter") return p.label;
  return new Date(p.start + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { month: "short", year: "numeric" });
}

/** Cash by month or quarter: the past from your records, then the forecast — as a balance line and money in/out bars. */
export function PeriodView({ by }: { by: "month" | "quarter" }) {
  const { t, lang } = useT();
  const { version } = useContext(DataVersion);
  const [data, setData] = useState<Data | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    setData(null);
    get<Data>(`/api/timeline?by=${by}`).then(setData).catch(() => setData({ status: "error", message: t("Couldn't load the timeline.") } as Data));
  }, [by, version, t]);
  if (!data) return <Loading />;
  if (data.status !== "ok") return <Card className="text-ink-2">{data.message}</Card>;

  const name = (p: Period) => periodName(p, by, lang);
  const firstForecast = data.periods.find((p) => p.kind !== "actual");
  const bars = data.periods.map((p) => ({ name: name(p), in: p.money_in, out: -p.money_out, closing: p.closing, lowest: p.lowest, kind: p.kind, p }));
  const line = data.daily.map((x) => ({ date: x.date, actual: x.kind === "actual" ? x.balance : null, forecast: x.kind === "forecast" || x.date === data.as_of ? x.balance : null }));
  const lastDate = data.daily[data.daily.length - 1]?.date;
  const future = data.periods.filter((p) => p.kind !== "actual");
  const worst = future.reduce<Period | null>((w, p) => (!w || p.lowest < w.lowest ? p : w), null);

  return (
    <div className="space-y-5">
      {/* headline numbers */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label={t("In the bank today")} value={short(data.today)} />
        {future.length > 0 && <Stat label={t("Expected on {d}", { d: fmtDay(future[future.length - 1].covers[1], lang) })} value={short(future[future.length - 1].closing)}
          tone={future[future.length - 1].closing < 0 ? "bad" : future[future.length - 1].closing < data.safety ? "caution" : "good"} />}
        {worst && <Stat label={t("Lowest point ahead")} value={short(worst.lowest)} sub={fmtDay(worst.lowest_date, lang)} tone={worst.lowest < 0 ? "bad" : worst.lowest < data.safety ? "caution" : "good"} />}
      </div>

      {/* bank balance, day by day */}
      <Card>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="serif text-lg font-semibold">{t("Bank balance")}</h2>
          <p className="text-xs text-muted">{data.approved ? t("Forecast includes the moves you approved.") : t("Forecast if nothing changes.")}</p>
        </div>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={line} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="bal" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-brand)" stopOpacity={0.22} />
                  <stop offset="100%" stopColor="var(--color-brand)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--color-grid)" />
              <XAxis dataKey="date" tickFormatter={(d) => fmtMonth(String(d), lang)} tick={{ fontSize: 11, fill: "var(--color-muted)" }} minTickGap={40} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={tick} tick={{ fontSize: 11, fill: "var(--color-muted)" }} width={58} tickLine={false} axisLine={false} />
              {lastDate && <ReferenceArea x1={data.as_of} x2={lastDate} fill="var(--color-brand)" fillOpacity={0.05} />}
              <ReferenceLine x={data.as_of} stroke="var(--color-ink)" strokeOpacity={0.4} label={{ value: t("Today"), position: "insideTopLeft", fontSize: 11, fill: "var(--color-ink-2)" }} />
              <ReferenceLine y={data.safety} stroke="var(--color-caution)" strokeDasharray="5 4" label={{ value: t("Your cushion"), position: "insideBottomRight", fontSize: 11, fill: "var(--color-caution)" }} />
              <ReferenceLine y={0} stroke="var(--color-bad)" strokeOpacity={0.5} />
              <Tooltip content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null;
                const v = payload.find((x) => x.value != null);
                return v ? (
                  <div className="rounded-xl border border-line bg-elevated px-3 py-2 text-sm shadow-lg">
                    <p className="font-medium">{fmtDay(String(label), lang)} · {v.dataKey === "actual" ? t("actual") : t("forecast")}</p>
                    <p className="num text-ink">{inr(Number(v.value))}</p>
                  </div>
                ) : null;
              }} />
              <Area type="monotone" dataKey="actual" stroke="var(--color-ink-2)" strokeWidth={1.8} fill="url(#bal)" dot={false} isAnimationActive={false} connectNulls={false} />
              <Line type="monotone" dataKey="forecast" stroke="var(--color-brand)" strokeWidth={2.4} strokeDasharray="6 4" dot={false} isAnimationActive={false} connectNulls={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
          <span className="inline-flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 bg-ink-2" /> {t("What happened (from your records)")}</span>
          <span className="inline-flex items-center gap-1.5"><span className="inline-block w-4 border-t-2 border-dashed border-brand" /> {t("Forecast")}</span>
          <span className="inline-flex items-center gap-1.5"><span className="inline-block w-4 border-t-2 border-dashed border-caution" /> {t("Your cushion")}</span>
        </div>
      </Card>

      {/* money in and out per period, with the closing balance */}
      <Card>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="serif text-lg font-semibold">{by === "quarter" ? t("Money in and out, by quarter") : t("Money in and out, by month")}</h2>
          <p className="text-xs text-muted">{t("Faded bars are forecast.")}</p>
        </div>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={bars} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} stackOffset="sign">
              <CartesianGrid vertical={false} stroke="var(--color-grid)" />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--color-muted)" }} tickLine={false} axisLine={false} interval={0} angle={by === "month" ? -35 : 0} textAnchor={by === "month" ? "end" : "middle"} height={by === "month" ? 48 : 24} />
              <YAxis tickFormatter={tick} tick={{ fontSize: 11, fill: "var(--color-muted)" }} width={58} tickLine={false} axisLine={false} />
              {firstForecast && <ReferenceLine x={name(firstForecast)} stroke="var(--color-ink)" strokeOpacity={0.25} strokeDasharray="3 3" />}
              <ReferenceLine y={0} stroke="var(--color-line)" />
              <ReferenceLine y={data.safety} stroke="var(--color-caution)" strokeDasharray="5 4" />
              <Tooltip content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const p = (payload[0].payload as { p: Period }).p;
                return (
                  <div className="rounded-xl border border-line bg-elevated px-3 py-2 text-sm shadow-lg">
                    <p className="font-medium">{name(p)} · {p.kind === "actual" ? t("actual") : p.kind === "forecast" ? t("forecast") : t("actual + forecast")}</p>
                    <p className="text-ink-2">{t("Money in")}: <span className="num text-good">{inr(p.money_in)}</span></p>
                    <p className="text-ink-2">{t("Money out")}: <span className="num text-ink">{inr(p.money_out)}</span></p>
                    <p className="text-ink-2">{t("Closing balance")}: <span className="num font-semibold text-ink">{inr(p.closing)}</span></p>
                    <p className="text-ink-2">{t("Lowest")}: <span className={cx("num", p.lowest < data.safety && "text-caution", p.lowest < 0 && "text-bad")}>{inr(p.lowest)}</span> · {fmtDay(p.lowest_date, lang)}</p>
                  </div>
                );
              }} />
              <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => (v === "in" ? t("Money in") : v === "out" ? t("Money out") : t("Closing balance"))} />
              <Bar dataKey="in" stackId="a" fill="var(--color-in)" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                {bars.map((b) => <Cell key={b.name} fillOpacity={b.kind === "actual" ? 0.9 : 0.4} />)}
              </Bar>
              <Bar dataKey="out" stackId="a" fill="var(--color-out)" radius={[0, 0, 4, 4]} isAnimationActive={false}>
                {bars.map((b) => <Cell key={b.name} fillOpacity={b.kind === "actual" ? 0.9 : 0.4} />)}
              </Bar>
              <Line type="monotone" dataKey="closing" stroke="var(--color-brand)" strokeWidth={2.4} dot={{ r: 3.5, fill: "var(--color-brand)" }} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* the periods, newest forecast first after the past */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {[...data.periods].reverse().map((p) => {
          const low = p.lowest < data.safety;
          const neg = p.lowest < 0;
          const isOpen = open === p.period;
          const net = p.money_in - p.money_out;
          return (
            <div key={p.period} className={cx("card overflow-hidden", neg ? "ring-2 ring-bad/40" : low && p.kind !== "actual" && "ring-2 ring-caution/40")}>
              <button onClick={() => setOpen(isOpen ? null : p.period)} className="w-full p-4 text-left" aria-expanded={isOpen}>
                <div className="flex items-center justify-between gap-2">
                  <p className="serif text-lg font-semibold">{name(p)}</p>
                  <span className={cx("rounded-full px-2 py-0.5 text-[0.65rem] font-semibold tracking-wide uppercase",
                    p.kind === "actual" ? "bg-surface-2 text-ink-2" : "bg-brand-50 text-brand")}>
                    {p.kind === "actual" ? t("Actual") : p.kind === "forecast" ? t("Forecast") : t("Actual + forecast")}
                  </span>
                </div>
                {p.partial && <p className="text-xs text-muted">{fmtDay(p.covers[0], lang)} – {fmtDay(p.covers[1], lang)}</p>}
                <div className="mt-2 grid grid-cols-3 gap-2 text-sm">
                  <div><p className="text-[0.65rem] text-muted uppercase">{t("In")}</p><p className="num font-semibold text-good">{short(p.money_in)}</p></div>
                  <div><p className="text-[0.65rem] text-muted uppercase">{t("Out")}</p><p className="num font-semibold">{short(p.money_out)}</p></div>
                  <div><p className="text-[0.65rem] text-muted uppercase">{t("Closing")}</p><p className={cx("num font-bold", p.closing < 0 ? "text-bad" : p.closing < data.safety ? "text-caution" : "text-ink")}>{short(p.closing)}</p></div>
                </div>
                <div className="mt-2 flex items-center justify-between gap-2 text-xs text-ink-2">
                  <span>{net >= 0 ? t("Net +{amt}", { amt: short(net) }) : t("Net −{amt}", { amt: short(-net) })} · {t("lowest {amt} on {d}", { amt: short(p.lowest), d: fmtDay(p.lowest_date, lang) })}</span>
                  {p.items.length > 0 && <ChevronDown className={cx("size-4 shrink-0 text-muted transition", isOpen && "rotate-180")} />}
                </div>
                {low && p.kind !== "actual" && <p className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-caution"><AlertTriangle className="size-3.5" /> {neg ? t("goes negative") : t("dips below your cushion")}</p>}
              </button>
              {isOpen && p.items.length > 0 && (
                <ul className="divide-y divide-line border-t border-line text-sm">
                  {p.items.map((it, k) => (
                    <li key={k} className="flex items-center gap-3 px-4 py-2">
                      <span className="w-14 shrink-0 text-xs text-muted">{fmtDay(it.date, lang)}</span>
                      <span className="min-w-0 flex-1 truncate">{it.label.replace(/^(INV|BILL|SCH)-[\w-]+ (from|to) /, "")}</span>
                      <span className={cx("num shrink-0 font-semibold", it.amount > 0 ? "text-good" : "text-ink")}>{it.amount > 0 ? "+" : "−"}{short(Math.abs(it.amount))}</span>
                    </li>
                  ))}
                  <li className="bg-surface-2/60 px-4 py-2 text-xs text-ink-2">{t("Biggest known items; day-to-day sales and costs are included in the totals.")}</li>
                </ul>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-xs text-muted">{t("How it's worked out")}: {data.method}</p>
    </div>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "good" | "caution" | "bad" }) {
  return (
    <div className="card p-4">
      <p className="text-xs tracking-wide text-muted uppercase">{label}</p>
      <p className={cx("serif text-3xl font-semibold", tone === "bad" ? "text-bad" : tone === "caution" ? "text-caution" : tone === "good" ? "text-good" : "text-ink")}>{value}</p>
      {sub && <p className="text-xs text-ink-2">{sub}</p>}
    </div>
  );
}
