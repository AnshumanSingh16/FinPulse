"use client";

import {
  AlertTriangle, Bot, Brain, CalendarClock, Check, CheckCheck, ChevronDown, CircleDashed, Circle, Copy, HandCoins, ListChecks, Loader2, MessageCircle,
  PiggyBank, Plus, RotateCcw, ShieldCheck, Tags, Trash2, X,
} from "lucide-react";
import { useContext, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { EvidenceSheet } from "./evidence";
import { del, get, post, API } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Evidence } from "@/lib/types";
import { DataVersion } from "./data-version";
import { confetti, useToast } from "./fx";
import { Button, cx, Pill, Sheet } from "./ui";

export type ActionKind = "record_entry" | "send_reminder" | "create_goal" | "set_budget" | "record_promise" | "recategorise";

export interface DraftAction {
  id: string;
  kind: ActionKind;
  title: string;
  summary: string;
  state: "pending" | "done" | "cancelled" | "expired";
  preview: {
    would_settle?: { id: string; amount: number; full: boolean }[];
    more_than_due?: number;
    per_month?: number | null;
    months_left?: number | null;
    spent_this_month?: number;
    suggested_from_recent_average?: number | null;
    total?: number;
    invoices?: { item_id: string; amount: number; due_date: string }[];
    oldest_days_late?: number;
    owner_notes?: string[];
    count?: number;
    from?: string[];
  };
  text?: string | null;
  whatsapp?: string | null;
  phone_saved?: boolean | null;
  result?: { message?: string; id?: string } | null;
}

export interface PlanStep {
  title: string;
  status: "todo" | "doing" | "done" | "skipped";
}

export interface AgentResult {
  answer: string;
  mode: "ai" | "rule-based";
  verified: boolean;
  has_figures: boolean;
  warnings: string[];
  steps: { label: string; tool: string; ok: boolean; checks: number }[];
  plan: PlanStep[];
  notes: string[];
  remembered: { id: number; fact: string }[];
  evidence: Evidence[];
  actions: DraftAction[];
  suggestions: string[];
  conversation_id?: string;
  ran_at?: string;
}

export interface Live {
  mode: "ai" | "rule-based" | null;
  steps: { label: string; done: boolean; ok: boolean }[];
  notes: string[];
  plan: PlanStep[];
  fallback?: string;
}

export const emptyLive = (): Live => ({ mode: null, steps: [], notes: [], plan: [] });

/** Fold one server-sent progress event into the live view. */
export function applyEvent(l: Live, e: Record<string, unknown>): Live {
  if (e.type === "start") return { ...l, mode: e.mode as Live["mode"] };
  if (e.type === "note") return { ...l, notes: [...l.notes, String(e.text)] };
  if (e.type === "plan") return { ...l, plan: e.steps as PlanStep[] };
  if (e.type === "fallback") return { ...l, mode: "rule-based", fallback: String(e.reason) };
  if (e.tool === "update_plan") return l;
  if (e.type === "tool_start") return { ...l, steps: [...l.steps, { label: String(e.label), done: false, ok: true }] };
  if (e.type === "tool_done") {
    const steps = [...l.steps];
    let k = steps.length - 1;
    while (k >= 0 && steps[k].done) k--;
    if (k >= 0) steps[k] = { ...steps[k], done: true, ok: Boolean(e.ok) };
    return { ...l, steps };
  }
  return l;
}

/** POST to a streaming endpoint and feed its server-sent events to `on`; resolves with the final payload. */
export async function streamAgent<T>(path: string, body: object, on: (e: Record<string, unknown>) => void, lang: string, fallback?: string): Promise<T> {
  const res = await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json", "X-Lang": lang }, body: JSON.stringify(body) });
  if (!res.ok || !res.body) {
    if (res.status === 404 && fallback) return post<T>(fallback, body);
    let msg = `Something went wrong (${res.status}).`;
    try {
      const j = await res.json();
      if (j?.detail) msg = String(j.detail);
    } catch {}
    throw new Error(msg);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const e = JSON.parse(line.slice(6));
      if (e.type === "final") return e.data as T;
      if (e.type === "error") throw new Error(String(e.message));
      on(e);
    }
  }
  throw new Error("The answer was interrupted. Please try again.");
}

