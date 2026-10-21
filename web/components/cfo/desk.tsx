"use client";

import {
  AlertTriangle, ArrowUp, Banknote, Check, CheckCheck, ChevronDown, CircleCheck, Clock, FastForward, HandCoins, Landmark, Loader2, Mic, PauseCircle, Percent,
  Sparkles, Volume2,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { AgentAnswer, LiveCard, applyEvent, emptyLive, streamAgent, type AgentResult, type Live } from "@/components/agent";
import { CashChart } from "@/components/cash-chart";
import { CREW } from "@/components/crew";
import { DataVersion } from "@/components/data-version";
import { EvidenceButton } from "@/components/evidence";
import { useToast } from "@/components/fx";
import { ReminderSheet } from "@/components/reminder";
import { BrandMark } from "@/components/shell";
import { Button, cx, ErrorNote, MoneyInput, Sheet } from "@/components/ui";
import { get, post } from "@/lib/api";
import { inr, short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { Cockpit } from "./cockpit";
import { currentOdds, day, moveDetail, moveShort, moveTitle, pct, standing, type Activity, type Move, type Plan, type T } from "./model";

type Kind = "brief" | "user" | "cfo" | "crew" | "plan" | "why" | "afford" | "proof" | "sim" | "answer" | "event";
interface Msg {
  id: number;
  k: Kind;
  text?: string;
  strong?: string;
  actions?: Act[];
  question?: string;
}
type Act = { key: string; label: string; primary?: boolean };

const AGENT_ICON: Record<Move["kind"], React.ElementType> = { collect: HandCoins, defer: Clock, pause: PauseCircle, reserve: Landmark, borrow: Banknote, discount: Percent };

// ---------------------------------------------------------------- the desk

export function CfoDesk() {
  const { t, lang } = useT();
  const { version } = useContext(DataVersion);
  const toast = useToast();
  const [p, setP] = useState<Plan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [cushion, setCushion] = useState(false);
  const [remind, setRemind] = useState<string | null>(null);
  const nextId = useRef(1);
  const end = useRef<HTMLDivElement>(null);
  const briefed = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      const x = await get<Plan>("/api/autopilot");
      setP(x);
      setErr(null);
      return x;
    } catch (e) {
      setErr(String(e));
      return null;
    }
  }, []);

  const add = useCallback((m: Omit<Msg, "id">) => setMsgs((list) => [...list, { ...m, id: nextId.current++ }]), []);

  useEffect(() => {
    load().then((x) => {
      if (x && briefed.current !== version) {
        briefed.current = version;
        setMsgs([{ id: nextId.current++, k: "brief" }]);
      }
    });
  }, [load, version]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs.length]);

  const params = useSearchParams();
  const asked = useRef(false);
  useEffect(() => {
    const q = params.get("q");
    const d = params.get("do");
    if ((q || d) && p && p.status === "ok" && !asked.current) {
      asked.current = true;
      if (q) ask(q);
      const labels: Record<string, string> = { fix: t("Show me the fix"), why: t("Why?"), afford: t("Can I afford something?"), proof: t("How sure are you?"),
        sim: t("Fast-forward 2 weeks"), event: t("Tell me what's coming") };
      if (d && labels[d]) act(d, labels[d]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, p]);

  const ask = (text: string) => {
    const q = text.trim();
    if (!q) return;
    setInput("");
    add({ k: "user", text: q });
    add({ k: "answer", question: q });
  };

  const act = async (key: string, label: string) => {
    if (!p) return;
    if (key.startsWith("remind:")) {
      setRemind(key.slice(7));
      return;
    }
    add({ k: "user", text: label });
    if (key === "fix") add({ k: "crew" });
    else if (key === "why") add({ k: "why" });
    else if (key === "afford") add({ k: "afford" });
    else if (key === "proof") add({ k: "proof" });
    else if (key === "sim") add({ k: "sim" });
    else if (key === "event") add({ k: "event" });
    else if (key === "planb") {
      setBusy(true);
      try {
        const r = await post<{ approved: string[] }>("/api/autopilot/plan-b", {});
        const x = await load();
        add({ k: "cfo", strong: t("Plan B is on."), text: t("I approved {n} steps with you. Chance you stay safe now: {p}. I'll keep watching.", { n: r.approved.length, p: x ? pct(currentOdds(x).p_safe) : "—" }),
              actions: followUps(x, t) });
      } finally {
        setBusy(false);
      }
    }
  };

  if (err) return <div className="p-6"><ErrorNote message={err} retry={load} /></div>;
  if (!p) {
    return (
      <div className="grid flex-1 place-items-center">
        <p className="flex items-center gap-2 text-ink-2"><Loader2 className="size-5 animate-spin" /> {t("Looking 90 days ahead…")}</p>
      </div>
    );
  }
  if (p.status !== "ok") {
    return (
      <div className="mx-auto max-w-xl p-6">
        <Cfo>
          <p className="serif text-2xl">{t("FinPilot needs your bank balance to look ahead")}</p>
          <p className="mt-1 text-ink-2">{p.message}</p>
          <Link href="/data/"><Button className="mt-3">{t("Add your balance or bank statement")}</Button></Link>
        </Cfo>
      </div>
    );
  }

  const chips = suggestions(p, t);
  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="lg:hidden"><Cockpit p={p} onCushion={() => setCushion(true)} compact /></div>
      <section className="paper-grid flex min-h-0 flex-1 flex-col">
        <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto" role="log" aria-live="polite">
          <div className="mx-auto w-full max-w-2xl space-y-6 px-4 py-6 sm:px-6 lg:py-10">
            {msgs.map((m) => (
              <div key={m.id} className="rise">
                {m.k === "brief" && <Briefing p={p} onAct={act} />}
                {m.k === "user" && <Owner text={m.text ?? ""} />}
                {m.k === "cfo" && (
                  <Cfo>
                    {m.strong && <p className="serif text-xl leading-snug font-semibold">{m.strong}</p>}
                    {m.text && <p className="mt-1 text-[1.02rem] leading-relaxed text-ink-2">{m.text}</p>}
                    {m.actions && <Actions acts={m.actions} onAct={act} />}
                  </Cfo>
                )}
                {m.k === "crew" && <CrewRun onDone={async (f) => {
                  const x = await load();
                  add({ k: "cfo", text: f.mode === "ai" ? f.brief : t("Here's the fix my agents agreed on. Every number was re-checked against your books.") });
                  if (x && x.moves.some((mv) => mv.suggested && mv.kind !== "reserve" && mv.state === "open")) add({ k: "plan" });
                  else add({ k: "cfo", text: t("Nothing to approve right now."), actions: followUps(x, t) });
                }} />}
                {m.k === "plan" && <PlanCard p={p} onApproved={async (msg) => {
                  const x = await load();
                  add({ k: "cfo", strong: t("Done. Your agents are on it."), text: msg, actions: followUps(x, t) });
                }} />}
                {m.k === "why" && <Why p={p} />}
                {m.k === "afford" && <Afford p={p} />}
                {m.k === "proof" && <Proof />}
                {m.k === "sim" && <Sim p={p} onDone={async (planB) => {
                  const x = await load();
                  add({ k: "cfo", strong: planB ? t("A checkpoint was missed — Plan B is ready.") : t("That's where things stand now."),
                        text: x ? headlineFor(x, t, lang) : undefined,
                        actions: planB ? [{ key: "planb", label: t("Approve Plan B"), primary: true }, ...followUps(x, t).map((a) => ({ ...a, primary: false }))] : followUps(x, t) });
                }} />}
                {m.k === "answer" && <Answer question={m.question ?? ""} onDone={load} />}
                {m.k === "event" && <Coming p={p} onAdded={async (label) => {
                  const x = await load();
                  add({ k: "cfo", strong: t("Added “{label}” to your forecast.", { label }), text: x ? headlineFor(x, t, lang) : undefined, actions: x && fixAvailable(x) ? [{ key: "fix", label: t("Show me the fix"), primary: true }] : followUps(x, t) });
                }} />}
              </div>
            ))}
            <div ref={end} />
          </div>
        </div>
        <div className="shrink-0 border-t border-line bg-canvas/95 backdrop-blur">
          <div className="mx-auto w-full max-w-2xl px-4 pt-3 pb-[calc(0.9rem+env(safe-area-inset-bottom))] sm:px-6">
            <div className="no-scrollbar -mx-1 mb-2 flex gap-2 overflow-x-auto px-1">
              {chips.map((c) => (
                <button key={c.key} onClick={() => act(c.key, c.label)} disabled={busy}
                  className="shrink-0 rounded-full border border-line bg-surface px-3.5 py-1.5 text-sm font-medium text-ink-2 transition hover:border-ink hover:text-ink disabled:opacity-50">
                  {c.label}
                </button>
              ))}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); ask(input); }} className="flex items-center gap-2 rounded-2xl border border-line bg-surface p-1.5 pl-4 shadow-sm focus-within:border-ink">
              <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={t("Ask your CFO anything — “Who pays me late?”")}
                className="h-10 w-full bg-transparent text-[0.95rem] outline-none placeholder:text-muted" aria-label={t("Ask your CFO")} />
              <MicButton onText={ask} />
              <button type="submit" disabled={!input.trim()} aria-label={t("Send")} className="grid size-10 shrink-0 place-items-center rounded-xl bg-ink text-canvas transition disabled:opacity-30">
                <ArrowUp className="size-5" />
              </button>
            </form>
          </div>
        </div>
      </section>
      <div className="hidden w-[420px] shrink-0 lg:block xl:w-[460px]"><Cockpit p={p} onCushion={() => setCushion(true)} /></div>
      <CushionSheet open={cushion} onClose={() => setCushion(false)} current={p.safety} suggested={p.default_safety} onSaved={() => { load(); toast.show({ text: t("Cushion saved"), tone: "good" }); }} />
      <ReminderSheet customer={remind} onClose={() => setRemind(null)} />
    </div>
  );
}

