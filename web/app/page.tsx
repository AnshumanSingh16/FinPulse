"use client";

import {
  AlertTriangle, ArrowRight, Check, CheckCheck, CircleCheck, CircleDollarSign, Clock, HandCoins, Landmark, MessageCircle, PauseCircle, Pencil, ShieldCheck,
  Sparkles, Undo2, X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useContext, useEffect, useState } from "react";
import { CashChart } from "@/components/cash-chart";
import { DataVersion } from "@/components/data-version";
import { EvidenceButton } from "@/components/evidence";
import { useToast } from "@/components/fx";
import { Button, Card, cx, ErrorNote, Loading, MoneyInput, Pill, Sheet } from "@/components/ui";
import { get, post } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Evidence } from "@/lib/types";

interface Summary {
  lowest: number;
  lowest_date: string;
  end: number;
  below_safety_from: string | null;
  runs_out: string | null;
  safe: boolean;
  free_cash_today: number;
}
interface Move {
  id: string;
  kind: "collect" | "defer" | "pause" | "reserve";
  agent: string;
  party: string;
  amount: number;
  monthly?: number;
  items: string[];
  days_late?: number;
  from_date?: string;
  to_date?: string;
  due?: string;
  impact: number;
  new_lowest: number;
  suggested: boolean;
  state: "open" | "approved" | "done";
}
interface Plan {
  status: string;
  message?: string;
  business: string;
  is_demo: boolean;
  today: number;
  safety: number;
  default_safety: number | null;
  baseline: Summary;
  with_suggested: Summary;
  with_approved: Summary;
  plan_basis: "approved" | "suggested";
  series: { baseline: { date: string; balance: number }[]; plan: { date: string; balance: number }[] };
  causes: { date: string; label: string; amount: number; category: string }[];
  at_risk: { party: string; amount: number; next_due: string; oldest_late_days: number }[];
  moves: Move[];
  evidence: Evidence;
}

const AGENT: Record<Move["kind"], { label: string; I: React.ElementType; grad: string }> = {
  collect: { label: "Collections agent", I: HandCoins, grad: "grad-mint" },
  defer: { label: "Payables agent", I: Clock, grad: "grad-ocean" },
  pause: { label: "Spending agent", I: PauseCircle, grad: "grad-sunset" },
  reserve: { label: "Tax agent", I: Landmark, grad: "grad-violet" },
};

