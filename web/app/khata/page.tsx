"use client";

import { ArrowDownLeft, ArrowUpRight, HandCoins, MessageCircle, ReceiptText, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useContext, useEffect, useMemo, useState } from "react";
import { DataVersion } from "@/components/data-version";
import { Avatar } from "@/components/cat";
import { useQuickEntry } from "@/components/quick-entry";
import { ReminderSheet } from "@/components/reminder";
import { Button, cx, Loading, Pill, Sheet } from "@/components/ui";
import { useApi } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Tone } from "@/lib/types";

interface Person {
  name: string;
  outstanding: number;
  overdue: number;
  open_items: number;
  oldest_days_late: number;
  next_due: string | null;
  last_payment: string | null;
  reliability: { label: string; tone: Tone; on_time_pct: number | null };
  phone: string | null;
  promise: { amount: number; day: string; broken: boolean } | null;
}
interface People {
  side: "customers" | "suppliers";
  total: number;
  overdue: number;
  count: number;
  people: Person[];
}
interface Detail {
  name: string;
  kind: "customer" | "supplier";
  outstanding: number;
  overdue: number;
  total_business: number;
  timeline: { id: string; day: string; type: string; title: string; amount: number; status: string; due: string | null; late_days: number }[];
}

export default function KhataPage() {
  return (
    <Suspense>
      <Khata />
    </Suspense>
  );
}

function Khata() {
  const { t } = useT();
  const { state } = useContext(DataVersion);
  const who = state?.type_info ?? { customers: "customers", suppliers: "suppliers" };
  const params = useSearchParams();
  const router = useRouter();
  const side = params.get("side") === "suppliers" ? "suppliers" : "customers";
  const { data } = useApi<People>(`/api/people?side=${side}`);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [remind, setRemind] = useState<string | null>(null);
  const lena = side === "customers";
  const list = useMemo(() => (data?.people ?? []).filter((p) => p.name.toLowerCase().includes(q.toLowerCase())), [data, q]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 rounded-2xl bg-surface-2 p-1" role="tablist">
        {(["customers", "suppliers"] as const).map((s) => (
          <button key={s} role="tab" aria-selected={side === s} onClick={() => router.replace(`/khata/?side=${s}`)}
            className={cx("rounded-xl py-2.5 text-sm font-semibold transition", side === s ? "bg-surface text-ink shadow-sm" : "text-ink-2")}>
            {s === "customers" ? `${t("Owed to you")} · ${t(who.customers)}` : `${t("You owe")} · ${t(who.suppliers)}`}
          </button>
        ))}
      </div>

      {data && (
        <div className={cx("rounded-3xl p-5", lena ? "grad-mint" : "grad-sunset")}>
          <p className="text-sm text-white/85">{lena ? t("Your {who} owe you", { who: t(who.customers) }) : t("You owe your {who}", { who: t(who.suppliers) })}</p>
          <p className="num text-4xl font-bold">{short(data.total)}</p>
          <p className="mt-1 text-sm text-white/85">
            {data.overdue > 0 ? t("{amt} is overdue", { amt: short(data.overdue) }) : t("Nothing overdue")} · {t("{n} people", { n: data.count })}
          </p>
        </div>
      )}

      <div className="flex h-11 items-center gap-2 rounded-2xl border border-line bg-surface px-3 focus-within:border-brand">
        <Search className="size-4 text-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Search a name")} className="w-full bg-transparent text-sm outline-none" aria-label={t("Search a name")} />
      </div>

      {!data ? (
        <Loading />
      ) : (
        <ul className="card divide-y divide-line overflow-hidden p-0">
          {list.map((p) => (
            <li key={p.name}>
              <button onClick={() => setOpen(p.name)} className="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-surface-2">
                <Avatar name={p.name} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold">{p.name}</span>
                  <span className="block truncate text-xs text-muted">
                    {p.overdue > 0 ? t("{d} days late", { d: p.oldest_days_late }) : p.next_due ? t("Due {day}", { day: p.next_due }) : p.last_payment ? t("Last paid {day}", { day: p.last_payment }) : t("All settled")}
                    {p.promise && ` · ${p.promise.broken ? t("promise broken") : t("promised {day}", { day: p.promise.day })}`}
                  </span>
                </span>
                <span className="text-right">
                  <span className={cx("num block font-bold", p.overdue > 0 ? "text-bad" : p.outstanding > 0 ? "text-ink" : "text-muted")}>{p.outstanding > 0 ? inr(p.outstanding) : "—"}</span>
                  {p.reliability.on_time_pct != null && <Pill tone={p.reliability.tone} className="mt-0.5">{t(p.reliability.label)}</Pill>}
                </span>
              </button>
            </li>
          ))}
          {list.length === 0 && <li className="p-6 text-center text-sm text-muted">{t("No one here yet.")}</li>}
        </ul>
      )}
      <PersonSheet name={open} onClose={() => setOpen(null)} onRemind={(n) => { setOpen(null); setRemind(n); }} />
      <ReminderSheet customer={remind} onClose={() => setRemind(null)} />
    </div>
  );
}

