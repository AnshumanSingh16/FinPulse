"use client";

import {
  AlertTriangle, ArrowUp, BookUser, Bot, CalendarClock, Check, ChevronDown, CircleDashed, Copy, HandCoins, Lightbulb, Loader2, MessageCircle, Mic,
  PiggyBank, Plus, RotateCcw, ShieldCheck, Sparkles, Store, Target, TrendingUp, Wallet, X,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useContext, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { AiModeChip, AiSetupSheet } from "@/components/ai-setup";
import { DataVersion } from "@/components/data-version";
import { EvidenceSheet } from "@/components/evidence";
import { confetti, useToast } from "@/components/fx";
import { Button, cx, Pill } from "@/components/ui";
import { API, post } from "@/lib/api";
import { useT } from "@/lib/i18n";
import type { Evidence } from "@/lib/types";

interface DraftAction {
  id: string;
  kind: "record_entry" | "send_reminder" | "create_goal" | "set_budget";
  title: string;
  summary: string;
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
  };
  text?: string | null;
  whatsapp?: string | null;
  phone_saved?: boolean | null;
}

interface Answer {
  conversation_id: string;
  answer: string;
  mode: "ai" | "rule-based";
  verified: boolean;
  has_figures: boolean;
  warnings: string[];
  steps: { label: string; tool: string; ok: boolean; checks: number }[];
  notes: string[];
  evidence: Evidence[];
  actions: DraftAction[];
  suggestions: string[];
}

interface LiveStep {
  label: string;
  done: boolean;
  ok: boolean;
}
interface Live {
  mode: "ai" | "rule-based" | null;
  steps: LiveStep[];
  notes: string[];
  fallback?: string;
}

type Msg = { role: "user"; text: string } | { role: "assistant"; data: Answer } | { role: "error"; text: string };

const CAPABILITIES = [
  { I: Lightbulb, grad: "grad-hero", title: "Plan my day", q: "What should I do today?", q_hi: "आज मुझे क्या करना चाहिए?" },
  { I: BookUser, grad: "grad-violet", title: "Khata & udhaar", q: "Who owes me money, and who pays late?", q_hi: "किस पर उधारी बाकी है, और कौन देर से चुकाता है?" },
  { I: TrendingUp, grad: "grad-mint", title: "Profit & costs", q: "Am I making money? Why did costs go up last month?", q_hi: "क्या मैं मुनाफ़ा कमा रहा हूँ? पिछले महीने खर्च क्यों बढ़ा?" },
  { I: Wallet, grad: "grad-ocean", title: "Cash ahead", q: "Will I have enough cash for the next 3 months?", q_hi: "अगले 90 दिन का कैश अनुमान बताओ" },
  { I: Target, grad: "grad-sunset", title: "What-ifs", q: "Can I raise prices by 5%?", q_hi: "दाम 5% बढ़ाऊँ तो?" },
  { I: Store, grad: "grad-berry", title: "Do it for me", q: "Add a sale of ₹500 cash", q_hi: "₹500 की नकद बिक्री जोड़ो" },
];

const MORE = [
  "Who are my best customers?",
  "How did this week go?",
  "What's my health score?",
  "How much GST should I keep aside?",
  "Should I hire a helper for ₹15,000 a month?",
  "Can I afford a ₹12 lakh machine on a loan at 11% for 3 years? It would save ₹45,000 a month.",
  "Remind Metro Foods",
  "Save ₹60,000 for a new fridge by March",
];
const MORE_HI = [
  "मेरे सबसे अच्छे ग्राहक कौन हैं?",
  "इस हफ़्ते कैसा रहा?",
  "मेरा सेहत स्कोर क्या है?",
  "GST के लिए कितना अलग रखूँ?",
  "₹15,000 महीने पर हेल्पर रखूँ?",
  "क्या मैं ₹12 लाख की मशीन 11% पर 3 साल के लोन पर ले सकता हूँ? हर महीने ₹45,000 बचेंगे",
  "Metro Foods को याद दिलाओ",
];

export default function AskPage() {
  return (
    <Suspense>
      <Ask />
    </Suspense>
  );
}

