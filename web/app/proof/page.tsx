"use client";

import { Info, Target } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card, cx, ErrorNote, Loading } from "@/components/ui";
import { useApi } from "@/lib/api";
import { short, tick } from "@/lib/format";
import { useT } from "@/lib/i18n";

interface Point {
  date: string;
  forecast_lowest: number;
  actual_lowest: number;
  safety: number;
  flagged: boolean;
  dipped: boolean;
}
interface Track {
  status: string;
  message?: string;
  business: string;
  is_demo: boolean;
  weeks: number;
  period: [string, string];
  horizon_days: number;
  median_low_error: number;
  median_flat_low_error: number;
  low_better_than_flat_pct: number | null;
  median_path_error: number;
  median_flat_path_error: number;
  path_better_than_flat_pct: number | null;
  range_coverage: number;
  low_range_coverage: number;
  brier: number;
  calibration: { range: [number, number]; weeks: number; said: number; happened: number }[];
  dips: number;
  dips_flagged: number;
  missed_dip_depth: number;
  flags: number;
  false_alarms: number;
  points: Point[];
}

const pct = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);

function day(iso: string, lang = "en") {
  return new Date(iso + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short" });
}

export default function ProofPage() {
  const { t, lang } = useT();
  const { data: r, error, reload } = useApi<Track>("/api/track-record");
  if (error) return <ErrorNote message={error} retry={reload} />;
  if (!r) return <Loading label={t("Testing the forecast on your past weeks…")} />;
  if (r.status !== "ok") return <Card>{r.message}</Card>;
  const series = r.points.map((p) => ({ date: p.date, forecast: p.forecast_lowest, actual: p.actual_lowest, cushion: p.safety }));
  const cal = r.calibration.map((b) => ({ name: `${Math.round(b.range[0] * 100)}–${Math.round(b.range[1] * 100)}%`, said: Math.round(b.said * 100), happened: Math.round(b.happened * 100), weeks: b.weeks }));
  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-2xl"><Target className="size-6 text-brand" /> {t("Track record")}</h1>
        <p className="text-sm text-ink-2">
          {t("For each of {n} past weeks ({a} – {b}), FinPilot rewound {biz}'s books to that day, forecast the next {d} days exactly as it does today, and compared with what really happened.",
            { n: r.weeks, a: day(r.period[0], lang), b: day(r.period[1], lang), biz: r.business, d: r.horizon_days })}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Stat big={pct(r.low_better_than_flat_pct)} title={t("Closer on the tightest day")}
          sub={t("Typical miss {a}, against {b} if you just assumed the balance stays where it is.", { a: short(r.median_low_error), b: short(r.median_flat_low_error) })} good={(r.low_better_than_flat_pct ?? 0) > 0} />
        <Stat big={pct(r.path_better_than_flat_pct)} title={t("Closer over the whole month")}
          sub={t("Average daily miss {a}, against {b} for the same guess.", { a: short(r.median_path_error), b: short(r.median_flat_path_error) })} good={(r.path_better_than_flat_pct ?? 0) > 0} />
        <Stat big={r.dips ? `${r.dips_flagged}/${r.dips}` : "—"} title={t("Real dips flagged in advance")}
          sub={r.dips ? t("Weeks where cash really fell below the cushion within 30 days. False alarms: {f} of {n} warnings.", { f: r.false_alarms, n: r.flags })
            + (r.dips_flagged < r.dips ? " " + t("The dips it missed went at most {amt} below the cushion.", { amt: short(r.missed_dip_depth) }) : "")
            : t("Cash never fell below the cushion in these weeks.")} good={!r.dips || r.dips_flagged / r.dips >= 0.8} />
        <Stat big={r.brier.toFixed(2)} title={t("Odds score (lower is better)")}
          sub={t("How well “chance you stay safe” matched what happened: 0 is perfect, 0.25 is a coin flip.")} good={r.brier < 0.15} />
      </div>

      <Card>
        <p className="font-semibold">{t("Tightest day: forecast vs what happened")}</p>
        <div className="mt-2 h-56 sm:h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--color-grid)" />
              <XAxis dataKey="date" tickFormatter={(d) => day(String(d), lang)} tick={{ fontSize: 11, fill: "var(--color-muted)" }} minTickGap={28} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={tick} tick={{ fontSize: 11, fill: "var(--color-muted)" }} width={58} tickLine={false} axisLine={false} />
              <Tooltip formatter={(v) => short(Number(v))} labelFormatter={(d) => day(String(d), lang)} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="actual" name={t("What happened")} stroke="var(--color-ink)" strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="forecast" name={t("FinPilot's forecast")} stroke="var(--color-brand)" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
              <Line type="stepAfter" dataKey="cushion" name={t("Your cushion")} stroke="var(--color-caution)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {cal.length > 1 && (
        <Card>
          <p className="font-semibold">{t("When FinPilot said… how often it happened")}</p>
          <p className="text-sm text-ink-2">{t("Weeks grouped by the chance FinPilot gave of staying above the cushion. Good odds match the real share.")}</p>
          <div className="mt-2 h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={cal} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke="var(--color-grid)" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--color-muted)" }} tickLine={false} axisLine={false} />
                <YAxis unit="%" tick={{ fontSize: 11, fill: "var(--color-muted)" }} width={40} tickLine={false} axisLine={false} domain={[0, 100]} />
                <Tooltip formatter={(v) => `${v}%`} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="said" name={t("FinPilot said")} fill="var(--color-brand)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                <Bar dataKey="happened" name={t("Really stayed safe")} fill="var(--color-ink-2)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      <Card className="space-y-2 text-sm text-ink-2">
        <p className="flex items-center gap-2 font-semibold text-ink"><Info className="size-4" /> {t("Read this honestly")}</p>
        <p>{t("The real 30-day balance fell inside FinPilot's 10–90% range in {a} of weeks (the aim is 80%); the real tightest day in {b}.", { a: pct(r.range_coverage), b: pct(r.low_range_coverage) })}{" "}
          {r.range_coverage < 0.7 ? t("So the range is too narrow here — treat the odds as a guide, not a guarantee.") : ""}</p>
        {r.is_demo && <p>{t("This demo's history is simulated, so these numbers show how the method works, not how it will do on your business. Upload your own bank statement to see your own track record.")}</p>}
        <p>{t("Nothing is tuned to these answers: the forecast and simulation are the same code the app uses today.")}</p>
      </Card>
    </div>
  );
}

function Stat({ big, title, sub, good }: { big: string; title: string; sub: string; good: boolean }) {
  return (
    <Card>
      <p className={cx("num text-3xl font-bold", good ? "text-good" : "text-caution")}>{big}</p>
      <p className="font-semibold">{title}</p>
      <p className="text-sm text-ink-2">{sub}</p>
    </Card>
  );
}