function PersonSheet({ name, onClose, onRemind }: { name: string | null; onClose: () => void; onRemind: (n: string) => void }) {
  const { t } = useT();
  const qe = useQuickEntry();
  const { data } = useApi<Detail>(name ? `/api/person?name=${encodeURIComponent(name)}` : null);
  const [shown, setShown] = useState<Detail | null>(null);
  useEffect(() => {
    if (data && data.name === name) setShown(data);
  }, [data, name]);
  const d = shown && shown.name === name ? shown : null;
  const cust = d?.kind !== "supplier";
  return (
    <Sheet open={!!name} onClose={onClose} title={name ?? ""}>
      {!d ? (
        <Loading />
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-2xl bg-surface-2 p-4">
            <div>
              <p className="text-sm text-ink-2">{cust ? t("Owes you") : t("You owe")}</p>
              <p className={cx("num text-3xl font-bold", d.overdue > 0 && "text-bad")}>{inr(d.outstanding)}</p>
              {d.overdue > 0 && <p className="text-sm text-bad">{t("{amt} is overdue", { amt: inr(d.overdue) })}</p>}
            </div>
            <Avatar name={d.name} size="lg" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            {cust ? (
              <>
                <Button onClick={() => { onClose(); qe.open({ kind: "payment_in", party: d.name }); }}><ArrowDownLeft className="size-4" /> {t("Paisa aaya")}</Button>
                <Button variant="secondary" onClick={() => { onClose(); qe.open({ kind: "credit_sale", party: d.name }); }}><HandCoins className="size-4" /> {t("Udhaar diya")}</Button>
                {d.overdue > 0 && (
                  <Button variant="secondary" className="col-span-2" onClick={() => onRemind(d.name)}><MessageCircle className="size-4" /> {t("Remind on WhatsApp")}</Button>
                )}
              </>
            ) : (
              <>
                <Button onClick={() => { onClose(); qe.open({ kind: "payment_out", party: d.name }); }}><ArrowUpRight className="size-4" /> {t("Paid them")}</Button>
                <Button variant="secondary" onClick={() => { onClose(); qe.open({ kind: "bill", party: d.name }); }}><ReceiptText className="size-4" /> {t("New bill")}</Button>
              </>
            )}
          </div>
          <div>
            <p className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">{t("History")}</p>
            <ul className="divide-y divide-line rounded-2xl border border-line">
              {d.timeline.slice(0, 30).map((x) => {
                const money_in = x.type === "payment_in";
                const paid = x.type.startsWith("payment");
                return (
                  <li key={x.id + x.day} className="flex items-center gap-3 px-3 py-2.5 text-sm">
                    <span className="w-16 shrink-0 text-xs text-muted">{x.day}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{x.title}</span>
                      {!paid && (
                        <span className={cx("text-xs", x.late_days > 0 ? "text-bad" : x.status === "paid" ? "text-good" : "text-muted")}>
                          {x.status === "paid" ? t("Paid") : x.late_days > 0 ? t("{d} days late", { d: x.late_days }) : t("Due {day}", { day: x.due ?? "" })} · {x.id}
                        </span>
                      )}
                    </span>
                    <span className={cx("num shrink-0 font-semibold", paid ? (money_in ? "text-good" : "text-ink") : "text-ink-2")}>
                      {paid ? (money_in ? "+" : "−") : ""}{inr(x.amount)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </Sheet>
  );
}