/** POST /api/ask/stream and feed server-sent events to `on`. Falls back to /api/ask if streaming isn't available. */
async function askStream(body: object, on: (e: Record<string, unknown>) => void, lang: string): Promise<Answer> {
  const res = await fetch(API + "/api/ask/stream", { method: "POST", headers: { "Content-Type": "application/json", "X-Lang": lang }, body: JSON.stringify(body) });
  if (!res.ok || !res.body) {
    if (res.status === 404) return post<Answer>("/api/ask", body);
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
      if (e.type === "final") return e.data as Answer;
      if (e.type === "error") throw new Error(String(e.message));
      on(e);
    }
  }
  throw new Error("The answer was interrupted. Please try again.");
}

function Ask() {
  const { t, lang } = useT();
  const [listening, setListening] = useState(false);
  const params = useSearchParams();
  const { state } = useContext(DataVersion);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [live, setLive] = useState<Live | null>(null);
  const [setup, setSetup] = useState(false);
  const conv = useRef<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const sentQ = useRef(false);
  const busy = live !== null;

  // a new chat when the owner switches between the demo and their own books
  useEffect(() => {
    setMsgs([]);
    conv.current = null;
  }, [state?.source]);

  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth", block: "end" }), [msgs, live]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text: q }]);
    setLive({ mode: null, steps: [], notes: [] });
    try {
      const a = await askStream(
        { question: q, conversation_id: conv.current },
        (e) =>
          setLive((l) => {
            if (!l) return l;
            if (e.type === "start") return { ...l, mode: e.mode as Live["mode"] };
            if (e.type === "note") return { ...l, notes: [...l.notes, String(e.text)] };
            if (e.type === "fallback") return { ...l, mode: "rule-based", fallback: String(e.reason) };
            if (e.type === "tool_start") return { ...l, steps: [...l.steps, { label: String(e.label), done: false, ok: true }] };
            if (e.type === "tool_done") {
              const steps = [...l.steps];
              let k = steps.length - 1;
              while (k >= 0 && steps[k].done) k--;
              if (k >= 0) steps[k] = { ...steps[k], done: true, ok: Boolean(e.ok) };
              return { ...l, steps };
            }
            return l;
          }),
        lang,
      );
      conv.current = a.conversation_id;
      setMsgs((m) => [...m, { role: "assistant", data: a }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "error", text: e instanceof Error ? e.message : String(e) }]);
    } finally {
      setLive(null);
    }
  };

  useEffect(() => {
    const q = params.get("q");
    if (q && !sentQ.current) {
      sentQ.current = true;
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  const lastAssistant = [...msgs].reverse().find((m) => m.role === "assistant") as { role: "assistant"; data: Answer } | undefined;

  return (
    <div className="flex min-h-[calc(100dvh-8.5rem)] flex-col lg:min-h-[calc(100dvh-3rem)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="grad-hero grid size-9 place-items-center rounded-xl text-[#ffd27a]">
            <Sparkles className="size-5" aria-hidden />
          </span>
          <div>
            <h1 className="text-lg leading-tight">{t("Ask FinPilot")}</h1>
            <p className="text-xs text-muted">{t("Your shop assistant")}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <AiModeChip onClick={() => setSetup(true)} />
          {msgs.length > 0 && (
            <Button size="sm" variant="secondary" onClick={() => { setMsgs([]); conv.current = null; }} disabled={busy}>
              <Plus className="size-4" /> {t("New chat")}
            </Button>
          )}
        </div>
      </div>

      <div className="flex-1 space-y-5 pb-6">
        {msgs.length === 0 && !busy && <Welcome onAsk={send} onSetup={() => setSetup(true)} />}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <p className="max-w-[85%] rounded-3xl rounded-br-lg bg-brand px-4 py-2.5 text-on-brand shadow-sm sm:max-w-[70%]">{m.text}</p>
            </div>
          ) : m.role === "error" ? (
            <div key={i} className="flex items-start gap-2 rounded-2xl bg-bad-50 p-4 text-sm text-bad">
              <AlertTriangle className="size-5 shrink-0" /> {m.text}
            </div>
          ) : (
            <AnswerCard key={i} a={m.data} />
          ),
        )}
        {live && <LiveCard live={live} />}
        {!busy && lastAssistant && lastAssistant.data.suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2 pl-1">
            {lastAssistant.data.suggestions.map((s) => (
              <button key={s} onClick={() => send(s)} className="rounded-full border border-brand/30 bg-brand-50 px-3.5 py-1.5 text-sm font-medium text-brand transition hover:border-brand">
                {s}
              </button>
            ))}
          </div>
        )}
        <div ref={end} />
      </div>

      <div className="sticky bottom-16 z-20 -mx-4 bg-gradient-to-t from-canvas via-canvas to-canvas/0 px-4 pt-4 pb-4 sm:-mx-6 sm:px-6 lg:bottom-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="card flex items-end gap-2 rounded-3xl p-2 pl-5"
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            rows={1}
            placeholder={t("Ask anything…")}
            className="max-h-36 min-h-10 flex-1 resize-none bg-transparent py-2.5 outline-none placeholder:text-muted"
            aria-label={t("Your question")}
          />
          <button
            type="button"
            onClick={() => {
              const W = window as unknown as { SpeechRecognition?: new () => any; webkitSpeechRecognition?: new () => any }; // eslint-disable-line @typescript-eslint/no-explicit-any
              const SR = W.SpeechRecognition ?? W.webkitSpeechRecognition;
              if (!SR) return;
              const r = new SR();
              r.lang = lang === "hi" ? "hi-IN" : "en-IN";
              r.onresult = (e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => send(e.results[0][0].transcript);
              r.onend = () => setListening(false);
              setListening(true);
              r.start();
            }}
            className={cx("grid size-10 shrink-0 place-items-center rounded-full transition", listening ? "animate-pulse bg-bad text-white" : "text-ink-2 hover:bg-surface-2")}
            aria-label={t("Speak your question")}
          >
            <Mic className="size-5" />
          </button>
          <button type="submit" disabled={!input.trim() || busy} className="grid size-10 shrink-0 place-items-center rounded-full bg-brand text-on-brand transition disabled:opacity-40" aria-label={t("Send")}>
            <ArrowUp className="size-5" />
          </button>
        </form>
        <p className="mt-2 text-center text-xs text-muted">
          {t(state?.ai.enabled
            ? "AI agent: your question and the figures its tools work out are sent to the AI provider. Your files are not."
            : "Built-in answers: nothing leaves this computer.")}{" "}
          {t("Nothing is saved or sent until you confirm.")} {t("Not financial advice.")}
        </p>
      </div>
      <AiSetupSheet open={setup} onClose={() => setSetup(false)} />
    </div>
  );
}

