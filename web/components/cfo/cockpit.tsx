"use client";

import { Eye, Pencil } from "lucide-react";
import Link from "next/link";
import { CountUp } from "@/components/fx";
import { cx } from "@/components/ui";
import { short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { currentOdds, day, pct, standing, type Plan } from "./model";

/** 90 days of cash as a clean line: what happens if nothing changes (dim) and with the plan (glowing), against the cushion. */
function CashLine({ p, height = 150 }: { p: Plan; height?: number }) {
  const { lang } = useT();
  const base = p.series.baseline.map((x) => x.balance);
  const plan = p.series.plan.map((x) => x.balance);
  const same = base.every((v, i) => Math.abs(v - (plan[i] ?? v)) < 1);
  const all = [...base, ...plan, p.safety, 0];
  const hi = Math.max(...all);
  const lo = Math.min(...all);
  const W = 360;
  const H = height;
  const pad = 6;
  const x = (i: number) => pad + (i / Math.max(base.length - 1, 1)) * (W - 2 * pad);
  const y = (v: number) => pad + (1 - (v - lo) / Math.max(hi - lo, 1)) * (H - 2 * pad);
  const path = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = (vals: number[]) => `${path(vals)} L${x(vals.length - 1).toFixed(1)},${H} L${x(0).toFixed(1)},${H} Z`;
  const months = p.series.baseline
    .map((d, i) => ({ i, d: d.date }))
    .filter(({ d }, k, arr) => k === 0 || d.slice(5, 7) !== arr[k - 1].d.slice(5, 7));
  const main = same ? base : plan;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }} role="img" aria-label="Cash over the next 90 days">
        <defs>
          <linearGradient id="fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#3ee6a8" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#3ee6a8" stopOpacity="0" />
          </linearGradient>
        </defs>
        {lo < 0 && <line x1={pad} x2={W - pad} y1={y(0)} y2={y(0)} stroke="#ff8a5c" strokeOpacity="0.55" strokeWidth="1" />}
        <line x1={pad} x2={W - pad} y1={y(p.safety)} y2={y(p.safety)} stroke="#ffc861" strokeOpacity="0.7" strokeDasharray="4 4" strokeWidth="1" />
        <path d={area(main)} fill="url(#fill)" />
        {!same && <path d={path(base)} fill="none" stroke="#8fa39b" strokeOpacity="0.7" strokeWidth="1.5" strokeDasharray="3 3" />}
        <path d={path(main)} fill="none" stroke="#3ee6a8" strokeWidth="2.2" strokeLinejoin="round" style={{ filter: "drop-shadow(0 0 6px rgb(62 230 168 / .55))" }} />
      </svg>
      <div className="mt-1 flex justify-between text-[0.65rem] tracking-wide text-pit-muted uppercase">
        {months.slice(0, 4).map((m) => <span key={m.d}>{day(m.d, lang)}</span>)}
      </div>
    </div>
  );
}

const STATUS: Record<string, string> = { done: "Done", waiting: "Waiting", missed: "Missed", partial: "Part paid", slipped: "Slipped" };

