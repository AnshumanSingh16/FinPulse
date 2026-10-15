"use client";

import { ArrowDownLeft, ArrowUpRight, CalendarCheck, ChevronRight, HandCoins, MessageCircle, Phone, ReceiptText, Search, Users } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useContext, useMemo, useState } from "react";
import { Avatar } from "@/components/cat";
import { DataVersion } from "@/components/data-version";
import { CountUp } from "@/components/fx";
import { useQuickEntry } from "@/components/quick-entry";
import { BulkReminders, ReminderSheet } from "@/components/reminder";
import { Button, Card, cx, ErrorNote, Loading, Pill, Segmented, Sheet } from "@/components/ui";
import { post, useApi } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Tone } from "@/lib/types";

interface Rel {
  label: string;
  tone: Tone;
  on_time_pct: number | null;
  avg_days_late: number | null;
  count: number;
}
interface PersonRow {
  name: string;
  outstanding: number;
  overdue: number;
  open_items: number;
  oldest_days_late: number;
  next_due: string | null;
  last_payment: string | null;
  reliability: Rel;
  phone: string | null;
  promise: { amount: number; date: string; day: string; broken: boolean } | null;
}
interface People {
  side: string;
  total: number;
  overdue: number;
  count: number;
  people: PersonRow[];
}
interface Person {
  name: string;
  kind: "customer" | "supplier";
  outstanding: number;
  overdue: number;
  total_business: number;
  reliability: Rel;
  phone: string | null;
  promise: { amount: number; date: string } | null;
  timeline: { id: string; date: string; day: string; type: string; title: string; amount: number; status: string; due: string | null; late_days: number }[];
}

export default function KhataPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Khata />
    </Suspense>
  );
}

function Khata() {
  const { t } = useT();
  const params = useSearchParams();
  const router = useRouter();
  const side = (params.get("side") as "customers" | "suppliers") || "customers";
  const name = params.get("name");
  const { data, error, loading, reload } = useApi<People>(`/api/people?side=${side}`);
  const [q, setQ] = useState("");
  const [bulk, setBulk] = useState(false);
  const qe = useQuickEntry();
  const list = useMemo(() => (data?.people ?? []).filter((p) => p.name.toLowerCase().includes(q.toLowerCase())), [data, q]);
  const cust = side === "customers";
  const go = (s: string) => router.replace(`/khata/?side=${s}`, { scroll: false });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl">{t("Khata")}</h1>
        <Segmented
          value={side}
          onChange={go}
          options={[
            { value: "customers", label: t("Customers") },
            { value: "suppliers", label: t("Suppliers") },
          ]}
        />
      </div>

      {error && <ErrorNote message={error} retry={reload} />}
      {loading && !data && <Loading />}
      {data && (
        <>
          <section className={cx("rise flex flex-wrap items-end justify-between gap-4 rounded-[1.75rem] p-6 shadow-xl", cust ? "grad-mint shadow-black/10" : "grad-sunset shadow-black/10")}>
            <div>
              <p className="text-sm text-white/85">{t(cust ? "You'll get" : "You'll give")}</p>
              <p className="display num text-5xl">
                <CountUp value={data.total} format={short} />
              </p>
              <p className="mt-1 text-sm text-white/85">
                {data.overdue > 0 ? `${short(data.overdue)} ${t("overdue")}` : t("Settled")} · {data.count} {t(cust ? "Customers" : "Suppliers").toLowerCase()}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {cust ? (
                <>
                  <Button className="" onClick={() => setBulk(true)}>
                    <MessageCircle className="size-4" /> {t("Remind all overdue")}
                  </Button>
                  <Button className="glass !text-ink" onClick={() => qe.open({ kind: "credit_sale" })}>
                    <HandCoins className="size-4" /> {t("Give udhaar")}
                  </Button>
                </>
              ) : (
                <>
                  <Button className="" onClick={() => qe.open({ kind: "payment_out" })}>
                    <ArrowUpRight className="size-4" /> {t("Pay bill")}
                  </Button>
                  <Button className="glass !text-ink" onClick={() => qe.open({ kind: "bill" })}>
                    <ReceiptText className="size-4" /> {t("Add bill")}
                  </Button>
                </>
              )}
            </div>
          </section>

          <div className="flex h-11 items-center gap-2 rounded-full border border-line bg-surface px-4 focus-within:border-brand sm:max-w-sm">
            <Search className="size-4 text-muted" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Search name")} className="w-full bg-transparent text-sm outline-none" aria-label={t("Search name")} />
          </div>

          {list.length === 0 ? (
            <Card className="flex flex-col items-center gap-2 py-10 text-center text-ink-2">
              <Users className="size-8 text-muted" />
              <p>{cust ? "No customers with udhaar yet. Tap “Give udhaar” when you sell on credit." : "No supplier bills yet. Add one when you buy on credit."}</p>
            </Card>
          ) : (
            <Card className="divide-y divide-line p-0">
              {list.map((p) => (
                <button key={p.name} onClick={() => router.push(`/khata/?side=${side}&name=${encodeURIComponent(p.name)}`, { scroll: false })} className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition hover:bg-canvas sm:px-5">
                  <Avatar name={p.name} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold">{p.name}</p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs">
                      {p.reliability.count >= 2 && <Pill tone={p.reliability.tone}>{t(p.reliability.label)}</Pill>}
                      {p.promise && (
                        <Pill tone={p.promise.broken ? "bad" : "info"}>
                          <CalendarCheck className="size-3" /> {p.promise.broken ? t("Promise broken") : t("Promised {amt} by {date}", { amt: short(p.promise.amount), date: p.promise.day })}
                        </Pill>
                      )}
                      {p.outstanding > 0 && p.overdue === 0 && p.next_due && <span className="text-muted">due {p.next_due}</span>}
                      {p.outstanding <= 0 && <span className="text-muted">{t("Settled")}</span>}
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={cx("num font-bold", p.overdue > 0 ? "text-bad" : p.outstanding > 0 ? "text-ink" : "text-muted")}>{inr(p.outstanding)}</p>
                    {p.overdue > 0 && <p className="text-xs text-bad">{p.oldest_days_late} {t("days late")}</p>}
                  </div>
                  <ChevronRight className="size-4 text-muted" />
                </button>
              ))}
            </Card>
          )}
        </>
      )}
      {bulk && <BulkReminders onClose={() => setBulk(false)} />}
      {name && <PersonSheet name={name} onClose={() => router.replace(`/khata/?side=${side}`, { scroll: false })} />}
    </div>
  );
}