// ---------------------------------------------------------------- what the CFO says first

function pendingPlanB(acts: Activity[]) {
  for (const a of acts) {
    if (a.agent === "planner" && a.tone === "good") return false; // approved since
    if (a.action?.type === "plan_b") return true;
  }
  return false;
}

function headlineFor(p: Plan, t: T, lang: string) {
  const anyApproved = p.moves.some((m) => m.state !== "open");
  const b = anyApproved ? p.with_approved : p.baseline;
  const s = standing(p);
  if (s === "out") return t("You'll run out of money in {n} days — on {date}.", { n: b.days_to_trouble ?? 0, date: day(b.runs_out, lang) });
  if (s === "tight") return t("Money gets tight in {n} days — on {date} you dip below your cushion.", { n: b.days_to_trouble ?? 0, date: day(b.below_safety_from, lang) });
  if (s === "unsure") return t("You're probably fine — but in {x} of 100 futures cash dips below your cushion.", { x: Math.round((1 - currentOdds(p).p_safe) * 100) });
  return t("You're in good shape. You can spend up to {amt} today and stay above your cushion.", { amt: short(b.spendable_today) });
}

function fixAvailable(p: Plan) {
  return !p.moves.some((m) => m.state !== "open") && p.moves.some((m) => m.suggested && m.kind !== "reserve");
}