export function Cockpit({ p, onCushion, compact }: { p: Plan; onCushion: () => void; compact?: boolean }) {
  const { t, lang } = useT();
  const s = standing(p);
  const anyApproved = p.moves.some((m) => m.state !== "open");
  const b = anyApproved ? p.with_approved : p.baseline;
  const odds = currentOdds(p);
  const backup = p.moves.find((m) => m.kind === "borrow" && m.state === "open");
  const best = anyApproved ? null : backup?.odds_with_plan ?? (p.moves.some((m) => m.suggested && m.kind !== "reserve") ? p.odds.suggested.p_safe : null);
  const tone = s === "out" ? "ember-text" : s === "tight" || s === "unsure" ? "amber-text" : "glow-text";
  const status =
    s === "out" ? t("Runs out in {n} days", { n: b.days_to_trouble ?? 0 })
      : s === "tight" ? t("Tight in {n} days", { n: b.days_to_trouble ?? 0 })
        : s === "unsure" ? t("Safe, not certain")
          : t("Covered for 90 days");

  if (compact) {
    return (
      <div className="pit flex items-center gap-4 px-4 py-3 text-sm">
        <div>
          <p className="text-[0.6rem] tracking-[0.14em] text-pit-muted uppercase">{t("Safe to spend")}</p>
          <p className={cx("serif text-2xl font-semibold", b.spendable_today > 0 ? "glow-text" : "ember-text")}>{short(b.spendable_today)}</p>
        </div>
        <div className="min-w-0 flex-1">
          <p className={cx("truncate font-semibold", tone)}>{status}</p>
          <p className="text-xs text-pit-muted">{t("{p} chance you stay safe", { p: pct(odds.p_safe) })}{best != null && best > odds.p_safe ? ` → ${pct(best)}` : ""}</p>
        </div>
      </div>
    );
  }

  return (
    <aside className="pit no-scrollbar flex h-full flex-col gap-4 overflow-y-auto p-6">
      <div className="flex items-center justify-between text-[0.65rem] tracking-[0.16em] text-pit-muted uppercase">
        <span className="inline-flex items-center gap-2"><span className="breathe size-2 rounded-full bg-glow" /> {t("Live")} · {day(p.as_of, lang)}</span>
        <span>{t("next 90 days")}</span>
      </div>

      <div>
        <p className="text-xs tracking-[0.14em] text-pit-muted uppercase">{t("Safe to spend today")}</p>
        <p className={cx("serif text-6xl leading-none font-semibold tracking-tight", b.spendable_today > 0 ? "glow-text" : "ember-text")}>
          <CountUp value={b.spendable_today} format={short} />
        </p>
        <p className="mt-2 text-sm text-pit-muted">
          {t("of {cash} in the bank", { cash: short(p.today) })} ·{" "}
          <button onClick={onCushion} className="inline-flex items-center gap-1 underline decoration-pit-line underline-offset-4 hover:text-pit-ink">
            <Pencil className="size-3" /> {t("cushion {amt}", { amt: short(p.safety) })}
          </button>
        </p>
      </div>

      <div className="pit-card p-4">
        <p className={cx("serif text-2xl font-semibold", tone)}>{status}</p>
        <p className="text-sm text-pit-muted">
          {b.runs_out ? t("on {date}, if nothing changes", { date: day(b.runs_out, lang) })
            : b.below_safety_from ? t("below your cushion from {date}", { date: day(b.below_safety_from, lang) })
              : t("tightest day {date}: {amt}", { date: day(b.lowest_date, lang), amt: short(b.lowest) })}
        </p>
        <div className="mt-3"><CashLine p={p} /></div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[0.7rem] text-pit-muted">
          <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-4 bg-glow" /> {anyApproved ? t("with your plan") : p.moves.some((m) => m.suggested && m.kind !== "reserve") ? t("with the fix") : t("forecast")}</span>
          <span className="inline-flex items-center gap-1.5"><span className="h-0 w-4 border-t border-dashed border-amber" /> {t("your cushion")}</span>
        </div>
      </div>

      <div className="pit-card p-4">
        <p className="text-xs tracking-[0.14em] text-pit-muted uppercase">{t("Chance you stay safe")}</p>
        <div className="mt-1 flex items-baseline gap-3">
          <span className={cx("serif text-4xl font-semibold", odds.p_safe >= p.odds.target ? "glow-text" : odds.p_safe >= 0.4 ? "amber-text" : "ember-text")}>{pct(odds.p_safe)}</span>
          {best != null && best > odds.p_safe && <span className="serif text-2xl text-pit-muted">→ <span className="glow-text">{pct(best)}</span></span>}
        </div>
        <div className="relative mt-2 h-1.5 overflow-hidden rounded-full bg-pit-line">
          {best != null && <div className="absolute inset-y-0 left-0 rounded-full bg-glow/30" style={{ width: `${best * 100}%` }} />}
          <div className="absolute inset-y-0 left-0 rounded-full bg-glow" style={{ width: `${Math.max(odds.p_safe * 100, 1.5)}%` }} />
        </div>
        <p className="mt-2 text-xs text-pit-muted">{t("across {n} simulated futures, from how your customers really pay", { n: odds.sims.toLocaleString("en-IN") })}</p>
      </div>

      {anyApproved && p.with_approved.lowest - p.baseline.lowest > 1 && (
        <div className="pit-card p-4">
          <p className="text-xs tracking-[0.14em] text-pit-muted uppercase">{t("Your agents' impact")}</p>
          <p className="serif mt-1 text-2xl glow-text">+{short(p.with_approved.lowest - p.baseline.lowest)}</p>
          <p className="text-xs text-pit-muted">
            {t("on your tightest day")} · {t("odds {a} → {b}", { a: pct(p.odds.baseline.p_safe), b: pct(odds.p_safe) })}
            {p.baseline.runs_out && !p.with_approved.runs_out ? ` · ${t("no longer runs out")}` : ""}
          </p>
        </div>
      )}

      {p.events.length > 0 && (
        <div className="pit-card p-4">
          <p className="text-xs tracking-[0.14em] text-pit-muted uppercase">{t("Coming up (you told me)")}</p>
          <ul className="mt-2 space-y-1.5 text-sm">
            {p.events.map((e) => (
              <li key={e.id} className="flex items-center justify-between gap-2">
                <span className="truncate">{e.label}</span>
                <span className={cx("shrink-0 text-xs", e.amount > 0 ? "text-glow" : "text-ember")}>{e.amount > 0 ? "+" : "−"}{short(Math.abs(e.amount))} · {day(e.date, lang)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {p.follow_through?.length > 0 && (
        <div className="pit-card p-4">
          <p className="text-xs tracking-[0.14em] text-pit-muted uppercase">{t("What you approved — and what happened")}</p>
          <ul className="mt-2 space-y-2.5 text-sm">
            {p.follow_through.map((f) => (
              <li key={f.move_id}>
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">{f.kind === "pause" ? (f.party === "Owner Drawings" ? t("Pause owner drawings") : t("Pause marketing")) : f.kind === "reserve" ? t("GST set aside") : f.kind === "borrow" ? t("Standby overdraft") : f.party}</span>
                  <span className={cx("shrink-0 rounded-full px-2 py-0.5 text-[0.65rem] font-semibold tracking-wide uppercase",
                    f.status === "done" ? "bg-glow/15 text-glow" : f.status === "missed" || f.status === "slipped" ? "bg-ember/15 text-ember" : "bg-pit-line text-pit-muted")}>
                    {t(STATUS[f.status])}
                  </span>
                </div>
                <p className="text-xs text-pit-muted">{f.result}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="pit-card p-4">
        <p className="flex items-center gap-2 text-xs tracking-[0.14em] text-pit-muted uppercase"><Eye className="size-3.5" /> {t("Watching")}</p>
        {p.watching.length ? (
          <ul className="mt-2 space-y-1.5 text-sm">
            {p.watching.map((w) => (
              <li key={w.move_id} className="flex items-center justify-between gap-2">
                <span className="truncate">{w.party}</span>
                <span className="shrink-0 text-xs text-pit-muted">{t("by {date}", { date: day(w.checkpoint, lang) })}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-pit-muted">{t("Nothing yet — approve a plan and I'll keep an eye on it.")}</p>
        )}
      </div>

      <div className="mt-auto flex flex-wrap gap-x-4 gap-y-1 text-xs text-pit-muted">
        <Link href="/timeline/" className="hover:text-pit-ink">{t("Week by week")} →</Link>
        <Link href="/khata/" className="hover:text-pit-ink">{t("Who owes you")} →</Link>
        <Link href="/proof/" className="hover:text-pit-ink">{t("Track record")} →</Link>
      </div>
    </aside>
  );
}
