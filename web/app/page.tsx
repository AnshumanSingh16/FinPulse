"use client";

import {
  AlertTriangle, ArrowRight, Banknote, Check, CheckCheck, ChevronDown, CircleCheck, Clock, Copy, HandCoins, Landmark, MessageCircle, PauseCircle, Pencil,
  Percent, ShieldCheck, ShoppingBag, Sparkles, TrendingDown, TrendingUp, Undo2, Wand2, X,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useContext, useEffect, useState } from "react";
import { CashChart } from "@/components/cash-chart";
import { CrewSheet } from "@/components/crew";
import { DataVersion } from "@/components/data-version";
import { ActivityFeed, FastForwardCard, TrackRecordCard, WatchCard, type Activity, type PlanB, type Watch } from "@/components/live";
import { EvidenceButton } from "@/components/evidence";
import { CountUp, useToast } from "@/components/fx";
import { Button, Card, cx, ErrorNote, Loading, MoneyInput, Pill, Sheet } from "@/components/ui";
import { get, post } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Evidence } from "@/lib/types";

type T = (s: string, v?: Record<string, string | number>) => string;

interface Summary {
  lowest: number;
  lowest_date: string;
  end: number;
  below_safety_from: string | null;
  runs_out: string | null;
  safe: boolean;
  free_cash_today: number;
  spendable_today: number;
  days_to_trouble: number | null;
}
interface Odds {
  sims: number;
  p_safe: number;
  p_short: number;
  bad_case_lowest: number;
}
interface Move {
  id: string;
  kind: "collect" | "defer" | "pause" | "reserve" | "borrow" | "discount";
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
  suggested: boolean;
  backup?: boolean;
  odds_with_plan?: number;
  interest_if_used?: number;
  invoice?: number;
  cost?: number;
  state: "open" | "approved" | "done";
}
interface Week {
  start: string;
  end: string;
  closing: number;
}
interface Plan {
  status: string;
  message?: string;
  as_of: string;
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
  causes: { date: string; label: string; amount: number }[];
  at_risk: { party: string; amount: number; next_due: string; oldest_late_days: number }[];
  moves: Move[];
  odds: { baseline: Odds; suggested: Odds; approved: Odds | null; target: number };
  weekly: Week[];
  changes: { tone: "good" | "bad" | "caution"; text: string }[];
  changes_since: string | null;
  plan_b: PlanB[];
  watching: Watch[];
  activity: Activity[];
  clock: { date: string; days_moved: number };
  evidence: Evidence;
}

const AGENT: Record<Move["kind"], { label: string; I: React.ElementType; grad: string }> = {
  collect: { label: "Collections agent", I: HandCoins, grad: "grad-mint" },
  defer: { label: "Payables agent", I: Clock, grad: "grad-ocean" },
  pause: { label: "Spending agent", I: PauseCircle, grad: "grad-sunset" },
  reserve: { label: "Tax agent", I: Landmark, grad: "grad-violet" },
  borrow: { label: "Financing agent", I: Banknote, grad: "grad-sunset" },
  discount: { label: "Deals agent", I: Percent, grad: "grad-ocean" },
};