function followUps(p: Plan | null, t: T): Act[] {
  if (!p) return [];
  const out: Act[] = [];
  const collect = p.moves.find((m) => m.kind === "collect" && m.state === "approved");
  if (collect) out.push({ key: `remind:${collect.party}`, label: t("Send the reminder to {who}", { who: collect.party }), primary: true });
  if (p.is_demo) out.push({ key: "sim", label: t("Fast-forward 2 weeks") });
  out.push({ key: "afford", label: t("Can I afford something?") });
  return out;
}

function suggestions(p: Plan, t: T): Act[] {
  const out: Act[] = [];
  if (pendingPlanB(p.activity)) out.push({ key: "planb", label: t("Approve Plan B") });
  if (fixAvailable(p)) out.push({ key: "fix", label: t("Show me the fix") });
  out.push({ key: "why", label: t("Why?") });
  out.push({ key: "afford", label: t("Can I afford something?") });
  out.push({ key: "event", label: t("Tell me what's coming") });
  if (p.is_demo) out.push({ key: "sim", label: t("Fast-forward 2 weeks") });
  out.push({ key: "proof", label: t("How sure are you?") });
  return out;
}

function Briefing({ p, onAct }: { p: Plan; onAct: (k: string, l: string) => void }) {
  const { t, lang } = useT();
  const h = new Date().getHours();
  const hello = h < 12 ? t("Good morning") : h < 17 ? t("Good afternoon") : t("Good evening");
  const s = standing(p);
  const anyApproved = p.moves.some((m) => m.state !== "open");
  const suggested = p.moves.filter((m) => m.suggested && m.kind !== "reserve");
  const backup = p.moves.find((m) => m.kind === "borrow");
  const planB = pendingPlanB(p.activity);
  const missed = p.activity.find((a) => a.agent === "collections" && a.tone === "bad");
  const lines: string[] = [];
  if (planB && missed) lines.push(missed.text);
  if (anyApproved && !p.baseline.safe && (s === "ok" || s === "unsure")) lines.push(t("Without your plan, {what}.", { what: p.baseline.runs_out ? t("money would run out on {date}", { date: day(p.baseline.runs_out, lang) }) : t("you'd dip below your cushion on {date}", { date: day(p.baseline.below_safety_from, lang) }) }));
  if (p.watching.length) {
    const w = [...p.watching].sort((a, b) => a.checkpoint.localeCompare(b.checkpoint))[0];
    lines.push(t("I'm watching {n} thing(s) for you — next check: {who} by {date}.", { n: p.watching.length, who: w.party, date: day(w.checkpoint, lang) }));
  }
  if (!anyApproved && suggested.length) {
    lines.push(backup?.odds_with_plan
      ? t("I found a fix: {n} steps take your chance of staying safe from {a} to {b} — and to {c} with a safety net.", { n: suggested.length, a: pct(p.odds.baseline.p_safe), b: pct(p.odds.suggested.p_safe), c: pct(backup.odds_with_plan) })
      : t("I found a fix: {n} steps take your chance of staying safe from {a} to {b}.", { n: suggested.length, a: pct(p.odds.baseline.p_safe), b: pct(p.odds.suggested.p_safe) }));
  }
  if (p.changes.length && !planB) lines.push(p.changes.slice(0, 2).map((c) => c.text).join(" "));
  const primary: Act | null = planB ? { key: "planb", label: t("Approve Plan B"), primary: true }
    : fixAvailable(p) ? { key: "fix", label: t("Show me the fix"), primary: true }
      : anyApproved && p.is_demo ? { key: "sim", label: t("Fast-forward 2 weeks"), primary: true }
        : { key: "afford", label: t("Can I afford something?"), primary: true };
  const secondary: Act[] = [{ key: "why", label: t("Why?") }, { key: "afford", label: t("Can I afford something?") }, { key: "proof", label: t("How sure are you?") }]
    .filter((a) => a.key !== primary.key);
  const tone = s === "out" ? "text-bad" : s === "tight" || s === "unsure" ? "text-caution" : "text-good";
  return (
    <Cfo>
      <p className="text-ink-2">{hello}, {p.business}.</p>
      <p className={cx("serif mt-1 text-3xl leading-tight font-semibold sm:text-[2.1rem]", tone)}>
        {s === "out" || s === "tight" ? <AlertTriangle className="mr-2 inline size-7 -translate-y-0.5" /> : null}
        {headlineFor(p, t, lang)}
      </p>
      {lines.map((l, i) => <p key={i} className="mt-3 text-[1.05rem] leading-relaxed text-ink-2">{l}</p>)}
      <Listen text={[`${hello}, ${p.business}.`, headlineFor(p, t, lang), ...lines].join(" ")} />
      <Actions acts={[primary, ...secondary]} onAct={onAct} />
    </Cfo>
  );
}

// ---------------------------------------------------------------- message shells

function Cfo({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex gap-3 sm:gap-4">
      <div className="pt-0.5"><BrandMark size="sm" /></div>
      <div className="min-w-0 flex-1">
        <p className="mb-1 text-[0.7rem] font-semibold tracking-[0.14em] text-muted uppercase">FinPilot · {"CFO"}</p>
        {children}
      </div>
    </div>
  );
}

