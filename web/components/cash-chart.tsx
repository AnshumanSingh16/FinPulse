"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { inr, tick } from "@/lib/format";
import { useT } from "@/lib/i18n";

interface Point {
  date: string;
  balance: number;
}

function label(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

/** The next 90 days: what happens if nothing is done (dashed) vs with the plan (solid), against the safety level. */
export function CashChart({ baseline, plan, safety, planLabel }: { baseline: Point[]; plan: Point[]; safety: number; planLabel: string }) {
  const { t } = useT();
  const data = baseline.map((b, i) => ({ date: b.date, baseline: b.balance, plan: plan[i]?.balance ?? null }));
  const same = baseline.every((b, i) => Math.abs((plan[i]?.balance ?? b.balance) - b.balance) < 1);
  return (
    <div>
      <div className="h-56 w-full sm:h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--color-grid)" />
            <XAxis dataKey="date" tickFormatter={label} tick={{ fontSize: 11, fill: "var(--color-muted)" }} interval="preserveStartEnd" minTickGap={28} tickLine={false} axisLine={false} />
            <YAxis tickFormatter={tick} tick={{ fontSize: 11, fill: "var(--color-muted)" }} width={58} tickLine={false} axisLine={false} />
            <ReferenceLine y={safety} stroke="var(--color-caution)" strokeDasharray="5 4" label={{ value: t("Your cushion"), position: "insideTopRight", fontSize: 11, fill: "var(--color-caution)" }} />
            <ReferenceLine y={0} stroke="var(--color-bad)" strokeOpacity={0.5} />
            <Tooltip
              content={({ active, payload, label: l }) =>
                active && payload?.length ? (
                  <div className="rounded-xl border border-line bg-elevated px-3 py-2 text-sm shadow-lg">
                    <p className="mb-1 font-medium">{label(String(l))}</p>
                    {payload.map((p) => (
                      <p key={String(p.dataKey)} className="flex items-center gap-2 text-ink-2">
                        <span className="inline-block h-0.5 w-3" style={{ background: p.color }} />
                        {p.dataKey === "plan" ? t(planLabel) : t("If nothing is done")}: <span className="num font-medium text-ink">{inr(Number(p.value))}</span>
                      </p>
                    ))}
                  </div>
                ) : null
              }
            />
            <Line type="stepAfter" dataKey="baseline" stroke="var(--color-muted)" strokeWidth={2} strokeDasharray={same ? undefined : "5 4"} dot={false} isAnimationActive={false} />
            {!same && <Line type="stepAfter" dataKey="plan" stroke="var(--color-brand)" strokeWidth={2.5} dot={false} isAnimationActive={false} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-muted" /> {t("If nothing is done")}</span>
        {!same && <span className="inline-flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 bg-brand" /> {t(planLabel)}</span>}
        <span className="inline-flex items-center gap-1.5"><span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-caution" /> {t("Your cushion")}</span>
      </div>
    </div>
  );
}