function day(iso: string | null | undefined, lang = "en") {
  if (!iso) return "";
  return new Date(iso + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short" });
}

/** The move's title, written here so amounts use Indian grouping and the owner's language. */
function moveTitle(m: Move, t: (s: string, v?: Record<string, string | number>) => string, lang: string) {
  if (m.kind === "collect") return t("Collect {amt} from {who}", { amt: short(m.amount), who: m.party });
  if (m.kind === "defer") return t("Ask {who} to move {bill} to {date}", { who: m.party, bill: m.items[0], date: day(m.to_date, lang) });
  if (m.kind === "pause") return m.party === "Owner Drawings" ? t("Pause owner drawings for 60 days") : t("Pause marketing spend for 60 days");
  return t("Set aside {amt} for GST due {date}", { amt: short(m.amount), date: day(m.due, lang) });
}
function moveDetail(m: Move, t: (s: string, v?: Record<string, string | number>) => string, lang: string) {
  if (m.kind === "collect") return t("{n} invoice(s) overdue, oldest {d} days. Assumes they pay within a week of your reminder.", { n: m.items.length, d: m.days_late ?? 0 });
  if (m.kind === "defer") return t("{amt} due {from}. Assumes they agree to 3 more weeks.", { amt: inr(m.amount), from: day(m.from_date, lang) });
  if (m.kind === "pause") return t("About {amt} a month on average; pausing keeps {kept} in the bank.", { amt: short(m.monthly ?? 0), kept: short(m.amount) });
  return t("Your typical monthly GST payment, kept aside so it isn't spent by mistake.");
}

export default function CashPage() {
  const { t, lang } = useT();
  const { version } = useContext(DataVersion);
  const router = useRouter();
  const [p, setP] = useState<Plan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [safetyOpen, setSafetyOpen] = useState(false);
  const load = useCallback(() => get<Plan>("/api/autopilot").then((x) => { setP(x); setErr(null); }).catch((e) => setErr(String(e))), []);
  useEffect(() => {
    load();
  }, [load, version]);

  if (err) return <ErrorNote message={err} retry={load} />;
  if (!p) return <Loading label={t("Looking 90 days ahead…")} />;
  if (p.status !== "ok") return <NoForecast p={p} />;

  const b = p.baseline;
  const tone = b.runs_out ? "bad" : b.below_safety_from ? "caution" : "good";
  const grad = tone === "bad" ? "grad-hero-bad" : tone === "caution" ? "grad-hero-caution" : "grad-hero";
  const headline = b.runs_out
    ? t("You'll run out of cash on {date}", { date: day(b.runs_out, lang) })
    : b.below_safety_from
      ? t("Cash drops below your safety level on {date}", { date: day(b.below_safety_from, lang) })
      : t("You're covered for the next 90 days");
  const suggested = p.moves.filter((m) => m.suggested && m.kind !== "reserve");
  const result = p.plan_basis === "approved" ? p.with_approved : p.with_suggested;

  return (
    <div className="space-y-5">
      <section className={cx("rise overflow-hidden rounded-[1.75rem] p-5 shadow-xl shadow-black/10 sm:p-7", grad)}>
        <p className="text-sm font-semibold text-white/80">{t("Cash autopilot · next 90 days")}</p>
        <h1 className="mt-1 text-2xl leading-tight font-bold sm:text-3xl">{headline}</h1>
        <div className="mt-4 grid grid-cols-3 gap-2 sm:gap-3">
          <Stat k={t("In the bank today")} v={short(p.today)} />
          <Stat k={t("Lowest point")} v={short(b.lowest)} sub={day(b.lowest_date, lang)} />
          <Stat k={t("Your safety level")} v={short(p.safety)} sub={<button onClick={() => setSafetyOpen(true)} className="inline-flex items-center gap-1 underline underline-offset-2"><Pencil className="size-3" /> {t("change")}</button>} />
        </div>
        {p.causes.length > 0 && !b.safe && (
          <p className="mt-4 text-sm text-white/85">
            {t("Why")}: {p.causes.map((c) => `${c.label.replace(/^(SCH|BILL|INV)-\d+ to /, "")} ${short(c.amount)} (${day(c.date, lang)})`).join(" · ")}
          </p>
        )}
        {p.at_risk.length > 0 && (
          <p className="glass mt-3 flex items-start gap-2 rounded-2xl px-3 py-2 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{p.at_risk.map((r) => t("Not counting {amt} due from {who} on {date} — they're already {d} days late on older invoices.", { amt: short(r.amount), who: r.party, date: day(r.next_due, lang), d: r.oldest_late_days })).join(" ")}</span>
          </p>
        )}
      </section>

      <Card>
        <CashChart baseline={p.series.baseline} plan={p.series.plan} safety={p.safety} planLabel={p.plan_basis === "approved" ? "With your approved moves" : "With the agents' plan"} />
      </Card>

      <AgentsPlan p={p} result={result} suggested={suggested} onChange={load} />

      <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(`/ask/?q=${encodeURIComponent(q.trim())}`); }} className="card flex items-center gap-2 rounded-3xl p-1.5 pl-4">
        <Sparkles className="size-5 shrink-0 text-brand" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Ask about your cash — “Can I afford a ₹2 lakh machine?”")} className="h-10 w-full bg-transparent outline-none placeholder:text-muted" aria-label={t("Ask about your cash")} />
        <Button type="submit" disabled={!q.trim()}><ArrowRight className="size-4" /></Button>
      </form>
      <div className="flex justify-center">
        <EvidenceButton evidence={p.evidence} label={t("How is this worked out?")} />
      </div>
      <SafetySheet open={safetyOpen} onClose={() => setSafetyOpen(false)} current={p.safety} suggested={p.default_safety} onSaved={load} />
    </div>
  );
}