function Owner({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[80%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-[0.95rem] text-canvas">{text}</p>
    </div>
  );
}

function Actions({ acts, onAct }: { acts: Act[]; onAct: (k: string, l: string) => void }) {
  const [used, setUsed] = useState(false);
  if (!acts.length) return null;
  return (
    <div className={cx("mt-4 flex flex-wrap gap-2 transition", used && "pointer-events-none opacity-40")}>
      {acts.map((a) => (
        <button key={a.key} onClick={() => { if (!a.key.startsWith("remind:")) setUsed(true); onAct(a.key, a.label); }}
          className={cx("inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition active:scale-95",
            a.primary ? "bg-ink text-canvas shadow-lg shadow-black/10 hover:bg-brand" : "border border-line bg-surface text-ink hover:border-ink")}>
          {a.primary && <Sparkles className="size-4" />} {a.label}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- the crew at work

interface CrewRow { agent: string; name: string; doing: string; text?: string; tone?: string; done: boolean }

function CrewRun({ onDone }: { onDone: (f: { brief?: string; mode?: string }) => void }) {
  const { t, lang } = useT();
  const [rows, setRows] = useState<CrewRow[]>([]);
  const [finished, setFinished] = useState(false);
  const [open, setOpen] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useState<string>("");
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    streamAgent<{ status: string; brief?: string; mode?: string; message?: string }>("/api/crew/stream", {}, (e) => {
      if (e.type !== "agent") return;
      const agent = String(e.agent);
      if (e.phase === "start") setRows((r) => (r.some((x) => x.agent === agent) ? r : [...r, { agent, name: String(e.name), doing: String(e.doing), done: false }]));
      else if (e.phase === "done") setRows((r) => r.map((x) => (x.agent === agent ? { ...x, text: String(e.text), tone: String(e.tone), done: true } : x)));
    }, lang)
      .then((f) => {
        setRows((r) => r.map((x) => ({ ...x, done: true })));
        setFinished(true);
        setMode(f.mode ?? "");
        setTimeout(() => setOpen(false), 900);
        onDone(f);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const doneN = rows.filter((r) => r.done).length;
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-sm sm:ml-14">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 px-4 py-3 text-left">
        {finished ? <CheckCheck className="size-5 text-good" /> : <Loader2 className="size-5 animate-spin text-brand" />}
        <span className="flex-1 text-sm font-semibold">
          {finished ? t("{n} agents worked on this · every number re-checked", { n: rows.length }) : t("Your agents are working… {d}/{n}", { d: doneN, n: Math.max(rows.length, doneN) })}
        </span>
        {mode === "ai" && <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[0.65rem] font-bold text-brand uppercase">AI</span>}
        <ChevronDown className={cx("size-4 text-muted transition", open && "rotate-180")} />
      </button>
      {open && (
        <ol className="divide-y divide-line border-t border-line">
          {rows.map((r) => {
            const C = CREW[r.agent] ?? { I: Sparkles, grad: "grad-night" };
            const first = (r.text ?? "").split(/(?<=[.।])\s/)[0];
            return (
              <li key={r.agent} className={cx("flex gap-3 px-4 py-2.5", !r.done && "working")}>
                <span className={cx("mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg", C.grad)}><C.I className="size-3.5" /></span>
                <div className="min-w-0 flex-1 text-sm">
                  <span className="font-semibold">{r.name}</span>{" "}
                  <span className={cx("text-ink-2", r.tone === "bad" && "text-bad", r.tone === "caution" && "text-caution", r.tone === "good" && "text-good")}>
                    {r.done ? <Expandable short={first} full={r.text ?? ""} /> : r.doing}
                  </span>
                </div>
              </li>
            );
          })}
          {!rows.length && !err && <li className="working px-4 py-3 text-sm text-ink-2">{t("Waking up your agents…")}</li>}
        </ol>
      )}
      {err && <p className="border-t border-line p-3 text-sm text-bad">{err}</p>}
    </div>
  );
}

function Expandable({ short: s, full }: { short: string; full: string }) {
  const { t } = useT();
  const [more, setMore] = useState(false);
  if (s.length >= full.length - 2) return <>{full}</>;
  return (
    <>
      {more ? full : s}{" "}
      <button onClick={() => setMore(!more)} className="text-xs font-semibold text-brand">{more ? t("less") : t("more")}</button>
    </>
  );
}

// ---------------------------------------------------------------- the fix, ready to approve

function PlanCard({ p, onApproved }: { p: Plan; onApproved: (msg: string) => void }) {
  const { t, lang } = useT();
  const toast = useToast();
  const steps = p.moves.filter((m) => m.suggested);
  const backup = p.moves.find((m) => m.kind === "borrow");
  const [net, setNet] = useState(true);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(steps.some((m) => m.state !== "open"));
  const [open, setOpen] = useState<string | null>(null);
  const after = backup && net ? backup.odds_with_plan ?? p.odds.suggested.p_safe : p.odds.suggested.p_safe;
  const approve = async () => {
    setBusy(true);
    try {
      await post("/api/autopilot/approve-suggested", {});
      if (backup && net) {
        const r = await post<{ next?: string; text?: string }>(`/api/autopilot/moves/${encodeURIComponent(backup.id)}`, { decision: "approve" });
        if (r.text) {
          try {
            await navigator.clipboard.writeText(r.text);
            toast.show({ text: t("Letter to your bank copied — paste it in an email"), tone: "good" });
          } catch {}
        }
      }
      setDone(true);
      const w = steps.find((m) => m.kind === "collect");
      onApproved(w ? t("I'll check that {who} has paid by {date}. Nothing has been sent yet — the reminder is ready for you to send.", { who: w.party, date: day(new Date(new Date(p.as_of + "T00:00:00").getTime() + 10 * 86400000).toISOString().slice(0, 10), lang) })
        : t("I'll keep watching your cash every day and tell you if anything changes."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="overflow-hidden rounded-3xl border border-line bg-surface shadow-[0_20px_50px_-20px_rgb(15_21_18/0.25)] sm:ml-14">
      <div className="pit flex flex-wrap items-end justify-between gap-3 px-5 py-4">
        <div>
          <p className="text-[0.65rem] tracking-[0.16em] text-pit-muted uppercase">{t("The fix")}</p>
          <p className="serif text-lg">{t("{n} steps · chance you stay safe", { n: steps.length })}</p>
        </div>
        <p className="serif text-3xl font-semibold">
          <span className="text-pit-muted line-through decoration-1">{pct(p.odds.baseline.p_safe)}</span>
          <span className="mx-2 text-pit-muted">→</span>
          <span className="glow-text">{pct(after)}</span>
        </p>
      </div>
      <ol className="divide-y divide-line">
        {steps.map((m, i) => {
          const I = AGENT_ICON[m.kind];
          return (
            <li key={m.id} className="px-5 py-3">
              <button onClick={() => setOpen(open === m.id ? null : m.id)} className="flex w-full items-center gap-3 text-left">
                <span className="serif w-5 shrink-0 text-lg text-muted">{i + 1}</span>
                <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand"><I className="size-4" /></span>
                <span className="min-w-0 flex-1 font-medium">{moveTitle(m, t, lang)}</span>
                <span className="shrink-0 text-sm font-semibold text-good">{m.impact > 0 ? `+${short(m.impact)}` : m.kind === "reserve" ? "" : ""}</span>
                {(done || m.state !== "open") && <Check className="size-4 shrink-0 text-good" />}
              </button>
              {open === m.id && <p className="mt-1.5 pl-16 text-sm text-ink-2">{moveDetail(m, t, lang)}</p>}
            </li>
          );
        })}
        {backup && (
          <li className="bg-surface-2/60 px-5 py-3">
            <label className="flex cursor-pointer items-start gap-3">
              <input type="checkbox" checked={net} disabled={done} onChange={(e) => setNet(e.target.checked)} className="mt-1 size-4 accent-[var(--color-brand)]" />
              <span className="text-sm">
                <span className="font-semibold">{t("Add a safety net: keep a {amt} overdraft ready", { amt: short(backup.amount) })}</span>
                <span className="block text-ink-2">{t("Costs nothing unless used — about {amt} if you use all of it for 90 days. I'll draft the letter to your bank.", { amt: short(backup.interest_if_used ?? 0) })}</span>
              </span>
            </label>
          </li>
        )}
      </ol>
      <WhyThisPlan p={p} chosen={steps.filter((m) => m.kind !== "reserve").map((m) => m.id)} />
      <div className="flex flex-wrap items-center gap-3 border-t border-line px-5 py-4">
        {done ? (
          <p className="flex items-center gap-2 font-semibold text-good"><CircleCheck className="size-5" /> {t("Approved")}</p>
        ) : (
          <>
            <button onClick={approve} disabled={busy} className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 font-semibold text-canvas shadow-lg transition hover:bg-brand disabled:opacity-50">
              <CheckCheck className="size-5" /> {t("Approve the fix")}
            </button>
            <p className="text-xs text-muted">{t("Nothing is paid or sent by itself — you send each message.")}</p>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- why

function Why({ p }: { p: Plan }) {
  const { t, lang } = useT();
  const b = p.baseline;
  const causes = p.causes.map((c) => ({ ...c, label: c.label.replace(/^(SCH|BILL|INV)-[\w-]+ (to|from) /, "") }));
  return (
    <Cfo>
      <p className="serif text-xl font-semibold">{b.safe ? t("Here's how the next 90 days look.") : t("Three things cause the dip.")}</p>
      {!b.safe && causes.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {causes.map((c, i) => (
            <li key={i} className="flex items-baseline justify-between gap-3 border-b border-dashed border-line pb-1.5 text-[0.98rem]">
              <span>{c.label} <span className="text-muted">· {day(c.date, lang)}</span></span>
              <span className="num font-semibold">−{short(c.amount)}</span>
            </li>
          ))}
        </ul>
      )}
      {p.at_risk.map((r) => (
        <p key={r.party} className="mt-3 text-ink-2">{t("And I'm not counting {amt} due from {who} on {date} — they're already {d} days late on older invoices.", { amt: short(r.amount), who: r.party, date: day(r.next_due, lang), d: r.oldest_late_days })}</p>
      ))}
      <div className="mt-4 rounded-2xl border border-line bg-surface p-4">
        <CashChart baseline={p.series.baseline} plan={p.series.plan} safety={p.safety} planLabel={p.plan_basis === "approved" ? "With your approved moves" : "With the agents' plan"} />
      </div>
      <div className="mt-3"><EvidenceButton evidence={p.evidence} label={t("How is this worked out?")} /></div>
    </Cfo>
  );
}

// ---------------------------------------------------------------- can I afford it?

interface AffordResult {
  status: string;
  message?: string;
  verdict: "yes" | "yes_if" | "risky" | "not_now";
  amount: number;
  date: string;
  without_moves: { lowest: number; runs_out: string | null; p_safe: number };
  with_plan: { p_safe: number; moves: { id: string }[] };
  earliest_safe_date_without_moves: string | null;
}

function Afford({ p }: { p: Plan }) {
  const { t, lang } = useT();
  const [amount, setAmount] = useState("");
  const [when, setWhen] = useState(7);
  const [r, setR] = useState<AffordResult | null>(null);
  const [busy, setBusy] = useState(false);
  const whens = [{ d: 1, l: t("Tomorrow") }, { d: 7, l: t("Next week") }, { d: 30, l: t("In a month") }, { d: 60, l: t("In 2 months") }];
  const check = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!Number(amount)) return;
    setBusy(true);
    const d = new Date(new Date(p.as_of + "T00:00:00").getTime() + when * 86400000);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    try {
      setR(await post<AffordResult>("/api/autopilot/afford", { amount: Number(amount), date: iso }));
    } finally {
      setBusy(false);
    }
  };
  const V = r && r.status === "ok" ? {
    yes: { c: "text-good", title: t("Yes — go ahead.") },
    yes_if: { c: "text-good", title: t("Yes — if you approve your agents' plan.") },
    risky: { c: "text-caution", title: t("Risky.") },
    not_now: { c: "text-bad", title: t("Not now.") },
  }[r.verdict] : null;
  return (
    <Cfo>
      <p className="serif text-xl font-semibold">{t("How much, and when?")}</p>
      <form onSubmit={check} className="mt-3 space-y-2.5 rounded-2xl border border-line bg-surface p-4">
        <MoneyInput value={amount} onChange={(v) => { setAmount(v); setR(null); }} placeholder={t("Amount")} />
        <div className="flex flex-wrap gap-2">
          {whens.map((w) => (
            <button key={w.d} type="button" onClick={() => { setWhen(w.d); setR(null); }}
              className={cx("rounded-full border px-3 py-1.5 text-sm font-medium", when === w.d ? "border-ink bg-ink text-canvas" : "border-line text-ink-2")}>{w.l}</button>
          ))}
          <Button type="submit" size="sm" className="ml-auto" disabled={!Number(amount) || busy}>{busy ? <Loader2 className="size-4 animate-spin" /> : t("Check")}</Button>
        </div>
      </form>
      {r && V && (
        <div className="rise mt-4">
          <p className={cx("serif text-2xl font-semibold", V.c)}>{V.title}</p>
          <p className="mt-1 text-[1.02rem] leading-relaxed text-ink-2">
            {r.verdict === "yes"
              ? t("Your tightest day would be {amt} and you stay safe in {p} of futures.", { amt: short(r.without_moves.lowest), p: pct(r.without_moves.p_safe) })
              : r.without_moves.runs_out
                ? t("On its own, it would make you run out of cash on {date}.", { date: day(r.without_moves.runs_out, lang) })
                : t("On its own, your tightest day would be {amt} — below your cushion.", { amt: short(r.without_moves.lowest) })}{" "}
            {r.verdict !== "yes" && r.with_plan.moves.length > 0 && t("With your agents' plan ({moves}), you stay safe in {p} of futures.", { moves: r.with_plan.moves.length, p: pct(r.with_plan.p_safe) })}{" "}
            {r.verdict !== "yes" && r.earliest_safe_date_without_moves && t("Without changing anything, the earliest safe day to pay is {date}.", { date: day(r.earliest_safe_date_without_moves, lang) })}
          </p>
        </div>
      )}
    </Cfo>
  );
}

// ---------------------------------------------------------------- how sure are you?

interface Track { status: string; message?: string; weeks: number; low_better_than_flat_pct: number | null; dips: number; dips_flagged: number; brier: number }

function Proof() {
  const { t } = useT();
  const [r, setR] = useState<Track | null>(null);
  useEffect(() => {
    get<Track>("/api/track-record").then(setR).catch(() => setR(null));
  }, []);
  return (
    <Cfo>
      {!r ? (
        <p className="flex items-center gap-2 text-ink-2"><Loader2 className="size-4 animate-spin" /> {t("Testing myself on your past weeks…")}</p>
      ) : r.status !== "ok" ? (
        <p className="text-ink-2">{r.message}</p>
      ) : (
        <>
          <p className="serif text-xl font-semibold">{t("I tested myself on your last {n} weeks.", { n: r.weeks })}</p>
          <p className="mt-1 text-ink-2">{t("Each week I rewound your books, forecast the next 30 days, and compared with what really happened.")}</p>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {[
              { v: r.low_better_than_flat_pct != null ? pct(r.low_better_than_flat_pct) : "—", l: t("closer on the tightest day than guessing") },
              { v: r.dips ? `${r.dips_flagged}/${r.dips}` : "—", l: t("real dips flagged in advance") },
              { v: r.brier.toFixed(2), l: t("odds score (0 = perfect)") },
            ].map((s) => (
              <div key={s.l} className="rounded-2xl border border-line bg-surface p-3">
                <p className="serif text-3xl font-semibold text-brand">{s.v}</p>
                <p className="text-xs leading-snug text-ink-2">{s.l}</p>
              </div>
            ))}
          </div>
          <Link href="/proof/" className="mt-3 inline-block text-sm font-semibold text-brand">{t("See the full track record")} →</Link>
        </>
      )}
    </Cfo>
  );
}

// ---------------------------------------------------------------- fast-forward (demo)

interface DayEv { date: string; balance: number; items: { kind: string; party?: string; amount?: number }[] }

function Sim({ p, onDone }: { p: Plan; onDone: (planB: boolean) => void }) {
  const { t, lang } = useT();
  const [scenario, setScenario] = useState<string | null>(null);
  const [days, setDays] = useState<DayEv[]>([]);
  const [acts, setActs] = useState<Activity[]>([]);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const late = p.at_risk[0]?.party ?? p.moves.find((m) => m.kind === "collect")?.party;
  const go = async (sc: string) => {
    setScenario(sc);
    setRunning(true);
    let planB = false;
    try {
      await streamAgent("/api/demo/fast-forward/stream", { days: 14, scenario: sc }, (e) => {
        if (e.type === "day") setDays((d) => [...d, e as unknown as DayEv]);
        if (e.type === "activity") {
          setActs((a) => [...a, e as unknown as Activity]);
          if ((e as unknown as Activity).action?.type === "plan_b") planB = true;
        }
      }, lang);
      onDone(planB);
    } catch (x) {
      setErr(x instanceof Error ? x.message : String(x));
    } finally {
      setRunning(false);
    }
  };
  if (!p.is_demo) return <Cfo><p className="text-ink-2">{t("Fast-forward only works on the demo businesses.")}</p></Cfo>;
  return (
    <Cfo>
      <p className="serif text-xl font-semibold">{t("Let's live the next two weeks.")}</p>
      {!scenario && (
        <>
          <p className="mt-1 text-ink-2">{late ? t("What should {who} do?", { who: late }) : t("How should customers behave?")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {[["defaults", late ? t("{who} never pays", { who: late }) : t("The late customer never pays")], ["pays", late ? t("{who} pays after the reminder", { who: late }) : t("The late customer pays after the reminder")], ["usual", t("Let chance decide")]].map(([k, l]) => (
              <button key={k} onClick={() => go(k)} className="rounded-full border border-line bg-surface px-4 py-2 text-sm font-semibold hover:border-ink">{l}</button>
            ))}
          </div>
        </>
      )}
      {scenario && (
        <div className="mt-3 overflow-hidden rounded-2xl border border-line bg-surface">
          <ol className="divide-y divide-line">
            {days.map((d) => {
              const big = d.items.filter((i) => i.kind !== "typical");
              const da = acts.filter((a) => a.book_date === d.date);
              if (!big.length && !da.length) return null;
              return (
                <li key={d.date} className="rise px-4 py-2.5 text-sm">
                  <div className="flex items-baseline gap-3">
                    <span className="w-14 shrink-0 text-xs text-muted">{day(d.date, lang)}</span>
                    <span className="min-w-0 flex-1 truncate text-ink-2">{big.map((i) => i.kind === "bill" ? `${i.party} −${short(Math.abs(i.amount ?? 0))}` : i.kind === "paid_in" ? `${i.party} +${short(i.amount)}` : i.kind === "overdraft" ? t("overdraft +{amt}", { amt: short(i.amount) }) : "").join(" · ")}</span>
                    <span className={cx("num shrink-0 font-semibold", d.balance < p.safety ? "text-caution" : "text-ink")}>{short(d.balance)}</span>
                  </div>
                  {da.map((a, k) => {
                    const C = CREW[a.agent] ?? { I: Sparkles, grad: "grad-night" };
                    return (
                      <div key={k} className="mt-2 flex gap-2.5 rounded-xl bg-brand-50/60 p-2.5">
                        <span className={cx("grid size-6 shrink-0 place-items-center rounded-lg", C.grad)}><C.I className="size-3" /></span>
                        <p className="text-[0.9rem] text-ink">{a.text}</p>
                      </div>
                    );
                  })}
                </li>
              );
            })}
            {running && <li className="working flex items-center gap-2 px-4 py-2.5 text-sm text-ink-2"><FastForward className="size-4" /> {t("Living the next day…")}</li>}
          </ol>
        </div>
      )}
      {err && <p className="mt-2 text-sm text-bad">{err}</p>}
    </Cfo>
  );
}

// ---------------------------------------------------------------- free questions: the tool-using agent

function Answer({ question, onDone }: { question: string; onDone: () => void }) {
  const { lang } = useT();
  const [live, setLive] = useState<Live | null>(emptyLive());
  const [res, setRes] = useState<AgentResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    streamAgent<AgentResult>("/api/ask/stream", { question, conversation_id: "desk" }, (e) => setLive((l) => (l ? applyEvent(l, e) : l)), lang, "/api/ask")
      .then((r) => { setRes(r); onDone(); })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLive(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <Cfo>
      {live && <LiveCard live={live} />}
      {res && <AgentAnswer a={res} conversation="desk" />}
      {err && <p className="text-sm text-bad">{err}</p>}
    </Cfo>
  );
}

// ---------------------------------------------------------------- cushion

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

// ---------------------------------------------------------------- why this plan (the planner's working, shown)

function WhyThisPlan({ p, chosen }: { p: Plan; chosen: string[] }) {
  const { t, lang } = useT();
  const [open, setOpen] = useState(false);
  const key = (ids: string[]) => [...ids].sort().join("|");
  const mine = key(chosen);
  const rows = [...p.search.plans].sort((a, b) => b.p_safe - a.p_safe || a.cost - b.cost).slice(0, 6);
  if (!rows.length) return null;
  return (
    <div className="border-t border-line px-5 py-3">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-1.5 text-sm font-semibold text-brand" aria-expanded={open}>
        {t("Why this plan?")} <ChevronDown className={cx("size-4 transition", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-2">
          <p className="text-sm text-ink-2">
            {t("I scored all {c} combinations of moves and played the best {k} out in {n} futures each. I pick the best odds — and among plans about as safe, the one that asks least of you.",
              { c: p.search.combinations, k: p.search.stress_tested, n: p.search.sims_each.toLocaleString("en-IN") })}
          </p>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr><th className="py-1 pr-3 font-medium">{t("Plan")}</th><th className="py-1 pr-3 font-medium">{t("Effort")}</th><th className="py-1 pr-3 font-medium">{t("Tightest day")}</th><th className="py-1 font-medium">{t("Odds")}</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((r, i) => {
                  const me = key(r.moves) === mine;
                  return (
                    <tr key={i} className={cx(me && "bg-brand-50 font-semibold")}>
                      <td className="py-1.5 pr-3">{r.moves.length ? r.moves.map((id) => moveShort(id, p, t, lang)).join(" + ") : t("Do nothing")}{me && <span className="ml-1.5 text-xs text-brand">← {t("chosen")}</span>}</td>
                      <td className="py-1.5 pr-3 text-ink-2">{"●".repeat(Math.min(r.cost, 8)) || "—"}</td>
                      <td className={cx("num py-1.5 pr-3", r.reaches_safety ? "text-ink" : "text-bad")}>{short(r.lowest)}</td>
                      <td className="num py-1.5">{pct(r.p_safe)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- tell me what's coming

function Coming({ p, onAdded }: { p: Plan; onAdded: (label: string) => void }) {
  const { t } = useT();
  const toast = useToast();
  const [label, setLabel] = useState("");
  const [dir, setDir] = useState<"in" | "out">("in");
  const [amount, setAmount] = useState("");
  const [days, setDays] = useState(21);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const examples = [
    { l: t("Diwali sales boost"), d: "in" as const }, { l: t("A big order is coming"), d: "in" as const },
    { l: t("New machine / equipment"), d: "out" as const }, { l: t("Festival bonus for staff"), d: "out" as const },
  ];
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!label.trim() || !Number(amount)) return;
    setBusy(true);
    const d = new Date(new Date(p.as_of + "T00:00:00").getTime() + days * 86400000);
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    try {
      await post("/api/events", { label: label.trim(), amount: Number(amount), direction: dir, date: iso });
      setDone(true);
      onAdded(label.trim());
    } catch (x) {
      toast.show({ text: x instanceof Error ? x.message : String(x), tone: "bad" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Cfo>
      <p className="serif text-xl font-semibold">{t("What do you know that your books don't?")}</p>
      <p className="mt-1 text-ink-2">{t("A festival rush, a big order, a purchase you're planning — I'll put it into every forecast and plan.")}</p>
      <form onSubmit={save} className={cx("mt-3 space-y-2.5 rounded-2xl border border-line bg-surface p-4", done && "pointer-events-none opacity-50")}>
        <div className="flex flex-wrap gap-2">
          {examples.map((x) => (
            <button key={x.l} type="button" onClick={() => { setLabel(x.l); setDir(x.d); }} className="rounded-full border border-line px-3 py-1 text-xs font-medium text-ink-2 hover:border-ink">{x.l}</button>
          ))}
        </div>
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={t("What is it?")} className="h-11 w-full rounded-xl border border-line bg-surface px-3 outline-none focus:border-ink" aria-label={t("What is it?")} />
        <div className="flex flex-wrap items-center gap-2">
          {(["in", "out"] as const).map((x) => (
            <button key={x} type="button" onClick={() => setDir(x)} className={cx("rounded-full border px-3 py-1.5 text-sm font-medium", dir === x ? "border-ink bg-ink text-canvas" : "border-line text-ink-2")}>
              {x === "in" ? t("Money coming in") : t("Money going out")}
            </button>
          ))}
        </div>
        <MoneyInput value={amount} onChange={setAmount} placeholder={t("Amount")} />
        <div className="flex flex-wrap items-center gap-2">
          {[7, 21, 45, 75].map((d) => (
            <button key={d} type="button" onClick={() => setDays(d)} className={cx("rounded-full border px-3 py-1.5 text-sm font-medium", days === d ? "border-ink bg-ink text-canvas" : "border-line text-ink-2")}>
              {t("in {n} days", { n: d })}
            </button>
          ))}
          <Button type="submit" size="sm" className="ml-auto" disabled={busy || !label.trim() || !Number(amount)}>{t("Add to forecast")}</Button>
        </div>
      </form>
    </Cfo>
  );
}

// ---------------------------------------------------------------- voice: speak to the CFO, hear the briefing

type Rec = { lang: string; onresult: (e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => void; onend: () => void; start: () => void };

function MicButton({ onText }: { onText: (s: string) => void }) {
  const { t, lang } = useT();
  const [on, setOn] = useState(false);
  const [ok, setOk] = useState(false);
  useEffect(() => {
    const W = window as unknown as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown };
    setOk(Boolean(W.SpeechRecognition ?? W.webkitSpeechRecognition));
  }, []);
  if (!ok) return null;
  const start = () => {
    const W = window as unknown as { SpeechRecognition?: new () => Rec; webkitSpeechRecognition?: new () => Rec };
    const SR = (W.SpeechRecognition ?? W.webkitSpeechRecognition)!;
    const r = new SR();
    r.lang = lang === "hi" ? "hi-IN" : "en-IN";
    r.onresult = (e) => onText(e.results[0][0].transcript);
    r.onend = () => setOn(false);
    setOn(true);
    r.start();
  };
  return (
    <button type="button" onClick={start} aria-label={t("Speak")} className={cx("grid size-10 shrink-0 place-items-center rounded-xl transition", on ? "animate-pulse bg-bad text-white" : "text-ink-2 hover:bg-surface-2")}>
      <Mic className="size-5" />
    </button>
  );
}

function Listen({ text }: { text: string }) {
  const { t, lang } = useT();
  const [ok, setOk] = useState(false);
  const [on, setOn] = useState(false);
  useEffect(() => {
    setOk(typeof window !== "undefined" && "speechSynthesis" in window);
  }, []);
  if (!ok) return null;
  const say = () => {
    const s = window.speechSynthesis;
    if (on) {
      s.cancel();
      setOn(false);
      return;
    }
    const u = new SpeechSynthesisUtterance(text.replace(/₹/g, lang === "hi" ? "रुपये " : "rupees ").replace(/ L\b/g, lang === "hi" ? " लाख" : " lakh"));
    u.lang = lang === "hi" ? "hi-IN" : "en-IN";
    u.rate = 0.98;
    u.onend = () => setOn(false);
    setOn(true);
    s.speak(u);
  };
  return (
    <button onClick={say} className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-ink-2 hover:text-ink">
      <Volume2 className="size-4" /> {on ? t("Stop") : t("Listen")}
    </button>
  );
}
