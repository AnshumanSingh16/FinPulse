"use client";

import { ArrowRight, Bot, CalendarClock, Eye, FastForward, GitBranch, Loader2, MessageCircle, RotateCcw, Target } from "lucide-react";
import Link from "next/link";
import { useContext, useEffect, useRef, useState } from "react";
import { streamAgent } from "@/components/agent";
import { CREW } from "@/components/crew";
import { DataVersion } from "@/components/data-version";
import { useToast } from "@/components/fx";
import { ReminderSheet } from "@/components/reminder";
import { Button, cx, Sheet } from "@/components/ui";
import { get, post } from "@/lib/api";
import { short } from "@/lib/format";
import { useT } from "@/lib/i18n";

export interface Activity {
  id?: number;
  book_date: string;
  agent: string;
  tone: string;
  text: string;
  action: { type: "remind"; party: string } | { type: "plan_b" } | null;
}
export interface PlanB {
  if_fails: string;
  checkpoint: string;
  then: string[];
  p_safe: number;
  lowest: number;
  reaches_safety: boolean;
  backup: { amount: number; p_safe: number; interest_if_used: number } | null;
}
export interface Watch {
  move_id: string;
  party: string;
  checkpoint: string;
  kind: string;
}

function day(iso: string | null | undefined, lang = "en") {
  if (!iso) return "";
  return new Date(iso + "T00:00:00").toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short" });
}
const pct = (x: number) => `${Math.round(x * 100)}%`;
const dot: Record<string, string> = { good: "bg-good", bad: "bg-bad", caution: "bg-caution", info: "bg-muted" };

function AgentIcon({ agent, small }: { agent: string; small?: boolean }) {
  const C = CREW[agent] ?? { I: Bot, grad: "grad-night" };
  return (
    <span className={cx("grid shrink-0 place-items-center rounded-xl", small ? "size-7" : "size-9", C.grad)}>
      <C.I className={small ? "size-3.5" : "size-4.5"} aria-hidden />
    </span>
  );
}

function prettyMove(id: string, t: (s: string, v?: Record<string, string | number>) => string) {
  const [kind, rest] = [id.split(":")[0], id.slice(id.indexOf(":") + 1)];
  if (kind === "pause") return rest === "Owner Drawings" ? t("pause owner drawings") : t("pause marketing");
  if (kind === "collect") return t("collect from {who}", { who: rest });
  if (kind === "defer") return t("move bill {id}", { id: rest });
  if (kind === "discount") return t("early-payment offer on {id}", { id: rest });
  return id;
}