function Stat({ k, v, sub }: { k: string; v: string; sub?: React.ReactNode }) {
  return (
    <div className="glass min-w-0 rounded-2xl px-2.5 py-2 sm:px-3">
      <p className="text-[0.65rem] leading-tight font-semibold tracking-wide text-white/75 uppercase sm:text-[0.7rem]">{k}</p>
      <p className="num mt-0.5 text-base font-bold whitespace-nowrap sm:text-xl">{v}</p>
      {sub && <p className="truncate text-xs text-white/80">{sub}</p>}
    </div>
  );
}

function AgentsPlan({ p, result, suggested, onChange }: { p: Plan; result: Summary; suggested: Move[]; onChange: () => void }) {
  const { t, lang } = useT();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const open = p.moves.filter((m) => m.state === "open" && m.suggested);
  const approveAll = async () => {
    setBusy(true);
    try {
      const r = await post<{ approved: string[] }>("/api/autopilot/approve-suggested", {});
      toast.show({ text: t("Approved {n} moves", { n: r.approved.length }), tone: "good" });
      onChange();
    } finally {
      setBusy(false);
    }
  };
  const main = p.moves.filter((m) => m.suggested);
  const more = p.moves.filter((m) => !m.suggested);
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold tracking-tight">{p.baseline.safe ? t("Your agents' suggestions") : t("Your agents' plan")}</h2>
          <p className="text-sm text-ink-2">
            {p.baseline.safe
              ? t("Cash stays above your safety level. These would still help.")
              : suggested.length
                ? t("{n} moves. With them, the lowest point is {amt} on {date}.", { n: suggested.length, amt: short(result.lowest), date: day(result.lowest_date, lang) })
                : t("No move available lifts the low point enough — ask FinPilot for other options.")}
            {!p.baseline.safe && (result.safe ? <span className="ml-1 font-semibold text-good">✓ {t("Above your safety level")}</span> : <span className="ml-1 font-semibold text-bad">{t("Still below safety")}</span>)}
          </p>
        </div>
        {open.length > 1 && (
          <Button onClick={approveAll} disabled={busy}>
            <CheckCheck className="size-4" /> {t("Approve plan ({n})", { n: open.length })}
          </Button>
        )}
      </div>
      <ul className="space-y-2.5">
        {main.map((m) => <MoveCard key={m.id} m={m} onChange={onChange} />)}
      </ul>
      {more.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer list-none text-sm font-semibold text-brand">{t("More options ({n})", { n: more.length })}</summary>
          <ul className="mt-2.5 space-y-2.5">{more.map((m) => <MoveCard key={m.id} m={m} onChange={onChange} />)}</ul>
        </details>
      )}
      {p.moves.length === 0 && <Card className="text-sm text-ink-2">{t("Nothing to do — no overdue money, nothing worth moving.")}</Card>}
    </section>
  );
}

