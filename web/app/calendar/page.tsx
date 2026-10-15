"use client";

import { ArrowDownLeft, ArrowUpRight, ChevronLeft, ChevronRight, Landmark, PiggyBank, Repeat } from "lucide-react";
import Link from "next/link";
import { useContext, useEffect, useState } from "react";
import { DataVersion } from "@/components/data-version";
import { EvidenceButton } from "@/components/evidence";
import { useToast } from "@/components/fx";
import { Button, Card, cx, Loading, SectionTitle } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Evidence } from "@/lib/types";

interface Ev {
  kind: "receivable" | "payable" | "expected" | "tax";
  title: string;
  detail: string;
  amount: number | null;
  id: string | null;
  overdue: boolean;
}
interface Day {
  date: string;
  day: number;
  in: number;
  out: number;
  events: Ev[];
}
interface Cal {
  year: number;
  month: number;
  label: string;
  first_weekday: number;
  today: string;
  days: Day[];
  money_in: number;
  money_out: number;
  due_in: number;
  due_out: number;
  gst?: { estimated_payable: number; output_gst: number; input_credit: number; gst_paid_in_period: number; evidence: Evidence };
  settings: { gst_rate_sales: string; gst_registered: string; gst_filing: string };
}

const EV_STYLE: Record<Ev["kind"], { dot: string; chip: string; I: React.ElementType }> = {
  receivable: { dot: "bg-good", chip: "bg-good-50 text-good", I: ArrowDownLeft },
  payable: { dot: "bg-bad", chip: "bg-bad-50 text-bad", I: ArrowUpRight },
  expected: { dot: "bg-[#f59e0b]", chip: "bg-caution-50 text-caution", I: Repeat },
  tax: { dot: "bg-brand", chip: "bg-brand-50 text-brand", I: Landmark },
};
const WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const WD_HI = ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"];