export function PlanChecklist({ plan, compact, collapsible }: { plan: PlanStep[]; compact?: boolean; collapsible?: boolean }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  if (!plan.length) return null;
  const done = plan.filter((s) => s.status === "done").length;
  if (collapsible && !open && done === plan.length) {
    return (
      <button onClick={() => setOpen(true)} className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand" aria-expanded={false}>
        <ListChecks className="size-4" /> {t("Plan finished: {d} of {n} steps done", { d: done, n: plan.length })} <ChevronDown className="size-3.5" />
      </button>
    );
  }
  return (
    <div className={cx("rounded-2xl border border-line bg-surface-2/60", compact ? "p-3" : "p-4")}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ink-2 uppercase">
          <ListChecks className="size-4 text-brand" /> {t("Agent's plan")}
        </p>
        <span className="text-xs text-muted">{t("{d} of {n} done", { d: done, n: plan.length })}</span>
      </div>
      <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full bg-brand transition-all duration-500" style={{ width: `${(done / plan.length) * 100}%` }} />
      </div>
      <ol className="space-y-1">
        {plan.map((s, i) => (
          <li key={i} className="flex items-center gap-2 text-sm">
            {s.status === "done" ? (
              <span className="grid size-5 place-items-center rounded-full bg-brand text-on-brand"><Check className="size-3.5" /></span>
            ) : s.status === "doing" ? (
              <CircleDashed className="size-5 animate-spin text-brand" />
            ) : s.status === "skipped" ? (
              <X className="size-5 text-muted" />
            ) : (
              <Circle className="size-5 text-line" />
            )}
            <span className={cx(s.status === "done" ? "text-ink" : s.status === "doing" ? "font-medium text-ink" : "text-muted", s.status === "skipped" && "line-through")}>{s.title}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function LiveCard({ live, title }: { live: Live; title?: string }) {
  const { t } = useT();
  const recent = live.steps.slice(-4);
  return (
    <div className="card max-w-3xl space-y-3 p-4" aria-live="polite">
      <div className="flex items-center gap-2 text-sm font-semibold text-ink">
        <Loader2 className="size-4 animate-spin text-brand" />
        {title ?? (live.mode === "ai" ? t("The AI agent is working…") : t("Working it out…"))}
      </div>
      {live.fallback && <p className="rounded-xl bg-caution-50 px-3 py-2 text-xs text-caution">{live.fallback}</p>}
      {live.notes.length > 0 && (
        <ul className="space-y-1 border-l-2 border-brand/30 pl-3">
          {live.notes.map((n, i) => (
            <li key={i} className="text-sm text-ink-2 italic">{n}</li>
          ))}
        </ul>
      )}
      <PlanChecklist plan={live.plan} compact />
      <ol className="space-y-1.5">
        {recent.map((s, i) => (
          <li key={live.steps.length - recent.length + i} className="rise flex items-center gap-2 text-sm">
            {s.done ? (
              <span className={cx("grid size-5 place-items-center rounded-full", s.ok ? "bg-good-50 text-good" : "bg-caution-50 text-caution")}>
                {s.ok ? <Check className="size-3.5" /> : <AlertTriangle className="size-3" />}
              </span>
            ) : (
              <CircleDashed className="size-5 animate-spin text-brand" />
            )}
            <span className={s.done ? "text-ink" : "text-ink-2"}>{s.label}</span>
          </li>
        ))}
        {live.steps.length === 0 && live.plan.length === 0 && live.notes.length === 0 && (
          <li className="flex items-center gap-2 text-sm text-ink-2">
            <span className="flex gap-1">
              <span className="dot size-1.5 rounded-full bg-brand" />
              <span className="dot size-1.5 rounded-full bg-brand" />
              <span className="dot size-1.5 rounded-full bg-brand" />
            </span>
            {t("Reading your question")}
          </li>
        )}
      </ol>
    </div>
  );
}

const ACTION_ICON: Record<ActionKind, React.ElementType> = { record_entry: HandCoins, send_reminder: MessageCircle, create_goal: PiggyBank, set_budget: CalendarClock, record_promise: CalendarClock, recategorise: Tags };
const ACTION_GRAD: Record<ActionKind, string> = { record_entry: "grad-mint", send_reminder: "grad-berry", create_goal: "grad-sunset", set_budget: "grad-ocean", record_promise: "grad-violet", recategorise: "grad-night" };
const inr = (n: number) => "₹" + Math.round(n).toLocaleString("en-IN");

export function ActionCard({ action, conversation, onDone }: { action: DraftAction; conversation?: string; onDone?: () => void }) {
  const { t } = useT();
  const toast = useToast();
  const { refresh } = useContext(DataVersion);
  const [state, setState] = useState<"pending" | "busy" | "done" | "cancelled" | "undone" | "expired">(action.state === "pending" ? "pending" : action.state);
  const [msg, setMsg] = useState<string | null>(action.result?.message ?? null);
  const [entryId, setEntryId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showText, setShowText] = useState(false);
  useEffect(() => {
    setState(action.state === "pending" ? "pending" : action.state);
    setMsg(action.result?.message ?? null);
  }, [action.state, action.result]);
  const I = ACTION_ICON[action.kind] ?? HandCoins;
  const p = action.preview || {};

  const decide = async (decision: "confirm" | "cancel") => {
    setState("busy");
    setErr(null);
    try {
      const r = await post<{ state: string; message?: string; id?: string; open?: string; cleared_all?: boolean }>(`/api/agent/actions/${action.id}`, { conversation_id: conversation, decision });
      if (decision === "cancel") {
        setState("cancelled");
        onDone?.();
        return;
      }
      if (r.open) window.open(r.open, "_blank", "noopener");
      setMsg(r.message ?? null);
      if (r.id) setEntryId(r.id);
      if (r.cleared_all) confetti();
      setState("done");
      onDone?.();
      if (action.kind !== "send_reminder") refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setState("pending");
    }
  };
  const undo = async () => {
    if (!entryId) return;
    await post(`/api/entries/${entryId}/undo`, {});
    setState("undone");
    refresh();
  };

  return (
    <div className={cx("card max-w-3xl overflow-hidden", state === "pending" && "ring-2 ring-brand/25", (state === "cancelled" || state === "expired") && "opacity-70")}>
      <div className="flex items-start gap-3 p-4">
        <span className={cx("grid size-10 shrink-0 place-items-center rounded-2xl", ACTION_GRAD[action.kind] ?? "grad-mint")}>
          <I className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold tracking-wide text-brand uppercase">{state === "pending" || state === "busy" ? t("Ready for you to confirm") : t(action.title)}</p>
          <p className="font-semibold text-ink">{action.summary}</p>
          <div className="mt-1 space-y-0.5 text-sm text-ink-2">
            {p.would_settle && p.would_settle.length > 0 && <p>{t("Clears")}: {p.would_settle.map((s) => `${s.id} (${inr(s.amount)}${s.full ? "" : ", part"})`).join(", ")}</p>}
            {p.more_than_due ? <p>{t("{amt} more than they owe", { amt: inr(p.more_than_due) })}</p> : null}
            {p.per_month && p.months_left ? <p>{t("Save {amt} a month for {m} months", { amt: inr(p.per_month), m: p.months_left })}</p> : null}
            {p.spent_this_month != null && <p>{t("Spent so far this month: {amt}", { amt: inr(p.spent_this_month) })}</p>}
            {p.invoices && <p>{p.invoices.map((i) => i.item_id).join(", ")} · {t("oldest {d} days late", { d: p.oldest_days_late ?? 0 })}</p>}
            {p.count != null && p.total != null && <p>{t("{n} line(s), {amt}", { n: p.count, amt: inr(p.total) })}{p.from?.length ? ` · ${t("now")}: ${p.from.join(", ")}` : ""}</p>}
            {p.owner_notes && p.owner_notes.length > 0 && (
              <p className="rounded-lg bg-caution-50 px-2 py-1 text-caution">
                <Brain className="mr-1 inline size-3.5" /> {t("You told me")}: “{p.owner_notes.join("”, “")}”
              </p>
            )}
          </div>
          {action.kind === "send_reminder" && action.text && state === "pending" && (
            showText ? (
              <pre className="mt-2 max-h-40 overflow-y-auto rounded-2xl bg-surface-2 p-3 font-sans text-sm whitespace-pre-wrap text-ink">{action.text}</pre>
            ) : (
              <button onClick={() => setShowText(true)} className="mt-1 text-sm font-semibold text-brand underline underline-offset-2">{t("Preview message")}</button>
            )
          )}
          {action.kind === "send_reminder" && action.phone_saved === false && state === "pending" && (
            <p className="mt-1 text-xs text-muted">{t("No phone number saved — WhatsApp will ask you to pick the contact.")}</p>
          )}
        </div>
      </div>
      {err && <p className="mx-4 mb-3 rounded-xl bg-bad-50 px-3 py-2 text-sm text-bad">{err}</p>}
      <div className="flex flex-wrap items-center gap-2 border-t border-line bg-surface-2/60 px-4 py-3">
        {state === "pending" || state === "busy" ? (
          <>
            <Button onClick={() => decide("confirm")} disabled={state === "busy"}>
              {action.kind === "send_reminder" ? <MessageCircle className="size-4" /> : <Check className="size-4" />}
              {action.kind === "send_reminder" ? t("Open WhatsApp") : t("Confirm")}
            </Button>
            {action.kind === "send_reminder" && action.text && (
              <Button variant="secondary" onClick={() => { navigator.clipboard?.writeText(action.text ?? ""); toast.show({ text: t("Copied") }); }}>
                <Copy className="size-4" /> {t("Copy text")}
              </Button>
            )}
            <Button variant="ghost" onClick={() => decide("cancel")} disabled={state === "busy"}>
              <X className="size-4" /> {t("Not now")}
            </Button>
          </>
        ) : state === "done" ? (
          <>
            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-good">
              <Check className="size-4" /> {msg ?? t("Done")}
            </span>
            {entryId && (
              <Button size="sm" variant="ghost" className="ml-auto" onClick={undo}>
                <RotateCcw className="size-4" /> {t("Undo")}
              </Button>
            )}
          </>
        ) : (
          <span className="text-sm text-muted">
            {state === "undone" ? t("Undone") : state === "expired" ? t("Replaced by a newer check-up.") : t("Cancelled — nothing was saved.")}
          </span>
        )}
      </div>
    </div>
  );
}

/** A list of drafted cards with "Approve all" for the ones that don't need the owner to send something themselves. */
export function ActionList({ actions, conversation, onChange }: { actions: DraftAction[]; conversation?: string; onChange?: () => void }) {
  const { t } = useT();
  const toast = useToast();
  const { refresh } = useContext(DataVersion);
  const [items, setItems] = useState(actions);
  const [busy, setBusy] = useState(false);
  useEffect(() => setItems(actions), [actions]);
  const batch = items.filter((a) => a.state === "pending" && a.kind !== "send_reminder");
  const approveAll = async () => {
    setBusy(true);
    try {
      const r = await post<{ done: number; results: { id: string; ok: boolean; message?: string }[] }>("/api/agent/approve-all", { ids: batch.map((a) => a.id), conversation_id: conversation });
      const byId = Object.fromEntries(r.results.map((x) => [x.id, x]));
      setItems((xs) => xs.map((a) => (byId[a.id]?.ok ? { ...a, state: "done", result: { message: byId[a.id].message } } : a)));
      toast.show({ text: t("Approved {n}", { n: r.done }), tone: "good" });
      refresh();
      onChange?.();
    } finally {
      setBusy(false);
    }
  };
  if (!items.length) return null;
  return (
    <div className="space-y-3">
      {batch.length > 1 && (
        <div className="flex max-w-3xl flex-wrap items-center gap-3 rounded-2xl bg-brand-50 px-4 py-3">
          <CheckCheck className="size-5 text-brand" />
          <p className="flex-1 text-sm text-ink">{t("{n} actions are ready. Reminders open WhatsApp one by one.", { n: batch.length })}</p>
          <Button size="sm" onClick={approveAll} disabled={busy}>
            <CheckCheck className="size-4" /> {t("Approve all ({n})", { n: batch.length })}
          </Button>
        </div>
      )}
      {items.map((a) => (
        <ActionCard key={a.id} action={a} conversation={conversation} onDone={onChange} />
      ))}
    </div>
  );
}

interface Memory {
  id: number;
  text: string;
  created_at: string;
}

export function MemorySheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useT();
  const [items, setItems] = useState<Memory[] | null>(null);
  const [text, setText] = useState("");
  useEffect(() => {
    if (open) get<Memory[]>("/api/agent/memory").then(setItems).catch(() => setItems([]));
  }, [open]);
  const add = async () => {
    if (!text.trim()) return;
    setItems(await post<Memory[]>("/api/agent/memory", { text }));
    setText("");
  };
  return (
    <Sheet open={open} onClose={onClose} title={t("What the agent remembers")}>
      <p className="mb-4 text-sm text-ink-2">
        {t("Preferences and facts you told the agent. It follows them — for example it won't draft reminders for someone you said not to remind. Figures always come from your records, never from here.")}
      </p>
      <ul className="space-y-2">
        {items?.length === 0 && <li className="rounded-2xl bg-surface-2 p-3 text-sm text-muted">{t("Nothing yet. Try: “Remember that Ramesh is my brother — never remind him.”")}</li>}
        {items?.map((m) => (
          <li key={m.id} className="flex items-start gap-3 rounded-2xl border border-line p-3">
            <Brain className="mt-0.5 size-4 shrink-0 text-brand" />
            <span className="flex-1 text-sm">{m.text}</span>
            <button onClick={async () => setItems(await del<Memory[]>(`/api/agent/memory/${m.id}`))} className="rounded-full p-1 text-muted hover:bg-bad-50 hover:text-bad" aria-label={t("Forget")}>
              <Trash2 className="size-4" />
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex gap-2">
        <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder={t("Add something to remember…")}
          className="h-11 flex-1 rounded-2xl border border-line bg-surface px-4 text-sm outline-none focus:border-brand" />
        <Button onClick={add} disabled={!text.trim()}>
          <Plus className="size-4" /> {t("Add")}
        </Button>
      </div>
    </Sheet>
  );
}

/** One finished agent run: the answer, its plan, trust badges, the steps and evidence, what it remembered, and the drafted cards. */
export function AgentAnswer({ a, conversation, hidePlan }: { a: AgentResult; conversation?: string; hidePlan?: boolean }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [ev, setEv] = useState<Evidence | null>(null);
  return (
    <div className="max-w-3xl space-y-3">
      <div className="card p-5">
        {!hidePlan && a.plan.length > 0 && (
          <div className="mb-4">
            <PlanChecklist plan={a.plan} compact collapsible />
          </div>
        )}
        <div className="prose-answer text-[0.97rem] leading-relaxed text-ink">
          <ReactMarkdown>{a.answer}</ReactMarkdown>
        </div>
        {a.remembered.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {a.remembered.map((m) => (
              <span key={m.id} className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand">
                <Brain className="size-3.5" /> {t("Remembered")}: {m.fact}
              </span>
            ))}
          </div>
        )}
        {a.warnings.length > 0 && (
          <div className="mt-3 space-y-1 rounded-2xl bg-caution-50 p-3 text-sm text-caution">
            {a.warnings.map((w) => (
              <p key={w} className="flex gap-2">
                <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {w}
              </p>
            ))}
          </div>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
          {a.has_figures &&
            (a.verified ? (
              <Pill tone="good">
                <ShieldCheck className="size-3.5" /> {t("Every figure checked against your records")}
              </Pill>
            ) : (
              <Pill tone="caution">
                <AlertTriangle className="size-3.5" /> {t("Some figures couldn't be checked")}
              </Pill>
            ))}
          {a.mode === "ai" ? (
            <Pill tone="info">
              <Bot className="size-3.5" /> {t("AI agent")}
            </Pill>
          ) : (
            <Pill>{t("Built-in answer (no AI)")}</Pill>
          )}
          {a.steps.length > 0 && (
            <button onClick={() => setOpen((o) => !o)} className="ml-auto inline-flex items-center gap-1 text-sm font-medium text-ink-2 hover:text-ink" aria-expanded={open}>
              {t("How I worked this out ({n})", { n: a.steps.length })} <ChevronDown className={cx("size-4 transition", open && "rotate-180")} />
            </button>
          )}
        </div>
        {open && (
          <div className="mt-3 space-y-3">
            {a.notes.length > 0 && (
              <ul className="space-y-1 border-l-2 border-brand/30 pl-3">
                {a.notes.map((n, i) => (
                  <li key={i} className="text-sm text-ink-2 italic">{n}</li>
                ))}
              </ul>
            )}
            <ol className="space-y-1.5">
              {a.steps.map((s, i) => (
                <li key={i} className="flex items-center gap-2 text-sm">
                  <span className={cx("grid size-5 place-items-center rounded-full", s.ok ? "bg-good-50 text-good" : "bg-caution-50 text-caution")}>
                    {s.ok ? <Check className="size-3.5" /> : <AlertTriangle className="size-3" />}
                  </span>
                  {s.label}
                  {s.checks > 0 && <span className="text-xs text-muted">· {t("{n} checks passed", { n: s.checks })}</span>}
                </li>
              ))}
            </ol>
            {a.evidence.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {a.evidence.map((e) => (
                  <button key={e.title} onClick={() => setEv(e)} className="rounded-full border border-line px-3 py-1.5 text-xs font-medium text-ink-2 hover:border-brand hover:text-brand">
                    <ShieldCheck className="mr-1 inline size-3.5" />
                    {e.title}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <ActionList actions={a.actions} conversation={conversation} />
      {ev && <EvidenceSheet evidence={ev} open={!!ev} onClose={() => setEv(null)} />}
    </div>
  );
}