function day(iso: string | null | undefined, lang = "en") {
  if (!iso) return "";
  return new Date(iso + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short" });
}
const pct = (x: number) => `${Math.round(x * 100)}%`;

function moveTitle(m: Move, t: T, lang: string) {
  if (m.kind === "collect") return t("Collect {amt} from {who}", { amt: short(m.amount), who: m.party });
  if (m.kind === "defer") return t("Ask {who} to move {bill} to {date}", { who: m.party, bill: m.items[0], date: day(m.to_date, lang) });
  if (m.kind === "pause") return m.party === "Owner Drawings" ? t("Pause owner drawings for 60 days") : t("Pause marketing spend for 60 days");
  if (m.kind === "borrow") return t("Keep a {amt} overdraft ready", { amt: short(m.amount) });
  if (m.kind === "discount") return t("Offer {who} 2% off to pay {amt} by {date}", { who: m.party, amt: short(m.invoice ?? 0), date: day(m.to_date, lang) });
  return t("Set aside {amt} for GST due {date}", { amt: short(m.amount), date: day(m.due, lang) });
}
function moveDetail(m: Move, t: T, lang: string) {
  if (m.kind === "collect") return t("{n} invoice(s) overdue, oldest {d} days. Assumes they pay within a week of your reminder.", { n: m.items.length, d: m.days_late ?? 0 });
  if (m.kind === "defer") return t("{amt} due {from}. Assumes they agree to 3 more weeks.", { amt: inr(m.amount), from: day(m.from_date, lang) });
  if (m.kind === "pause") return t("About {amt} a month on average; pausing keeps {kept} in the bank.", { amt: short(m.monthly ?? 0), kept: short(m.amount) });
  if (m.kind === "discount") return t("Due {date}. Costs {amt}; assumes they accept (7 in 10 do in the simulation).", { date: day(m.from_date, lang), amt: short(m.cost ?? 0) });
  if (m.kind === "borrow") return t("Only if the plan falls short. Using all of it for 90 days would cost about {amt} in interest (at about 14% a year).", { amt: short(m.interest_if_used ?? 0) });
  return t("Your typical monthly GST payment, kept aside so it isn't spent by mistake.");
}

export default function TodayPage() {
  const { t, lang } = useT();
  const { version } = useContext(DataVersion);
  const [p, setP] = useState<Plan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [crew, setCrew] = useState(false);
  const [cushion, setCushion] = useState(false);
  const load = useCallback(() => get<Plan>("/api/autopilot").then((x) => { setP(x); setErr(null); }).catch((e) => setErr(String(e))), []);
  useEffect(() => {
    load();
  }, [load, version]);

  if (err) return <ErrorNote message={err} retry={load} />;
  if (!p) return <Loading label={t("Looking 90 days ahead…")} />;
  if (p.status !== "ok") return <NoForecast p={p} />;

  const b = p.baseline;
  const anyApproved = p.moves.some((m) => m.state !== "open");
  const needsFix = !b.safe || p.odds.baseline.p_safe < p.odds.target;

  return (
    <div className="space-y-4">
      <Hero p={p} onFix={() => setCrew(true)} onCushion={() => setCushion(true)} needsFix={needsFix} anyApproved={anyApproved} />
      <WeekStrip p={p} />
      {p.changes.length > 0 && <Changes p={p} />}
      <PlanSection p={p} onChange={load} />
      <WatchCard planB={p.plan_b ?? []} watching={p.watching ?? []} moves={p.moves} />
      <ActivityFeed items={p.activity ?? []} onChange={load} />
      {p.is_demo && <FastForwardCard clock={p.clock} onDone={load} />}
      <AffordCard p={p} />
      <TrackRecordCard />
      <Details p={p} onCushion={() => setCushion(true)} />
      <AskBox />
      <CrewSheet open={crew} onClose={() => setCrew(false)} onApproved={load} canApprove={p.moves.some((m) => m.suggested && m.state === "open" && m.kind !== "reserve")} />
      <CushionSheet open={cushion} onClose={() => setCushion(false)} current={p.safety} suggested={p.default_safety} onSaved={load} />
    </div>
  );
}

function Hero({ p, onFix, onCushion, needsFix, anyApproved }: { p: Plan; onFix: () => void; onCushion: () => void; needsFix: boolean; anyApproved: boolean }) {
  const { t, lang } = useT();
  const base = p.baseline;
  const withPlan = anyApproved;
  const b = withPlan ? p.with_approved : base;
  const now = withPlan && p.odds.approved ? p.odds.approved : p.odds.baseline;
  const sure = now.p_safe >= p.odds.target;
  const tone = b.runs_out ? "bad" : !b.safe || !sure ? "caution" : "good";
  const grad = tone === "bad" ? "grad-hero-bad" : tone === "caution" ? "grad-hero-caution" : "grad-hero";
  const unsafeIn = Math.round((1 - now.p_safe) * 100);
  let big: string, sub: string;
  if (b.runs_out) {
    big = t("Money runs out in {n} days", { n: b.days_to_trouble ?? 0 });
    sub = t("on {date}, if nothing changes", { date: day(b.runs_out, lang) });
  } else if (!b.safe) {
    big = t("Money gets tight in {n} days", { n: b.days_to_trouble ?? 0 });
    sub = t("on {date} you dip below your cushion of {amt}", { date: day(b.below_safety_from, lang), amt: short(p.safety) });
  } else if (!sure) {
    big = withPlan ? t("Your plan works — if customers pay") : t("Safe, but not certain");
    sub = withPlan && !base.safe
      ? t("Without it, {what} on {date}. Add the backup to be sure.", { what: base.runs_out ? t("money would run out") : t("you'd dip below your cushion"), date: day(base.runs_out ?? base.below_safety_from, lang) })
      : t("In {n} of 100 possible futures, cash dips below your cushion.", { n: unsafeIn });
  } else if (withPlan && !base.safe) {
    big = t("Your plan keeps you safe");
    sub = t("Without it, {what} on {date}.", { what: base.runs_out ? t("money would run out") : t("you'd dip below your cushion"), date: day(base.runs_out ?? base.below_safety_from, lang) });
  } else {
    big = t("You're all set");
    sub = t("for the next 90 days — you stay above your cushion of {amt}", { amt: short(p.safety) });
  }
  return (
    <section className={cx("rise overflow-hidden rounded-[1.75rem] p-5 shadow-xl shadow-black/10 sm:p-7", grad)}>
      <p className="text-sm font-semibold text-white/80">{withPlan ? t("With the moves you approved") : t("If nothing changes")} · {t("next 90 days")}</p>
      <h1 className="mt-1 text-3xl leading-tight font-bold sm:text-4xl">{big}</h1>
      <p className="mt-1 text-white/90">{sub}</p>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <div className="glass rounded-2xl p-3">
          <p className="text-xs font-semibold tracking-wide text-white/80 uppercase">{t("Safe to spend today")}</p>
          <p className="num text-3xl font-bold"><CountUp value={b.spendable_today} format={short} /></p>
          <p className="text-xs text-white/80">
            {t("of {cash} in the bank", { cash: short(p.today) })} ·{" "}
            <button onClick={onCushion} className="inline-flex items-center gap-1 underline underline-offset-2"><Pencil className="size-3" /> {t("cushion {amt}", { amt: short(p.safety) })}</button>
          </p>
        </div>
        <div className="glass rounded-2xl p-3">
          <p className="text-xs font-semibold tracking-wide text-white/80 uppercase">{t("Chance you stay safe")}</p>
          <p className="num text-3xl font-bold">{pct(now.p_safe)}</p>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/25" aria-hidden>
            <div className="h-full rounded-full bg-white" style={{ width: `${Math.max(2, now.p_safe * 100)}%` }} />
          </div>
          <p className="mt-1 text-xs text-white/80">{t("in {n} possible futures, based on how your customers really pay", { n: now.sims.toLocaleString("en-IN") })}</p>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button onClick={onFix} className="inline-flex h-12 items-center gap-2 rounded-full bg-white px-5 font-semibold text-ink shadow-lg transition hover:scale-[1.02] active:scale-95">
          <Wand2 className="size-5 text-brand" /> {needsFix && !anyApproved ? t("Fix it for me") : t("Ask my agents to check")}
        </button>
        {needsFix && !anyApproved && <span className="text-sm text-white/85">{t("Your agents look for a way out — you approve.")}</span>}
      </div>
    </section>
  );
}

function WeekStrip({ p }: { p: Plan }) {
  const { t, lang } = useT();
  if (!p.weekly?.length) return null;
  const max = Math.max(...p.weekly.map((w) => w.closing), p.safety * 1.5, 1);
  return (
    <Link href="/timeline/" className="card block p-4 transition hover:shadow-md">
      <div className="mb-3 flex items-center justify-between">
        <p className="font-semibold">{t("Your next 13 weeks")}</p>
        <span className="flex items-center gap-1 text-sm font-semibold text-brand">{t("Week by week")} <ArrowRight className="size-4" /></span>
      </div>
      <div className="flex h-20 items-end gap-1" role="img" aria-label={t("Bank balance at the end of each of the next 13 weeks")}>
        {p.weekly.map((w) => {
          const tone = w.closing < 0 ? "bg-bad" : w.closing < p.safety ? "bg-caution" : "bg-good";
          return (
            <div key={w.start} className="flex h-full flex-1 flex-col justify-end" title={`${day(w.end, lang)}: ${short(w.closing)}`}>
              <div className={cx("w-full rounded-t-md", tone)} style={{ height: `${Math.max(6, (Math.max(w.closing, 0) / max) * 100)}%` }} />
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between text-xs text-muted">
        <span>{day(p.weekly[0].end, lang)}</span>
        <span>{day(p.weekly[Math.floor(p.weekly.length / 2)].end, lang)}</span>
        <span>{day(p.weekly[p.weekly.length - 1].end, lang)}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-good" /> {t("Comfortable")}</span>
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-caution" /> {t("Below your cushion")}</span>
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-bad" /> {t("Out of money")}</span>
      </div>
    </Link>
  );
}

function Changes({ p }: { p: Plan }) {
  const { t } = useT();
  return (
    <Card className="space-y-2">
      <p className="font-semibold">{t("What changed")}</p>
      <ul className="space-y-1.5">
        {p.changes.map((c, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            {c.tone === "good" ? <TrendingUp className="mt-0.5 size-4 shrink-0 text-good" /> : <TrendingDown className={cx("mt-0.5 size-4 shrink-0", c.tone === "bad" ? "text-bad" : "text-caution")} />}
            <span>{c.text}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function PlanSection({ p, onChange }: { p: Plan; onChange: () => void }) {
  const { t } = useT();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const plan = p.moves.filter((m) => m.suggested);
  const backup = p.moves.find((m) => m.kind === "borrow");
  const more = p.moves.filter((m) => !m.suggested && m.kind !== "borrow");
  const open = plan.filter((m) => m.state === "open");
  const approvedAny = p.moves.some((m) => m.state !== "open");
  const o = p.odds;
  if (!plan.length && !backup && !more.length) return null;

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

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-bold tracking-tight">{approvedAny ? t("Your to-do list") : t("Your agents' plan")}</h2>
        <p className="text-sm text-ink-2">
          {p.baseline.safe && o.baseline.p_safe >= o.target
            ? t("You're safe. These keep it that way.")
            : approvedAny && o.approved
              ? t("With what you approved, your chance of staying safe is {p}.", { p: pct(o.approved.p_safe) })
              : t("Approve these and your chance of staying safe goes from {a} to {b}.", { a: pct(o.baseline.p_safe), b: pct(o.suggested.p_safe) })}
        </p>
      </div>
      <ul className="card divide-y divide-line overflow-hidden p-0">
        {plan.map((m) => <MoveRow key={m.id} m={m} onChange={onChange} />)}
      </ul>
      {open.length > 1 && (
        <Button className="w-full" size="lg" onClick={approveAll} disabled={busy}><CheckCheck className="size-5" /> {t("Approve all {n}", { n: open.length })}</Button>
      )}
      {backup && <BackupCard m={backup} p={p} onChange={onChange} />}
      {more.length > 0 && (
        <details className="group">
          <summary className="flex cursor-pointer list-none items-center gap-1 text-sm font-semibold text-brand">{t("More options ({n})", { n: more.length })} <ChevronDown className="size-4 transition group-open:rotate-180" /></summary>
          <ul className="card mt-2 divide-y divide-line overflow-hidden p-0">{more.map((m) => <MoveRow key={m.id} m={m} onChange={onChange} />)}</ul>
        </details>
      )}
    </section>
  );
}

function useDecide(m: Move, onChange: () => void) {
  const { t } = useT();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const decide = async (decision: "approve" | "dismiss" | "undo" | "done") => {
    setBusy(true);
    try {
      const r = await post<{ next?: string; whatsapp?: string; text?: string }>(`/api/autopilot/moves/${encodeURIComponent(m.id)}`, { decision });
      if (decision === "approve" && r.whatsapp) {
        window.open(r.whatsapp, "_blank", "noopener");
        toast.show({ text: m.kind === "collect" ? t("Reminder opened in WhatsApp — press send") : t("Message to the supplier opened in WhatsApp"), tone: "good" });
      } else if (decision === "approve" && r.next === "copy" && r.text) {
        try {
          await navigator.clipboard.writeText(r.text);
          toast.show({ text: t("Letter to your bank copied — paste it in an email"), tone: "good" });
        } catch {
          toast.show({ text: r.text });
        }
      }
      onChange();
    } catch (e) {
      toast.show({ text: e instanceof Error ? e.message : String(e), tone: "bad" });
    } finally {
      setBusy(false);
    }
  };
  return { busy, decide };
}

function MoveRow({ m, onChange }: { m: Move; onChange: () => void }) {
  const { t, lang } = useT();
  const [open, setOpen] = useState(false);
  const { busy, decide } = useDecide(m, onChange);
  const A = AGENT[m.kind];
  const approved = m.state !== "open";
  return (
    <li className={cx("p-3.5", approved && "bg-good-50/40")}>
      <div className="flex items-center gap-3">
        <button onClick={() => setOpen(!open)} className="flex min-w-0 flex-1 items-center gap-3 text-left" aria-expanded={open}>
          <span className={cx("grid size-10 shrink-0 place-items-center rounded-2xl", approved ? "bg-good text-white" : A.grad)}>
            {approved ? <Check className="size-5" /> : <A.I className="size-5" aria-hidden />}
          </span>
          <span className="min-w-0 flex-1">
            <span className={cx("block font-semibold", approved ? "text-ink-2" : "text-ink")}>{moveTitle(m, t, lang)}</span>
            <span className="block text-xs text-muted">
              {t(A.label)} · {m.impact > 0 ? t("+{amt} on your tightest day", { amt: short(m.impact) }) : m.kind === "reserve" ? t("keeps GST money safe") : t("good to do anyway")}
            </span>
          </span>
          <ChevronDown className={cx("size-4 shrink-0 text-muted transition", open && "rotate-180")} />
        </button>
        {!approved && !open && (
          <Button size="sm" onClick={() => decide("approve")} disabled={busy} aria-label={t("Approve")}>
            {m.kind === "collect" || m.kind === "defer" ? <MessageCircle className="size-4" /> : <Check className="size-4" />}
            <span className="hidden sm:inline">{m.kind === "collect" ? t("Approve & remind") : m.kind === "defer" ? t("Approve & ask") : t("Approve")}</span>
          </Button>
        )}
      </div>
      {open && (
        <div className="mt-2 pl-13">
          <p className="text-sm text-ink-2">{moveDetail(m, t, lang)}</p>
          <div className="mt-2.5 flex flex-wrap gap-2">
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
                {m.kind === "defer" && m.state === "approved" && <Button size="sm" onClick={() => decide("done")} disabled={busy}><CircleCheck className="size-4" /> {t("Supplier agreed")}</Button>}
                {m.kind === "collect" && <Link href="/khata/?side=customers"><Button size="sm" variant="secondary"><HandCoins className="size-4" /> {t("Record payment")}</Button></Link>}
                <Button size="sm" variant="ghost" onClick={() => decide("undo")} disabled={busy}><Undo2 className="size-4" /> {t("Undo")}</Button>
              </>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

function BackupCard({ m, p, onChange }: { m: Move; p: Plan; onChange: () => void }) {
  const { t } = useT();
  const { busy, decide } = useDecide(m, onChange);
  const approved = m.state !== "open";
  return (
    <div className="card border-l-4 border-caution p-4">
      <p className="flex items-center gap-2 text-xs font-semibold tracking-wide text-caution uppercase"><Banknote className="size-4" /> {t("Backup plan · Financing agent")}</p>
      <p className="mt-1 font-semibold">{t("Keep a {amt} overdraft ready", { amt: short(m.amount) })}</p>
      <p className="text-sm text-ink-2">
        {t("The plan depends on customers paying. If they don't, this covers you: your chance of staying safe rises from {a} to {b}.", { a: pct(p.odds.suggested.p_safe), b: pct(m.odds_with_plan ?? 0) })}{" "}
        {t("Costs nothing unless you use it — about {amt} if you use all of it for 90 days.", { amt: short(m.interest_if_used ?? 0) })}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {!approved ? (
          <>
            <Button size="sm" onClick={() => decide("approve")} disabled={busy}><Copy className="size-4" /> {t("Approve & copy bank letter")}</Button>
            <Button size="sm" variant="ghost" onClick={() => decide("dismiss")} disabled={busy}><X className="size-4" /> {t("Not now")}</Button>
          </>
        ) : (
          <>
            <Pill tone="good"><Check className="size-3.5" /> {t("Approved")}</Pill>
            <Button size="sm" variant="ghost" onClick={() => decide("undo")} disabled={busy}><Undo2 className="size-4" /> {t("Undo")}</Button>
          </>
        )}
      </div>
    </div>
  );
}

interface Afford {
  status: string;
  message?: string;
  verdict: "yes" | "yes_if" | "risky" | "not_now";
  amount: number;
  date: string;
  without_moves: Summary & { p_safe: number };
  with_plan: Summary & { p_safe: number; moves: { id: string; title: string; agent: string }[] };
  earliest_safe_date_without_moves: string | null;
}

function AffordCard({ p }: { p: Plan }) {
  const { t, lang } = useT();
  const [amount, setAmount] = useState("");
  const [when, setWhen] = useState(7);
  const [r, setR] = useState<Afford | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const whens = [{ d: 1, l: t("Tomorrow") }, { d: 7, l: t("Next week") }, { d: 30, l: t("In a month") }, { d: 60, l: t("In 2 months") }];
  const check = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!Number(amount)) return;
    setBusy(true);
    setErr(null);
    const date = new Date(new Date(p.as_of + "T00:00:00").getTime() + when * 86400000);
    const iso = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    try {
      setR(await post<Afford>("/api/autopilot/afford", { amount: Number(amount), date: iso }));
    } catch (x) {
      setErr(x instanceof Error ? x.message : String(x));
    } finally {
      setBusy(false);
    }
  };
  const V = r && r.status === "ok"
    ? {
        yes: { tone: "good", title: t("Yes — go ahead"), I: CircleCheck },
        yes_if: { tone: "good", title: t("Yes, if you approve your agents' plan"), I: CircleCheck },
        risky: { tone: "caution", title: t("Risky"), I: AlertTriangle },
        not_now: { tone: "bad", title: t("Not now"), I: X },
      }[r.verdict]
    : null;
  return (
    <section className="card p-4">
      <p className="flex items-center gap-2 font-semibold"><ShoppingBag className="size-5 text-brand" /> {t("Can I afford it?")}</p>
      <p className="text-sm text-ink-2">{t("A machine, a deposit, a big order — your agents check it against the next 90 days.")}</p>
      <form onSubmit={check} className="mt-3 space-y-2.5">
        <MoneyInput value={amount} onChange={(v) => { setAmount(v); setR(null); }} placeholder={t("Amount")} />
        <div className="flex flex-wrap gap-2">
          {whens.map((w) => (
            <button key={w.d} type="button" onClick={() => { setWhen(w.d); setR(null); }}
              className={cx("rounded-full border px-3 py-1.5 text-sm font-medium transition", when === w.d ? "border-brand bg-brand text-on-brand" : "border-line bg-surface text-ink-2")}>
              {w.l}
            </button>
          ))}
        </div>
        <Button type="submit" className="w-full" disabled={!Number(amount) || busy}>{busy ? t("Checking…") : t("Check")}</Button>
      </form>
      {err && <p className="mt-3 text-sm text-bad">{err}</p>}
      {r && r.status !== "ok" && <p className="mt-3 text-sm text-ink-2">{r.message}</p>}
      {r && V && (
        <div className={cx("rise mt-4 rounded-2xl p-4", V.tone === "good" ? "bg-good-50" : V.tone === "bad" ? "bg-bad-50" : "bg-caution-50")}>
          <p className={cx("flex items-center gap-2 text-lg font-bold", V.tone === "good" ? "text-good" : V.tone === "bad" ? "text-bad" : "text-caution")}><V.I className="size-5" /> {V.title}</p>
          <ul className="mt-1.5 space-y-1 text-sm text-ink">
            {r.verdict === "yes" && <li>{t("Your tightest day would be {amt} and you stay safe in {p} of futures.", { amt: short(r.without_moves.lowest), p: pct(r.without_moves.p_safe) })}</li>}
            {r.verdict !== "yes" && (
              <li>{r.without_moves.runs_out
                ? t("On its own, it would make you run out of cash on {date}.", { date: day(r.without_moves.runs_out, lang) })
                : t("On its own, your tightest day would be {amt} — below your cushion.", { amt: short(r.without_moves.lowest) })}</li>
            )}
            {r.verdict !== "yes" && r.with_plan.moves.length > 0 && (
              <li>{t("With your agents' plan ({moves}), you stay safe in {p} of futures.", { moves: r.with_plan.moves.length, p: pct(r.with_plan.p_safe) })}</li>
            )}
            {r.verdict !== "yes" && r.earliest_safe_date_without_moves && <li>{t("Without changing anything, the earliest safe day to pay is {date}.", { date: day(r.earliest_safe_date_without_moves, lang) })}</li>}
          </ul>
          <Link href={`/ask/?q=${encodeURIComponent(t("Can I afford {amt} on {date}? What are my options?", { amt: inr(r.amount), date: r.date }))}`} className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-brand">
            {t("Talk it through with FinPilot")} <ArrowRight className="size-4" />
          </Link>
        </div>
      )}
    </section>
  );
}

function Details({ p, onCushion }: { p: Plan; onCushion: () => void }) {
  const { t, lang } = useT();
  const b = p.baseline;
  return (
    <details className="group card p-0">
      <summary className="flex cursor-pointer list-none items-center justify-between p-4 font-semibold">
        {t("See the numbers")} <ChevronDown className="size-4 text-muted transition group-open:rotate-180" />
      </summary>
      <div className="space-y-4 border-t border-line p-4">
        <CashChart baseline={p.series.baseline} plan={p.series.plan} safety={p.safety} planLabel={p.plan_basis === "approved" ? "With your approved moves" : "With the agents' plan"} />
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div><dt className="text-muted">{t("In the bank today")}</dt><dd className="num font-semibold">{short(p.today)}</dd></div>
          <div><dt className="text-muted">{t("Tightest day")}</dt><dd className="num font-semibold">{short(b.lowest)} · {day(b.lowest_date, lang)}</dd></div>
          <div><dt className="text-muted">{t("Your cushion")}</dt><dd className="num font-semibold"><button onClick={onCushion} className="underline underline-offset-2">{short(p.safety)}</button></dd></div>
          <div><dt className="text-muted">{t("Bad case (1 in 10)")}</dt><dd className="num font-semibold">{short(p.odds.baseline.bad_case_lowest)}</dd></div>
        </dl>
        {p.causes.length > 0 && !b.safe && (
          <p className="text-sm text-ink-2">
            <span className="font-semibold text-ink">{t("Why")}:</span> {p.causes.map((c) => `${c.label.replace(/^(SCH|BILL|INV)-[\w-]+ (to|from) /, "")} ${short(c.amount)} (${day(c.date, lang)})`).join(" · ")}
          </p>
        )}
        {p.at_risk.length > 0 && (
          <p className="flex items-start gap-2 rounded-2xl bg-caution-50 p-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-caution" />
            <span>{p.at_risk.map((r) => t("Not counting {amt} due from {who} on {date} — they're already {d} days late on older invoices.", { amt: short(r.amount), who: r.party, date: day(r.next_due, lang), d: r.oldest_late_days })).join(" ")}</span>
          </p>
        )}
        <EvidenceButton evidence={p.evidence} label={t("How is this worked out?")} />
      </div>
    </details>
  );
}

function AskBox() {
  const { t } = useT();
  const router = useRouter();
  const [q, setQ] = useState("");
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(`/ask/?q=${encodeURIComponent(q.trim())}`); }} className="card flex items-center gap-2 rounded-3xl p-1.5 pl-4">
      <Sparkles className="size-5 shrink-0 text-brand" />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Ask anything — “Who pays me late?”")} className="h-10 w-full bg-transparent outline-none placeholder:text-muted" aria-label={t("Ask about your cash")} />
      <Button type="submit" disabled={!q.trim()} aria-label={t("Send")}><ArrowRight className="size-4" /></Button>
    </form>
  );
}

function CushionSheet({ open, onClose, current, suggested, onSaved }: { open: boolean; onClose: () => void; current: number; suggested: number | null; onSaved: () => void }) {
  const { t } = useT();
  const [v, setV] = useState(String(Math.round(current)));
  useEffect(() => {
    setV(String(Math.round(current)));
  }, [current, open]);
  const save = async (amount: string | null) => {
    await post("/api/autopilot/safety", { amount });
    onSaved();
    onClose();
  };
  return (
    <Sheet open={open} onClose={onClose} title={t("Your cushion")}>
      <p className="mb-3 text-sm text-ink-2">{t("The least you always want in the bank. Your agents warn you before cash goes below it and plan to keep you above it.")}</p>
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
      <ShieldCheck className="size-8 text-brand" />
      <h1 className="text-2xl">{t("FinPilot needs your bank balance to look ahead")}</h1>
      <p className="text-ink-2">{p.message}</p>
      <Link href="/data/"><Button>{t("Add your balance or bank statement")}</Button></Link>
    </Card>
  );
}