function MoveCard({ m, onChange }: { m: Move; onChange: () => void }) {
  const { t, lang } = useT();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const A = AGENT[m.kind];
  const decide = async (decision: "approve" | "dismiss" | "undo" | "done") => {
    setBusy(true);
    try {
      const r = await post<{ next?: string; whatsapp?: string; text?: string }>(`/api/autopilot/moves/${encodeURIComponent(m.id)}`, { decision });
      if (decision === "approve" && r.whatsapp) {
        window.open(r.whatsapp, "_blank", "noopener");
        toast.show({ text: m.kind === "collect" ? t("Reminder opened in WhatsApp — press send") : t("Message to the supplier opened in WhatsApp"), tone: "good" });
      }
      onChange();
    } catch (e) {
      toast.show({ text: e instanceof Error ? e.message : String(e), tone: "bad" });
    } finally {
      setBusy(false);
    }
  };
  const approved = m.state === "approved" || m.state === "done";
  return (
    <li className={cx("card flex flex-wrap items-start gap-3 p-4", approved && "ring-2 ring-good/30")}>
      <span className={cx("grid size-10 shrink-0 place-items-center rounded-2xl", A.grad)}>
        <A.I className="size-5" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold tracking-wide text-muted uppercase">{t(A.label)}</p>
        <p className="font-semibold text-ink">{moveTitle(m, t, lang)}</p>
        <p className="text-sm text-ink-2">{moveDetail(m, t, lang)}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {m.impact > 0 ? (
            <Pill tone="good"><CircleDollarSign className="size-3.5" /> {t("+{amt} to your lowest point", { amt: short(m.impact) })}</Pill>
          ) : m.kind === "reserve" ? (
            <Pill tone="info"><ShieldCheck className="size-3.5" /> {t("Free cash today: {amt} less", { amt: short(m.amount) })}</Pill>
          ) : (
            <Pill>{t("Doesn't change the low point — still worth doing")}</Pill>
          )}
          {approved && <Pill tone="good"><Check className="size-3.5" /> {m.state === "done" ? t("Done") : t("Approved")}</Pill>}
        </div>
      </div>
      <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:flex-col sm:items-end">
        {!approved ? (
          <>
            <Button size="sm" onClick={() => decide("approve")} disabled={busy}>
              {m.kind === "collect" || m.kind === "defer" ? <MessageCircle className="size-4" /> : <Check className="size-4" />}
              {m.kind === "collect" ? t("Approve & remind") : m.kind === "defer" ? t("Approve & ask") : t("Approve")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => decide("dismiss")} disabled={busy}><X className="size-4" /> {t("Not now")}</Button>
          </>
        ) : (
          <>
            {m.kind === "defer" && m.state === "approved" && (
              <Button size="sm" onClick={() => decide("done")} disabled={busy}><CircleCheck className="size-4" /> {t("Supplier agreed")}</Button>
            )}
            {m.kind === "collect" && (
              <Link href={`/khata/?side=customers`}><Button size="sm" variant="secondary"><HandCoins className="size-4" /> {t("Record payment")}</Button></Link>
            )}
            <Button size="sm" variant="ghost" onClick={() => decide("undo")} disabled={busy}><Undo2 className="size-4" /> {t("Undo")}</Button>
          </>
        )}
      </div>
    </li>
  );
}

function SafetySheet({ open, onClose, current, suggested, onSaved }: { open: boolean; onClose: () => void; current: number; suggested: number | null; onSaved: () => void }) {
  const { t } = useT();
  const [v, setV] = useState(String(Math.round(current)));
  useEffect(() => setV(String(Math.round(current))), [current, open]);
  const save = async (amount: string | null) => {
    await post("/api/autopilot/safety", { amount });
    onSaved();
    onClose();
  };
  return (
    <Sheet open={open} onClose={onClose} title={t("Your safety level")}>
      <p className="mb-3 text-sm text-ink-2">{t("The least you want in the bank at any time. The autopilot warns you before cash goes below it and plans moves to stay above it.")}</p>
      <MoneyInput value={v} onChange={setV} autoFocus />
      {suggested != null && <p className="mt-2 text-xs text-muted">{t("Suggested: {amt} — about two weeks of your running costs.", { amt: inr(suggested) })}</p>}
      <div className="mt-4 flex gap-2">
        <Button onClick={() => save(v)} disabled={!v}>{t("Save")}</Button>
        <Button variant="ghost" onClick={() => save(null)}>{t("Use suggested")}</Button>
      </div>
    </Sheet>
  );
}

function NoForecast({ p }: { p: Plan }) {
  const { t } = useT();
  return (
    <Card className="space-y-3">
      <h1 className="text-2xl">{t("FinPilot needs your bank balance to look ahead")}</h1>
      <p className="text-ink-2">{p.message}</p>
      <Link href="/data/"><Button>{t("Add your balance or bank statement")}</Button></Link>
    </Card>
  );
}