export default function CalendarPage() {
  const { t, lang } = useT();
  const { state, refresh } = useContext(DataVersion);
  const toast = useToast();
  const [ym, setYm] = useState<{ y: number; m: number } | null>(null);
  useEffect(() => {
    if (state && !ym) {
      const d = new Date(state.as_of + "T00:00:00");
      d.setDate(d.getDate() + 1); // on the last day of a month, open the month ahead
      setYm({ y: d.getFullYear(), m: d.getMonth() + 1 });
    }
  }, [state, ym]);
  const { data } = useApi<Cal>(ym ? `/api/calendar?year=${ym.y}&month=${ym.m}` : null);
  const [sel, setSel] = useState<string | null>(null);
  const shift = (n: number) => {
    if (!ym) return;
    const d = new Date(ym.y, ym.m - 1 + n, 1);
    setYm({ y: d.getFullYear(), m: d.getMonth() + 1 });
    setSel(null);
  };
  if (!data) return <Loading />;
  const selected = data.days.find((d) => d.date === sel) ?? data.days.find((d) => d.date === data.today) ?? null;
  const addGstGoal = async () => {
    if (!data.gst) return;
    await post("/api/goals", { name: `GST set-aside · ${data.label}`, target: Math.round(data.gst.estimated_payable), icon: "gst" });
    refresh();
    toast.show({ text: t("Add goal") + " ✓" });
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl">{t("Calendar")}</h1>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => shift(-1)} aria-label="Previous month">
            <ChevronLeft className="size-4" />
          </Button>
          <span className="w-40 text-center font-semibold">{data.label}</span>
          <Button variant="secondary" size="sm" onClick={() => shift(1)} aria-label="Next month">
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="grad-mint rounded-3xl p-4">
          <p className="text-xs text-white/85">{t("Money in")}</p>
          <p className="num text-xl font-bold">{short(data.money_in)}</p>
        </div>
        <div className="grad-sunset rounded-3xl p-4">
          <p className="text-xs text-white/85">{t("Money out")}</p>
          <p className="num text-xl font-bold">{short(data.money_out)}</p>
        </div>
        <div className="grad-ocean rounded-3xl p-4">
          <p className="text-xs text-white/85">Due to come in</p>
          <p className="num text-xl font-bold">{short(data.due_in)}</p>
        </div>
        <div className="grad-berry rounded-3xl p-4">
          <p className="text-xs text-white/85">Due to pay</p>
          <p className="num text-xl font-bold">{short(data.due_out)}</p>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
        <Card className="p-3 sm:p-5">
          <div className="grid grid-cols-7 gap-1 text-center text-xs font-semibold text-muted">
            {(lang === "hi" ? WD_HI : WD).map((w) => (
              <div key={w} className="py-1">
                {w}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {Array.from({ length: data.first_weekday }).map((_, i) => (
              <div key={`e${i}`} />
            ))}
            {data.days.map((d) => {
              const isToday = d.date === data.today;
              const isSel = selected?.date === d.date;
              const kinds = Array.from(new Set(d.events.map((e) => e.kind)));
              return (
                <button
                  key={d.date}
                  onClick={() => setSel(d.date)}
                  className={cx(
                    "flex aspect-square flex-col items-start rounded-xl p-1.5 text-left text-xs transition sm:aspect-[1.1] sm:p-2",
                    isSel ? "grad-violet shadow-lg" : isToday ? "bg-brand-50 ring-2 ring-brand" : d.date > data.today ? "bg-canvas/60 hover:bg-canvas" : "bg-canvas hover:bg-[#ece9f5]",
                  )}
                >
                  <span className={cx("font-semibold", isSel ? "text-white" : "text-ink")}>{d.day}</span>
                  {(d.in > 0 || d.out > 0) && (
                    <span className={cx("num mt-auto hidden w-full truncate text-[0.65rem] sm:block", isSel ? "text-white/90" : d.in - d.out >= 0 ? "text-good" : "text-bad")}>
                      {d.in - d.out >= 0 ? "+" : "−"}
                      {short(Math.abs(d.in - d.out)).replace("₹", "")}
                    </span>
                  )}
                  <span className="mt-auto flex gap-0.5 sm:mt-1">
                    {kinds.map((k) => (
                      <span key={k} className={cx("size-1.5 rounded-full", isSel ? "bg-white" : EV_STYLE[k].dot)} />
                    ))}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-xs text-ink-2">
            {(
              [
                ["receivable", "Customer payment due"],
                ["payable", "Bill due"],
                ["expected", "Regular payment (usual day)"],
                ["tax", "Typical tax date"],
              ] as const
            ).map(([k, l]) => (
              <span key={k} className="inline-flex items-center gap-1.5">
                <span className={cx("size-2 rounded-full", EV_STYLE[k].dot)} /> {l}
              </span>
            ))}
          </div>
        </Card>

        <div className="space-y-5">
          <Card>
            <SectionTitle>{selected ? new Date(selected.date + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { weekday: "long", day: "numeric", month: "long" }) : "—"}</SectionTitle>
            {selected && (
              <div className="space-y-2">
                {(selected.in > 0 || selected.out > 0) && (
                  <div className="flex gap-2 text-sm">
                    <span className="flex-1 rounded-xl bg-good-50 px-3 py-2 text-good">
                      + <span className="num font-semibold">{inr(selected.in)}</span>
                    </span>
                    <span className="flex-1 rounded-xl bg-bad-50 px-3 py-2 text-bad">
                      − <span className="num font-semibold">{inr(selected.out)}</span>
                    </span>
                  </div>
                )}
                {selected.events.length === 0 && selected.in === 0 && selected.out === 0 && <p className="text-sm text-muted">Nothing on this day.</p>}
                {selected.events.map((e, i) => {
                  const st = EV_STYLE[e.kind];
                  return (
                    <div key={i} className="flex items-start gap-3 rounded-2xl border border-line p-3">
                      <span className={cx("grid size-9 shrink-0 place-items-center rounded-xl", st.chip)}>
                        <st.I className="size-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold">{e.title}</p>
                        <p className="text-xs text-muted">
                          {e.detail}
                          {e.overdue && <span className="text-bad"> · {t("overdue")}</span>}
                        </p>
                      </div>
                      {e.amount != null && <span className="num text-sm font-semibold">{inr(e.amount)}</span>}
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {data.gst && (
            <div className="grad-violet rounded-[1.5rem] p-5 shadow-lg">
              <div className="flex items-center gap-2 text-sm text-white/85">
                <PiggyBank className="size-4" /> {t("GST set-aside")} · {data.label}
              </div>
              <p className="num mt-1 text-3xl font-bold">{inr(data.gst.estimated_payable)}</p>
              <p className="mt-1 text-xs text-white/80">
                Output {short(data.gst.output_gst)} − input credit {short(data.gst.input_credit)} at {data.settings.gst_rate_sales}% · estimate only
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" className="" onClick={addGstGoal} disabled={!data.gst.estimated_payable}>
                  <PiggyBank className="size-4" /> Set aside as a goal
                </Button>
                <EvidenceButton evidence={data.gst.evidence} className="!text-white" />
              </div>
              <Link href="/data/#settings" className="mt-2 block text-xs text-white/80 underline">
                Change GST rate / filing type
              </Link>
            </div>
          )}
        </div>
      </div>
      <p className="text-xs text-muted">Tax dates are the typical ones and can change — always confirm on the GST and income-tax portals. FinPilot never files anything.</p>
    </div>
  );
}