/** Plan B and the checkpoints the agents are watching. */
export function WatchCard({ planB, watching, moves }: { planB: PlanB[]; watching: Watch[]; moves: { id: string; party: string; kind: string }[] }) {
  const { t, lang } = useT();
  // Plan B for the moves being watched; before anything is approved, just the first one
  const shown = watching.length ? planB.filter((b) => watching.some((w) => w.move_id === b.if_fails)) : planB.slice(0, 1);
  if (!shown.length && !watching.length) return null;
  return (
    <div className="card space-y-3 p-4">
      {watching.length > 0 && (
        <div>
          <p className="flex items-center gap-2 text-xs font-semibold tracking-wide text-brand uppercase"><Eye className="size-4" /> {t("Your agents are watching")}</p>
          <ul className="mt-1.5 space-y-1 text-sm">
            {watching.map((w) => (
              <li key={w.move_id} className="flex items-center gap-2">
                <CalendarClock className="size-4 shrink-0 text-muted" />
                <span>{w.kind === "collect" ? t("{who} should pay by {date}", { who: w.party, date: day(w.checkpoint, lang) })
                  : w.kind === "defer" ? t("{who} should agree by {date}", { who: w.party, date: day(w.checkpoint, lang) })
                  : t("{who} should take the offer by {date}", { who: w.party, date: day(w.checkpoint, lang) })}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {shown.map((b) => {
        const src = moves.find((m) => m.id === b.if_fails);
        const then = b.then.map((x) => prettyMove(x, t));
        if (b.backup) then.push(t("draw on a {amt} overdraft", { amt: short(b.backup.amount) }));
        return (
          <div key={b.if_fails} className="rounded-2xl bg-surface-2 p-3">
            <p className="flex items-center gap-2 text-xs font-semibold tracking-wide text-ink-2 uppercase"><GitBranch className="size-4" /> {t("Plan B, ready if needed")}</p>
            <p className="mt-1 text-sm">
              {t("If {who} hasn't paid by {date}: {then}.", { who: src?.party ?? b.if_fails, date: day(b.checkpoint, lang), then: then.join(", ") || t("keep the rest of the plan") })}{" "}
              <span className="font-semibold">{t("Chance of staying safe: {p}", { p: pct(b.backup ? b.backup.p_safe : b.p_safe) })}</span>
            </p>
          </div>
        );
      })}
    </div>
  );
}

/** What the agents did by themselves — newest first, with the next step ready where one is needed. */
export function ActivityFeed({ items, onChange }: { items: Activity[]; onChange: () => void }) {
  const { t, lang } = useT();
  const toast = useToast();
  const [remind, setRemind] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!items.length) return null;
  const planB = async () => {
    setBusy(true);
    try {
      const r = await post<{ approved: string[] }>("/api/autopilot/plan-b", {});
      toast.show({ text: t("Plan B approved ({n} moves)", { n: r.approved.length }), tone: "good" });
      onChange();
    } finally {
      setBusy(false);
    }
  };
  const latestPlanB = items.findIndex((a) => a.action?.type === "plan_b");
  return (
    <section className="card p-4">
      <p className="mb-3 flex items-center gap-2 font-semibold"><Bot className="size-5 text-brand" /> {t("What your agents did")}</p>
      <ol className="space-y-3">
        {items.slice(0, 12).map((a, i) => (
          <li key={a.id ?? i} className="flex gap-3">
            <AgentIcon agent={a.agent} small />
            <div className="min-w-0 flex-1">
              <p className="text-xs text-muted">{day(a.book_date, lang)}</p>
              <p className="text-sm">
                <span className={cx("mr-1.5 inline-block size-2 rounded-full align-middle", dot[a.tone] ?? "bg-muted")} />
                {a.text}
              </p>
              {a.action?.type === "remind" && (
                <Button size="sm" variant="secondary" className="mt-1.5" onClick={() => setRemind((a.action as { party: string }).party)}>
                  <MessageCircle className="size-4" /> {t("Send the firmer reminder")}
                </Button>
              )}
              {a.action?.type === "plan_b" && i === latestPlanB && (
                <Button size="sm" className="mt-1.5" onClick={planB} disabled={busy}><GitBranch className="size-4" /> {t("Approve Plan B")}</Button>
              )}
            </div>
          </li>
        ))}
      </ol>
      <ReminderSheet customer={remind} onClose={() => setRemind(null)} />
    </section>
  );
}

interface DayEv {
  date: string;
  balance: number;
  items: { kind: string; party?: string; amount?: number; in?: number; out?: number }[];
}

/** Demo only: live the next days and watch the agents react. */
export function FastForwardCard({ clock, onDone }: { clock: { date: string; days_moved: number }; onDone: () => void }) {
  const { t, lang } = useT();
  const { refresh } = useContext(DataVersion);
  const [open, setOpen] = useState(false);
  const [scenario, setScenario] = useState<"usual" | "defaults" | "pays">("defaults");
  const [days, setDays] = useState<DayEv[]>([]);
  const [acts, setActs] = useState<Activity[]>([]);
  const [running, setRunning] = useState(false);
  const [final, setFinal] = useState<{ headline?: string; changes?: { tone: string; text: string }[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [days, acts]);

  const go = async (n: number) => {
    setOpen(true);
    setDays([]);
    setActs([]);
    setFinal(null);
    setErr(null);
    setRunning(true);
    try {
      const f = await streamAgent<{ headline?: string; changes?: { tone: string; text: string }[] }>("/api/demo/fast-forward/stream", { days: n, scenario }, (e) => {
        if (e.type === "day") setDays((d) => [...d, e as unknown as DayEv]);
        if (e.type === "activity") setActs((a) => [...a, e as unknown as Activity]);
      }, lang);
      setFinal(f);
    } catch (x) {
      setErr(x instanceof Error ? x.message : String(x));
    } finally {
      setRunning(false);
    }
  };
  const reset = async () => {
    await post("/api/demo/reset", {});
    refresh();
    onDone();
  };
  const close = () => {
    setOpen(false);
    onDone();
  };
  const scenarios = [
    { v: "defaults" as const, l: t("The late customer never pays") },
    { v: "pays" as const, l: t("The late customer pays after the reminder") },
    { v: "usual" as const, l: t("Customers behave as usual") },
  ];
  return (
    <section className="card border-2 border-dashed border-brand/40 p-4">
      <p className="flex items-center gap-2 font-semibold"><FastForward className="size-5 text-brand" /> {t("Watch your agents over time")}</p>
      <p className="text-sm text-ink-2">
        {t("Demo only: live the next days with simulated payments, and see the agents check on each move, learn, and switch plans.")}
        {clock.days_moved > 0 && <> {t("Demo date: {date} ({n} days ahead).", { date: day(clock.date, lang), n: clock.days_moved })}</>}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        {scenarios.map((s) => (
          <button key={s.v} onClick={() => setScenario(s.v)} className={cx("rounded-full border px-3 py-1.5 text-sm font-medium transition", scenario === s.v ? "border-brand bg-brand text-on-brand" : "border-line bg-surface text-ink-2")}>
            {s.l}
          </button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={() => go(7)} disabled={running}><FastForward className="size-4" /> {t("+1 week")}</Button>
        <Button variant="secondary" onClick={() => go(14)} disabled={running}>{t("+2 weeks")}</Button>
        <Button variant="secondary" onClick={() => go(30)} disabled={running}>{t("+1 month")}</Button>
        {clock.days_moved > 0 && <Button variant="ghost" onClick={reset} disabled={running}><RotateCcw className="size-4" /> {t("Back to the start")}</Button>}
      </div>
      <Sheet open={open} onClose={close} title={t("Living the next days")}>
        <ol className="space-y-1.5">
          {days.map((d) => {
            const big = d.items.filter((i) => i.kind !== "typical");
            const dayActs = acts.filter((a) => a.book_date === d.date);
            return (
              <li key={d.date} className="rise">
                <div className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="w-14 shrink-0 text-xs text-muted">{day(d.date, lang)}</span>
                  <span className="min-w-0 flex-1 truncate text-ink-2">
                    {big.length === 0 ? t("Usual day") : big.map((i) => i.kind === "bill" ? `${i.party} ${short(i.amount)}` : i.kind === "paid_in" ? `+${short(i.amount)} ${i.party}` : i.kind === "overdraft" ? t("overdraft +{amt}", { amt: short(i.amount) }) : "").join(" · ")}
                  </span>
                  <span className={cx("num shrink-0 font-semibold", d.balance < 0 ? "text-bad" : "text-ink")}>{short(d.balance)}</span>
                </div>
                {dayActs.map((a, k) => (
                  <div key={k} className="mt-1.5 mb-2 flex gap-2 rounded-2xl bg-surface-2 p-2.5">
                    <AgentIcon agent={a.agent} small />
                    <p className="text-sm">{a.text}</p>
                  </div>
                ))}
              </li>
            );
          })}
          {running && <li className="flex items-center gap-2 text-sm text-ink-2"><Loader2 className="size-4 animate-spin" /> {t("Living the next day…")}</li>}
        </ol>
        {err && <p className="mt-3 text-sm text-bad">{err}</p>}
        {final && (
          <div className="rise mt-4 rounded-3xl bg-brand-50 p-4">
            <p className="font-semibold">{final.headline}</p>
            <ul className="mt-1 space-y-0.5 text-sm text-ink-2">{(final.changes ?? []).map((c, i) => <li key={i}>• {c.text}</li>)}</ul>
            <Button className="mt-3 w-full" onClick={close}>{t("See the new plan")} <ArrowRight className="size-4" /></Button>
          </div>
        )}
        <div ref={end} />
      </Sheet>
    </section>
  );
}

interface Track {
  status: string;
  message?: string;
  weeks: number;
  low_better_than_flat_pct: number | null;
  path_better_than_flat_pct: number | null;
  dips: number;
  dips_flagged: number;
  brier: number;
  false_alarms: number;
}

/** A small "how accurate is this?" card that links to the full track record. */
export function TrackRecordCard() {
  const { t } = useT();
  const { version } = useContext(DataVersion);
  const [r, setR] = useState<Track | null>(null);
  useEffect(() => {
    get<Track>("/api/track-record").then(setR).catch(() => setR(null));
  }, [version]);
  return (
    <Link href="/proof/" className="card block p-4 transition hover:shadow-md">
      <p className="flex items-center gap-2 font-semibold"><Target className="size-5 text-brand" /> {t("How accurate is this?")}</p>
      {!r ? (
        <p className="mt-1 flex items-center gap-2 text-sm text-ink-2"><Loader2 className="size-4 animate-spin" /> {t("Testing the forecast on your past weeks…")}</p>
      ) : r.status !== "ok" ? (
        <p className="mt-1 text-sm text-ink-2">{r.message}</p>
      ) : (
        <div className="mt-2 grid grid-cols-3 gap-2 text-center">
          <div className="rounded-2xl bg-surface-2 p-2">
            <p className="num text-xl font-bold text-good">{r.low_better_than_flat_pct != null ? pct(r.low_better_than_flat_pct) : "—"}</p>
            <p className="text-xs text-ink-2">{t("closer on the tightest day than guessing")}</p>
          </div>
          <div className="rounded-2xl bg-surface-2 p-2">
            <p className="num text-xl font-bold">{r.dips ? `${r.dips_flagged}/${r.dips}` : "—"}</p>
            <p className="text-xs text-ink-2">{t("real dips flagged in advance")}</p>
          </div>
          <div className="rounded-2xl bg-surface-2 p-2">
            <p className="num text-xl font-bold">{r.weeks}</p>
            <p className="text-xs text-ink-2">{t("past weeks tested")}</p>
          </div>
        </div>
      )}
      <p className="mt-2 flex items-center gap-1 text-sm font-semibold text-brand">{t("See the track record")} <ArrowRight className="size-4" /></p>
    </Link>
  );
}
