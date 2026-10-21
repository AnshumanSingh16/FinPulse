"use client";

import { AlertTriangle, Loader2, SlidersHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { EvidenceButton } from "@/components/evidence";
import { cx, MoneyInput } from "@/components/ui";
import { post } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Evidence } from "@/lib/types";
import { day } from "./model";

interface Item { id: string; date: string; label: string; amount: number; group: string; included: boolean }
interface Outlook {
  status: string;
  message?: string;
  as_of: string;
  end_date: string;
  safety: number;
  start: number;
  end: number;
  change: number;
  lowest: number;
  lowest_date: string;
  below_cushion_from: string | null;
  runs_out: string | null;
  daily: { date: string; balance: number }[];
  waterfall: { key: string; label: string; amount: number }[];
  items: Item[];
  overdue: { id: string; party: string; amount: number; included: boolean }[];
  evidence: Evidence;
}

function Spark({ data, safety }: { data: { balance: number }[]; safety: number }) {
  const v = data.map((d) => d.balance);
  const hi = Math.max(...v, safety);
  const lo = Math.min(...v, safety, 0);
  const W = 320, H = 70;
  const x = (i: number) => (i / Math.max(v.length - 1, 1)) * W;
  const y = (n: number) => 4 + (1 - (n - lo) / Math.max(hi - lo, 1)) * (H - 8);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[70px] w-full" role="img" aria-label="Cash over the next two weeks">
      <line x1={0} x2={W} y1={y(safety)} y2={y(safety)} stroke="currentColor" className="text-caution" strokeDasharray="4 4" strokeWidth="1" />
      {lo < 0 && <line x1={0} x2={W} y1={y(0)} y2={y(0)} stroke="currentColor" className="text-bad" strokeWidth="1" />}
      <path d={v.map((n, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(n).toFixed(1)}`).join(" ")} fill="none" stroke="currentColor" className="text-brand" strokeWidth="2.2" strokeLinejoin="round" />
    </svg>
  );
}

/** Cash in two weeks, as a scenario the owner can change: which payments arrive, which bills to hold, sales level, a purchase. */
export function OutlookCard() {
  const { t, lang } = useT();
  const [r, setR] = useState<Outlook | null>(null);
  const [skip, setSkip] = useState<string[]>([]);
  const [od, setOd] = useState<string[]>([]);
  const [sales, setSales] = useState(100);
  const [buy, setBuy] = useState("");
  const [buyDate, setBuyDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const seq = useRef(0);
  useEffect(() => {
    const n = ++seq.current;
    setBusy(true);
    const h = setTimeout(() => {
      post<Outlook>("/api/outlook", { days: 14, skip, overdue_pay: od, sales_pct: sales, purchase: Number(buy) > 0 ? { amount: Number(buy), date: buyDate || null, label: t("Planned purchase") } : null })
        .then((x) => { if (n === seq.current) setR(x); })
        .finally(() => { if (n === seq.current) setBusy(false); });
    }, 250);
    return () => clearTimeout(h);
  }, [skip, od, sales, buy, buyDate, t]);

  if (!r) return <p className="flex items-center gap-2 text-ink-2"><Loader2 className="size-4 animate-spin" /> {t("Working out the next two weeks…")}</p>;
  if (r.status !== "ok") return <p className="text-ink-2">{r.message}</p>;
  const toggle = (list: string[], set: (v: string[]) => void, id: string) => set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const coll = r.items.filter((i) => i.group === "collection");
  const bills = r.items.filter((i) => i.group === "bill");
  const tone = r.runs_out ? "text-bad" : r.below_cushion_from ? "text-caution" : "text-good";
  return (
    <div className="overflow-hidden rounded-3xl border border-line bg-surface">
      <div className="px-5 pt-4">
        <p className="text-[0.65rem] font-semibold tracking-[0.16em] text-muted uppercase">{t("Cash in two weeks · a scenario, not a promise")}</p>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-3">
          <p className={cx("serif text-4xl font-semibold", tone)}>{short(r.end)}</p>
          <p className="text-sm text-ink-2">{t("on {date}", { date: day(r.end_date, lang) })} · {r.change >= 0 ? "+" : "−"}{short(Math.abs(r.change))} {t("vs today")}</p>
          {busy && <Loader2 className="size-4 animate-spin text-muted" />}
        </div>
        <p className="mt-1 text-sm text-ink-2">
          {r.runs_out ? <><AlertTriangle className="mr-1 inline size-4 text-bad" />{t("Runs out on {date}.", { date: day(r.runs_out, lang) })} </>
            : r.below_cushion_from ? <><AlertTriangle className="mr-1 inline size-4 text-caution" />{t("Below your cushion from {date}.", { date: day(r.below_cushion_from, lang) })} </> : null}
          {t("Lowest point: {amt} on {date}.", { amt: short(r.lowest), date: day(r.lowest_date, lang) })}
        </p>
        <div className="mt-2"><Spark data={r.daily} safety={r.safety} /></div>
      </div>
      <ul className="mx-5 my-3 divide-y divide-dashed divide-line border-y border-line text-sm">
        {r.waterfall.map((w) => (
          <li key={w.key} className="flex justify-between gap-3 py-1.5">
            <span className={w.key === "start" ? "font-semibold" : "text-ink-2"}>{w.key === "typical_in" ? t("Day-to-day sales ({p}% of usual)", { p: sales }) : t(w.label)}</span>
            <span className={cx("num font-medium", w.key !== "start" && (w.amount < 0 ? "text-ink" : "text-good"))}>{w.key === "start" ? inr(w.amount) : `${w.amount < 0 ? "−" : "+"}${inr(Math.abs(w.amount))}`}</span>
          </li>
        ))}
        <li className="flex justify-between gap-3 py-1.5 font-semibold"><span>{t("Cash on {date}", { date: day(r.end_date, lang) })}</span><span className="num">{inr(r.end)}</span></li>
      </ul>
      <div className="px-5 pb-4">
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={() => setOpen(!open)} className="inline-flex items-center gap-1.5 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-canvas">
            <SlidersHorizontal className="size-4" /> {open ? t("Hide assumptions") : t("Change the assumptions")}
          </button>
          <EvidenceButton evidence={r.evidence} label={t("Show me why")} />
        </div>
        {open && (
          <div className="mt-4 space-y-5 text-sm">
            <div>
              <p className="font-semibold">{t("Day-to-day sales: {p}% of usual", { p: sales })}</p>
              <input type="range" min={50} max={130} step={10} value={sales} onChange={(e) => setSales(Number(e.target.value))} className="mt-1 w-full accent-[var(--color-brand)]" aria-label={t("Day-to-day sales")} />
            </div>
            {r.overdue.length > 0 && (
              <div>
                <p className="font-semibold">{t("Overdue — tick if you're confident they'll pay this week")}</p>
                {r.overdue.map((o) => (
                  <label key={o.id} className="mt-1 flex items-center gap-2"><input type="checkbox" checked={od.includes(o.id)} onChange={() => toggle(od, setOd, o.id)} className="size-4 accent-[var(--color-brand)]" />
                    <span className="flex-1">{o.party} · {o.id}</span><span className="num">{inr(o.amount)}</span></label>
                ))}
              </div>
            )}
            {coll.length > 0 && (
              <div>
                <p className="font-semibold">{t("Customer payments expected — untick any you doubt")}</p>
                {coll.map((i) => (
                  <label key={i.id} className="mt-1 flex items-center gap-2"><input type="checkbox" checked={!skip.includes(i.id)} onChange={() => toggle(skip, setSkip, i.id)} className="size-4 accent-[var(--color-brand)]" />
                    <span className="flex-1 truncate">{i.label.replace(/^INV-\S+ from /, "")} · {day(i.date, lang)}</span><span className="num text-good">+{inr(i.amount)}</span></label>
                ))}
              </div>
            )}
            {bills.length > 0 && (
              <div>
                <p className="font-semibold">{t("Bills due — untick one to see the effect of holding it")}</p>
                {bills.map((i) => (
                  <label key={i.id} className="mt-1 flex items-center gap-2"><input type="checkbox" checked={!skip.includes(i.id)} onChange={() => toggle(skip, setSkip, i.id)} className="size-4 accent-[var(--color-brand)]" />
                    <span className="flex-1 truncate">{i.label.replace(/^(SCH|BILL)-\S+ to /, "")} · {day(i.date, lang)}</span><span className="num">−{inr(-i.amount)}</span></label>
                ))}
              </div>
            )}
            <div>
              <p className="font-semibold">{t("A purchase you're planning")}</p>
              <div className="mt-1 grid grid-cols-[1fr_auto] gap-2">
                <MoneyInput value={buy} onChange={setBuy} placeholder="0" />
                <input type="date" value={buyDate} min={r.as_of} max={r.end_date} onChange={(e) => setBuyDate(e.target.value)} className="h-12 rounded-2xl border border-line bg-surface px-3" aria-label={t("Date")} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
