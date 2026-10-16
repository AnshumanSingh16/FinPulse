"use client";

import { AlertTriangle, ArrowDownLeft, ArrowUpRight, ChevronDown } from "lucide-react";
import { useContext, useEffect, useState } from "react";
import { DataVersion } from "@/components/data-version";
import { Card, cx, Loading } from "@/components/ui";
import { get } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";

interface Week {
  start: string;
  end: string;
  money_in: number;
  money_out: number;
  closing: number;
  typical_in: number;
  typical_out: number;
  items: { date: string; label: string; amount: number; source: string; kind: string }[];
}
interface Data {
  status: string;
  message?: string;
  today: number;
  safety: number;
  plan_basis: "approved" | "suggested";
  weekly: Week[];
  moves: { state: string }[];
}

function d(iso: string, lang: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short" });
}

/** Turn engine labels ("INV-0064 from Zenith Realty", "SCH-0001 to Staff payroll") into plain words. */
function plain(it: Week["items"][number], t: (k: string, v?: Record<string, string | number>) => string) {
  const [kind, rest] = [it.source.split(":")[0], it.source.slice(it.source.indexOf(":") + 1)];
  if (it.kind === "scenario") {
    if (kind === "collect") return t("{name} pays after your reminder", { name: rest });
    if (kind === "pause") return t("{what} paused (saved this week)", { what: t(rest) });
    if (kind === "defer") return it.amount > 0 ? t("{id} — moved to a later date", { id: rest }) : t("{id} — paid on the new date", { id: rest });
  }
  return it.label.replace(/^(INV|BILL|SCH)-[\w-]+ (from|to) /, "");
}

export default function TimelinePage() {
  const { t, lang } = useT();
  const { version } = useContext(DataVersion);
  const [data, setData] = useState<Data | null>(null);
  const [open, setOpen] = useState<number | null>(0);
  useEffect(() => {
    get<Data>("/api/autopilot").then(setData).catch(() => setData(null));
  }, [version]);
  if (!data) return <Loading />;
  if (data.status !== "ok") return <Card className="text-ink-2">{data.message}</Card>;
  const approved = data.moves.some((m) => m.state === "approved" || m.state === "done");
  const max = Math.max(...data.weekly.map((w) => Math.max(w.money_in, w.money_out)), 1);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl">{t("Cash timeline")}</h1>
        <p className="text-sm text-ink-2">
          {t("Money in and out, week by week, for the next 13 weeks.")} {approved ? t("Includes the moves you approved.") : t("If nothing changes — approve moves on the Cash tab to see their effect.")}
        </p>
      </div>
      <ol className="space-y-2.5">
        {data.weekly.map((w, i) => {
          const low = w.closing < data.safety;
          const neg = w.closing < 0;
          const isOpen = open === i;
          return (
            <li key={w.start} className={cx("card overflow-hidden", neg ? "ring-2 ring-bad/40" : low && "ring-2 ring-caution/40")}>
              <button onClick={() => setOpen(isOpen ? null : i)} className="flex w-full items-center gap-3 p-4 text-left" aria-expanded={isOpen}>
                <div className="w-24 shrink-0">
                  <p className="text-sm font-semibold">{d(w.start, lang)} – {d(w.end, lang)}</p>
                  <p className="text-xs text-muted">{t("Week {n}", { n: i + 1 })}</p>
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center gap-2 text-xs">
                    <ArrowDownLeft className="size-3.5 shrink-0 text-good" />
                    <div className="h-2 rounded-full bg-in" style={{ width: `${(w.money_in / max) * 100}%` }} />
                    <span className="num shrink-0 text-ink-2">{short(w.money_in)}</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    <ArrowUpRight className="size-3.5 shrink-0 text-bad" />
                    <div className="h-2 rounded-full bg-out" style={{ width: `${(w.money_out / max) * 100}%` }} />
                    <span className="num shrink-0 text-ink-2">{short(w.money_out)}</span>
                  </div>
                </div>
                <div className="w-24 shrink-0 text-right">
                  <p className="text-[0.65rem] font-semibold tracking-wide text-muted uppercase">{t("Closing")}</p>
                  <p className={cx("num font-bold", neg ? "text-bad" : low ? "text-caution" : "text-ink")}>{short(w.closing)}</p>
                  {low && <p className="inline-flex items-center gap-1 text-[0.65rem] font-semibold text-caution"><AlertTriangle className="size-3" /> {neg ? t("negative") : t("below safety")}</p>}
                </div>
                <ChevronDown className={cx("size-4 shrink-0 text-muted transition", isOpen && "rotate-180")} />
              </button>
              {isOpen && (
                <ul className="divide-y divide-line border-t border-line text-sm">
                  {w.items.map((it, k) => (
                    <li key={k} className="flex items-center gap-3 px-4 py-2">
                      <span className="w-14 shrink-0 text-xs text-muted">{d(it.date, lang)}</span>
                      <span className="min-w-0 flex-1 truncate">
                        {plain(it, t)}
                        {it.kind === "scenario" && <span className="ml-1.5 rounded-full bg-brand-50 px-1.5 text-[0.65rem] font-semibold text-brand">{t("plan")}</span>}
                      </span>
                      <span className={cx("num shrink-0 font-semibold", it.amount > 0 ? "text-good" : "text-ink")}>{it.amount > 0 ? "+" : "−"}{inr(Math.abs(it.amount))}</span>
                    </li>
                  ))}
                  {(w.typical_in > 0 || w.typical_out > 0) && (
                    <li className="flex items-center gap-3 bg-surface-2/60 px-4 py-2 text-ink-2">
                      <span className="w-14 shrink-0 text-xs">{t("all week")}</span>
                      <span className="min-w-0 flex-1">{t("Typical day-to-day sales and costs (from your last 3 months)")}</span>
                      <span className="num shrink-0 text-xs">+{short(w.typical_in)} / −{short(w.typical_out)}</span>
                    </li>
                  )}
                  {w.items.length === 0 && w.typical_in === 0 && w.typical_out === 0 && <li className="px-4 py-2 text-muted">{t("Nothing scheduled.")}</li>}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
      <p className="text-center text-xs text-muted">{t("Arithmetic on your records and stated assumptions — not a prediction.")}</p>
    </div>
  );
}