function PersonSheet({ name, onClose }: { name: string; onClose: () => void }) {
  const { t } = useT();
  const { refresh } = useContext(DataVersion);
  const qe = useQuickEntry();
  const { data, reload } = useApi<Person>(`/api/person?name=${encodeURIComponent(name)}`);
  const [remind, setRemind] = useState(false);
  const [phone, setPhone] = useState<string | null>(null);
  const [pDate, setPDate] = useState("");
  const [pAmt, setPAmt] = useState("");
  const cust = data?.kind !== "supplier";

  const savePhone = async () => {
    if (phone != null) await post("/api/person/contact", { name, phone });
    reload();
  };
  const savePromise = async () => {
    await post("/api/person/promise", { name, date: pDate, amount: Number(pAmt) || data?.outstanding });
    setPDate("");
    setPAmt("");
    reload();
    refresh();
  };

  return (
    <Sheet open onClose={onClose} title={name} wide>
      {!data ? (
        <Loading />
      ) : (
        <div className="space-y-5">
          <div className={cx("flex items-center gap-4 rounded-3xl p-5", data.overdue > 0 ? "grad-hero-bad" : cust ? "grad-mint" : "grad-sunset")}>
            <Avatar name={name} size="lg" />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-white/80">{t(cust ? "You'll get" : "You'll give")}</p>
              <p className="display num text-4xl">{inr(data.outstanding)}</p>
              {data.overdue > 0 && <p className="text-sm text-white/90">{inr(data.overdue)} {t("overdue")}</p>}
            </div>
            {data.reliability.count >= 2 && (
              <div className="glass rounded-2xl px-3 py-2 text-right text-xs">
                <p className="font-semibold">{t(data.reliability.label)}</p>
                <p className="text-white/80">{data.reliability.on_time_pct}% on time</p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {cust ? (
              <>
                <Button onClick={() => qe.open({ kind: "payment_in", party: name, amount: data.overdue || data.outstanding || undefined })} className="!h-auto flex-col py-3">
                  <ArrowDownLeft className="size-5" /> {t("Record payment")}
                </Button>
                <Button variant="secondary" onClick={() => qe.open({ kind: "credit_sale", party: name })} className="!h-auto flex-col py-3">
                  <HandCoins className="size-5" /> {t("Give udhaar")}
                </Button>
                <Button variant="secondary" onClick={() => setRemind(true)} disabled={data.overdue <= 0} className="!h-auto flex-col py-3">
                  <MessageCircle className="size-5" /> {t("Send reminder")}
                </Button>
              </>
            ) : (
              <>
                <Button onClick={() => qe.open({ kind: "payment_out", party: name, amount: data.overdue || data.outstanding || undefined })} className="!h-auto flex-col py-3">
                  <ArrowUpRight className="size-5" /> {t("Pay bill")}
                </Button>
                <Button variant="secondary" onClick={() => qe.open({ kind: "bill", party: name })} className="!h-auto flex-col py-3">
                  <ReceiptText className="size-5" /> {t("Add bill")}
                </Button>
              </>
            )}
            {data.phone && (
              <a href={`tel:+${data.phone}`} className="contents">
                <Button variant="secondary" className="!h-auto flex-col py-3">
                  <Phone className="size-5" /> Call
                </Button>
              </a>
            )}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex items-center gap-2 rounded-2xl border border-line px-3">
              <Phone className="size-4 text-muted" />
              <input value={phone ?? data.phone ?? ""} onChange={(e) => setPhone(e.target.value)} onBlur={savePhone} placeholder={t("Phone (WhatsApp)")} inputMode="tel" className="h-11 flex-1 bg-transparent text-sm outline-none" />
            </label>
            {cust && data.outstanding > 0 && (
              <div className="flex items-center gap-2 rounded-2xl border border-line px-3">
                <CalendarCheck className="size-4 text-muted" />
                <input type="date" value={pDate} onChange={(e) => setPDate(e.target.value)} className="h-11 min-w-0 flex-1 bg-transparent text-sm outline-none" aria-label={t("Set promise date")} />
                <input value={pAmt} onChange={(e) => setPAmt(e.target.value.replace(/\D/g, ""))} placeholder="₹" className="h-11 w-20 bg-transparent text-sm outline-none" aria-label="Promised amount" />
                <Button size="sm" onClick={savePromise} disabled={!pDate}>
                  {t("Save")}
                </Button>
              </div>
            )}
          </div>
          {data.promise && (
            <p className="rounded-2xl bg-info-50 px-4 py-2.5 text-sm text-info">
              {t("Promised {amt} by {date}", { amt: inr(data.promise.amount), date: data.promise.date })}
            </p>
          )}

          <ol className="relative space-y-3 border-l-2 border-line pl-5">
            {data.timeline.map((e) => {
              const isPay = e.type.startsWith("payment");
              return (
                <li key={e.id} className="relative">
                  <span className={cx("absolute -left-[1.72rem] top-1.5 size-3 rounded-full ring-4 ring-surface", isPay ? "bg-good" : e.status === "pending" ? (e.late_days ? "bg-bad" : "bg-[#f59e0b]") : "bg-muted")} />
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{isPay ? (e.type === "payment_in" ? "Payment received" : "Payment made") : e.title}</p>
                      <p className="text-xs text-muted">
                        {e.day} · {e.id}
                        {!isPay && e.status === "pending" && e.due && ` · due ${e.due}`}
                        {e.late_days > 0 && <span className="text-bad"> · {e.late_days} {t("days late")}</span>}
                        {!isPay && e.status === "paid" && " · paid"}
                      </p>
                    </div>
                    <span className={cx("num shrink-0 font-semibold", isPay ? "text-good" : e.status === "pending" ? "text-ink" : "text-muted line-through decoration-1")}>{inr(e.amount)}</span>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      )}
      {remind && <ReminderSheet customer={name} onClose={() => setRemind(false)} />}
    </Sheet>
  );
}