function Welcome({ onAsk, onSetup }: { onAsk: (q: string) => void; onSetup: () => void }) {
  const { t, lang } = useT();
  const { state } = useContext(DataVersion);
  return (
    <div className="mx-auto max-w-3xl pt-4 sm:pt-6">
      {state && !state.ai.enabled && (
        <div className="mb-6 flex flex-wrap items-center gap-4 rounded-3xl border border-dashed border-brand/40 bg-brand-50 p-4">
          <span className="grid size-10 place-items-center rounded-2xl bg-surface text-brand shadow-sm">
            <Bot className="size-5" />
          </span>
          <div className="min-w-0 flex-1 text-sm">
            <p className="font-semibold text-ink">{state.ai.has_key ? t("The AI agent is paused") : t("Answers now come from built-in rules")}</p>
            <p className="hidden text-ink-2 sm:block">{t("They work offline for common questions. Turn on the AI agent to ask anything in your own words — it plans, uses 21 tools and checks every figure.")}</p>
          </div>
          <Button size="sm" onClick={onSetup}>
            <Sparkles className="size-4" /> {state.ai.has_key ? t("Turn AI back on") : t("Set up AI")}
          </Button>
        </div>
      )}
      <div className="text-center">
        <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">{t("What can I help with today?")}</h2>
        <p className="mx-auto mt-2 max-w-xl text-ink-2">
          {t("I look through your khata, bank and bills, run the numbers with tested calculations, check every figure, and can prepare entries and reminders for you to confirm.")}
        </p>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {CAPABILITIES.map(({ I, grad, title, q, q_hi }) => (
          <button key={title} onClick={() => onAsk(lang === "hi" ? q_hi : q)} className="card group flex flex-col gap-3 p-4 text-left transition hover:-translate-y-0.5 hover:border-brand/40">
            <span className={cx("grid size-10 place-items-center rounded-2xl", grad)}>
              <I className="size-5" aria-hidden />
            </span>
            <span>
              <span className="block font-semibold text-ink">{t(title)}</span>
              <span className="mt-0.5 block text-sm text-ink-2">“{lang === "hi" ? q_hi : t(q)}”</span>
            </span>
          </button>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {(lang === "hi" ? MORE_HI : MORE).map((s) => (
          <button key={s} onClick={() => onAsk(s)} className="rounded-full border border-line bg-surface px-3.5 py-1.5 text-left text-sm text-ink-2 transition hover:border-brand hover:text-brand">
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function LiveCard({ live }: { live: Live }) {
  const { t } = useT();
  return (
    <div className="card max-w-3xl p-4" aria-live="polite">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
        <Loader2 className="size-4 animate-spin text-brand" />
        {live.mode === "ai" ? t("The AI agent is working…") : t("Working it out…")}
      </div>
      {live.fallback && <p className="mb-2 rounded-xl bg-caution-50 px-3 py-2 text-xs text-caution">{live.fallback}</p>}
      <ol className="space-y-1.5">
        {live.notes.map((n, i) => (
          <li key={`n${i}`} className="text-sm text-ink-2 italic">{n}</li>
        ))}
        {live.steps.map((s, i) => (
          <li key={i} className="rise flex items-center gap-2 text-sm">
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
        {live.steps.length === 0 && live.notes.length === 0 && (
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

function AnswerCard({ a }: { a: Answer }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [ev, setEv] = useState<Evidence | null>(null);
  return (
    <div className="max-w-3xl space-y-3">
      <div className="card p-5">
        <div className="prose-answer text-[0.97rem] leading-relaxed text-ink">
          <ReactMarkdown>{a.answer}</ReactMarkdown>
        </div>
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
              {t("{n} steps · how I worked this out", { n: a.steps.length })} <ChevronDown className={cx("size-4 transition", open && "rotate-180")} />
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
      {a.actions.map((x) => (
        <ActionCard key={x.id} action={x} conversation={a.conversation_id} />
      ))}
      {ev && <EvidenceSheet evidence={ev} open={!!ev} onClose={() => setEv(null)} />}
    </div>
  );
}

const ACTION_ICON = { record_entry: HandCoins, send_reminder: MessageCircle, create_goal: PiggyBank, set_budget: CalendarClock };
const ACTION_GRAD = { record_entry: "grad-mint", send_reminder: "grad-berry", create_goal: "grad-sunset", set_budget: "grad-ocean" };
const inr = (n: number) => "₹" + Math.round(n).toLocaleString("en-IN");

function ActionCard({ action, conversation }: { action: DraftAction; conversation: string }) {
  const { t } = useT();
  const toast = useToast();
  const { refresh } = useContext(DataVersion);
  const [state, setState] = useState<"pending" | "busy" | "done" | "cancelled" | "undone">("pending");
  const [msg, setMsg] = useState<string | null>(null);
  const [entryId, setEntryId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const I = ACTION_ICON[action.kind];
  const p = action.preview || {};

  const decide = async (decision: "confirm" | "cancel") => {
    setState("busy");
    setErr(null);
    try {
      const r = await post<{ state: string; message?: string; id?: string; open?: string; cleared_all?: boolean }>(`/api/ask/action/${action.id}`, { conversation_id: conversation, decision });
      if (decision === "cancel") {
        setState("cancelled");
        return;
      }
      if (r.open) window.open(r.open, "_blank", "noopener");
      setMsg(r.message ?? null);
      if (r.id) setEntryId(r.id);
      if (r.cleared_all) confetti();
      setState("done");
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
    <div className={cx("card max-w-3xl overflow-hidden", state === "pending" && "ring-2 ring-brand/25")}>
      <div className="flex items-start gap-3 p-4">
        <span className={cx("grid size-10 shrink-0 place-items-center rounded-2xl", ACTION_GRAD[action.kind])}>
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
          </div>
          {action.kind === "send_reminder" && action.text && (
            <pre className="mt-2 max-h-40 overflow-y-auto rounded-2xl bg-surface-2 p-3 font-sans text-sm whitespace-pre-wrap text-ink">{action.text}</pre>
          )}
          {action.kind === "send_reminder" && action.phone_saved === false && <p className="mt-1 text-xs text-muted">{t("No phone number saved — WhatsApp will ask you to pick the contact.")}</p>}
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
          <span className="text-sm text-muted">{state === "undone" ? t("Undone") : t("Cancelled — nothing was saved.")}</span>
        )}
      </div>
    </div>
  );
}
