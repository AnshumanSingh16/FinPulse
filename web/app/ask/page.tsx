"use client";

import { AlertTriangle, ArrowDownLeft, ArrowUp, ArrowUpRight, BookOpen, HandCoins, Landmark, Mic, ReceiptText, RotateCcw, Store } from "lucide-react";
import Link from "next/link";
import { Component, Suspense, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AgentAnswer, type AgentResult, applyEvent, emptyLive, type Live, LiveCard, streamAgent } from "@/components/agent";
import { AiModeChip, AiSetupSheet } from "@/components/ai-setup";
import { DataVersion } from "@/components/data-version";
import { useToast } from "@/components/fx";
import { type Kind, useQuickEntry } from "@/components/quick-entry";
import { BrandMark } from "@/components/shell";
import { cx } from "@/components/ui";
import { get, post } from "@/lib/api";
import { short } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { AiStatus } from "@/lib/types";

interface Snapshot {
  cash: number | null;
  as_of_label: string;
  to_collect: number;
  collect_overdue: number;
  to_pay: number;
  pay_overdue: number;
}
interface EntryEvent {
  entry_id: string;
  entry_kind: Kind;
  message: string;
  amount: number;
  party: string;
  undone: boolean;
}
type Item =
  | { id: number; at: string; role: "owner"; kind: "text"; data: { text: string } }
  | { id: number; at: string; role: "munshi"; kind: "answer" | "checkup"; data: AgentResult }
  | { id: number; at: string; role: "event"; kind: "entry"; data: EntryEvent };

interface Thread {
  business: string;
  is_demo: boolean;
  snapshot: Snapshot;
  items: Item[];
  checkup_due: boolean;
  ai: AiStatus;
}

const ENTRY_CHIPS: { kind: Kind; label: string; I: React.ElementType }[] = [
  { kind: "sale", label: "Sale", I: Store },
  { kind: "payment_in", label: "Paisa aaya", I: ArrowDownLeft },
  { kind: "credit_sale", label: "Udhaar diya", I: HandCoins },
  { kind: "expense", label: "Kharcha", I: ArrowUpRight },
  { kind: "bill", label: "Supplier bill", I: ReceiptText },
];
const ASK_CHIPS = ["Will I run short of cash?", "Can I afford a ₹2 lakh purchase?", "Who owes me money?"];
const ASK_CHIPS_HI = ["क्या कैश कम पड़ेगा?", "क्या मैं ₹2 लाख की ख़रीद कर सकता हूँ?", "किस पर उधारी बाकी है?"];
const ENTRY_ICON: Record<string, React.ElementType> = { sale: Store, payment_in: ArrowDownLeft, credit_sale: HandCoins, expense: ArrowUpRight, bill: ReceiptText, payment_out: ArrowUpRight };
const MONEY_IN: string[] = ["sale", "payment_in"];

function dayKey(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

export default function AskPage() {
  return (
    <Suspense>
      <AskChat />
    </Suspense>
  );
}

function AskChat() {
  const { t, lang } = useT();
  const { version, state } = useContext(DataVersion);
  const qe = useQuickEntry();
  const [thread, setThread] = useState<Thread | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [live, setLive] = useState<Live | null>(null);
  const [liveTitle, setLiveTitle] = useState<string | undefined>();
  const [err, setErr] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [listening, setListening] = useState(false);
  const [setup, setSetup] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const busy = live !== null;

  const load = useCallback(() => get<Thread>("/api/chat").then(setThread).catch((e) => setErr(String(e))), []);

  useEffect(() => {
    load();
  }, [load, version]);

  useEffect(() => {
    // braces matter: newer browsers return a Promise from scrollIntoView, and an effect must return nothing (or a cleanup function)
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread?.items.length, live, pending]);

  const params = useSearchParams();
  const sentQ = useRef(false);
  useEffect(() => {
    const q = params.get("q");
    if (q && thread && !sentQ.current) {
      sentQ.current = true;
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params, thread]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setErr(null);
    setPending(q);
    setLiveTitle(undefined);
    setLive(emptyLive());
    try {
      await streamAgent("/api/ask/stream", { question: q, conversation_id: "main", log: true }, (e) => setLive((l) => (l ? applyEvent(l, e) : l)), lang, "/api/ask");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLive(null);
      setPending(null);
      await load();
    }
  };

  const listen = () => {
    const W = window as unknown as { SpeechRecognition?: new () => any; webkitSpeechRecognition?: new () => any }; // eslint-disable-line @typescript-eslint/no-explicit-any
    const SR = W.SpeechRecognition ?? W.webkitSpeechRecognition;
    if (!SR) return;
    const r = new SR();
    r.lang = lang === "hi" ? "hi-IN" : "en-IN";
    r.onresult = (e: { results: { [i: number]: { [j: number]: { transcript: string } } } }) => send(e.results[0][0].transcript);
    r.onend = () => setListening(false);
    setListening(true);
    r.start();
  };

  const items = thread?.items ?? [];
  const lastAnswer = [...items].reverse().find((i) => i.role === "munshi") as Extract<Item, { role: "munshi" }> | undefined;
  const lastIsAnswer = items.length > 0 && items[items.length - 1].role === "munshi";
  const askChips = lastIsAnswer && lastAnswer?.data.suggestions?.length ? lastAnswer.data.suggestions : lang === "hi" ? ASK_CHIPS_HI : ASK_CHIPS;

  return (
    <div className="flex min-h-0 flex-1 flex-col">

      <div className="no-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-4 sm:px-4" role="log" aria-live="polite">
        {thread && <Welcome business={thread.business} ai={thread.ai} onSetup={() => setSetup(true)} />}
        {items.map((it, i) => (
          <div key={it.id}>
            {(i === 0 || dayKey(items[i - 1].at) !== dayKey(it.at)) && <DaySep iso={it.at} />}
            <Safe><Bubble item={it} onUndone={load} /></Safe>
          </div>
        ))}
        {pending && <OwnerBubble text={pending} />}
        {live && (
          <BotRow>
            <LiveCard live={live} title={liveTitle} />
          </BotRow>
        )}
        {err && (
          <div className="flex items-start gap-2 rounded-2xl bg-bad-50 p-3 text-sm text-bad">
            <AlertTriangle className="size-5 shrink-0" /> {err}
          </div>
        )}
        <div ref={end} />
      </div>

      <div className="no-print shrink-0 border-t border-line bg-canvas/95 px-3 pt-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))] backdrop-blur sm:px-4">
        <div className="no-scrollbar -mx-3 mb-2 flex gap-2 overflow-x-auto px-3 sm:-mx-4 sm:px-4">
          {ENTRY_CHIPS.map(({ kind, label, I }) => (
            <button key={kind} onClick={() => qe.open({ kind })} className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink shadow-sm transition hover:border-brand">
              <I className="size-4 text-brand" /> {t(label)}
            </button>
          ))}
          <span className="mx-1 w-px shrink-0 bg-line" />
          {askChips.slice(0, 3).map((q) => (
            <button key={q} onClick={() => send(q)} disabled={busy} className="shrink-0 rounded-full bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand transition hover:bg-brand/15 disabled:opacity-50">
              {q}
            </button>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="card flex items-end gap-1.5 rounded-3xl p-1.5 pl-4">
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
            placeholder={t("Ask FinPilot…")}
            className="max-h-32 min-h-10 flex-1 resize-none bg-transparent py-2.5 outline-none placeholder:text-muted"
            aria-label={t("Ask FinPilot")}
          />
          <button type="button" onClick={listen} aria-label={t("Speak")}
            className={cx("grid size-10 shrink-0 place-items-center rounded-full transition", listening ? "animate-pulse bg-bad text-white" : "text-ink-2 hover:bg-surface-2")}>
            <Mic className="size-5" />
          </button>
          <button type="submit" disabled={!input.trim() || busy} aria-label={t("Send")} className="grid size-10 shrink-0 place-items-center rounded-full bg-brand text-on-brand transition disabled:opacity-40">
            <ArrowUp className="size-5" />
          </button>
        </form>
      </div>
      <AiSetupSheet open={setup} onClose={() => setSetup(false)} />
    </div>
  );
}

function Welcome({ business, ai, onSetup }: { business: string; ai: AiStatus; onSetup: () => void }) {
  const { t } = useT();
  return (
    <BotRow>
      <div className="card max-w-xl space-y-2 p-4 text-[0.95rem]">
        <p className="font-semibold">{t("Hi! I'm FinPilot, the cash autopilot for {shop}.", { shop: business })}</p>
        <p className="text-ink-2">{t("Ask me anything about your money, or tell me what happened and I'll record it. Every answer comes from your own records, checked.")}</p>
        <ul className="space-y-1 text-sm text-ink-2">
          <li>💬 <i>“Why will cash dip in November?”</i> · <i>“Can I afford a ₹2 lakh machine?”</i> · <i>“Who pays late?”</i></li>
          <li>✍️ <i>“Received 50,000 from Zenith Realty”</i> · <i>“Paid rent 95,000”</i></li>
        </ul>
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <AiModeChip onClick={onSetup} />
          {!ai.enabled && <button onClick={onSetup} className="text-xs font-semibold text-brand underline underline-offset-2">{t("Make me smarter with a free AI key")}</button>}
        </div>
      </div>
    </BotRow>
  );
}

function DaySep({ iso }: { iso: string }) {
  const { t, lang } = useT();
  const d = new Date(iso);
  const today = new Date();
  const y = new Date();
  y.setDate(today.getDate() - 1);
  const label = dayKey(iso) === dayKey(today.toISOString()) ? t("Today") : dayKey(iso) === dayKey(y.toISOString()) ? t("Yesterday") : d.toLocaleDateString(lang === "hi" ? "hi-IN" : "en-IN", { day: "numeric", month: "short", year: "numeric" });
  return (
    <div className="my-2 flex justify-center">
      <span className="rounded-full bg-surface-2 px-3 py-0.5 text-xs font-medium text-muted">{label}</span>
    </div>
  );
}

function BotRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <BrandMark size="sm" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

function OwnerBubble({ text, at }: { text: string; at?: string }) {
  const { lang } = useT();
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] rounded-3xl rounded-br-md bg-brand px-4 py-2.5 text-on-brand shadow-sm sm:max-w-[75%]">
        {text}
        {at && <span className="ml-2 align-bottom text-[0.65rem] text-on-brand/70">{new Date(at).toLocaleTimeString(lang === "hi" ? "hi-IN" : "en-IN", { hour: "numeric", minute: "2-digit" })}</span>}
      </p>
    </div>
  );
}

function Bubble({ item, onUndone }: { item: Item; onUndone: () => void }) {
  const { t } = useT();
  if (item.role === "owner") return <OwnerBubble text={item.data.text} at={item.at} />;
  if (item.role === "event") return <EntryLine e={item.data} at={item.at} onUndone={onUndone} />;
  return (
    <BotRow>
      {item.kind === "checkup" && <p className="mb-1 text-xs font-semibold tracking-wide text-brand uppercase">{t("Morning check-up")}</p>}
      <AgentAnswer a={item.data} conversation="main" />
    </BotRow>
  );
}

/** A khata line in the thread: every entry, from chat or the + buttons, lands here with Undo. */
function EntryLine({ e, at, onUndone }: { e: EntryEvent; at: string; onUndone: () => void }) {
  const { t, lang } = useT();
  const toast = useToast();
  const { refresh } = useContext(DataVersion);
  const I = ENTRY_ICON[e.entry_kind] ?? BookOpen;
  const incoming = MONEY_IN.includes(e.entry_kind);
  const undo = async () => {
    try {
      await post(`/api/entries/${e.entry_id}/undo`, {});
      toast.show({ text: t("Undone") });
      refresh();
      onUndone();
    } catch (x) {
      toast.show({ text: x instanceof Error ? x.message : String(x), tone: "bad" });
    }
  };
  return (
    <div className="flex justify-center">
      <div className={cx("flex max-w-[92%] items-center gap-2.5 rounded-2xl border border-dashed px-3 py-2 text-sm", e.undone ? "border-line text-muted line-through" : "border-brand/30 bg-surface")}>
        <span className={cx("grid size-7 shrink-0 place-items-center rounded-full", incoming ? "bg-good-50 text-good" : "bg-caution-50 text-caution")}>
          <I className="size-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="text-[0.65rem] font-semibold tracking-wide text-muted uppercase no-underline">{t("Written in khata")} · {new Date(at).toLocaleTimeString(lang === "hi" ? "hi-IN" : "en-IN", { hour: "numeric", minute: "2-digit" })}</span>
          <span className="block font-medium text-ink">{e.message}</span>
        </span>
        {!e.undone && (
          <button onClick={undo} className="inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold text-ink-2 hover:bg-surface-2" aria-label={t("Undo")}>
            <RotateCcw className="size-3.5" /> {t("Undo")}
          </button>
        )}
      </div>
    </div>
  );
}

/** One message that can't be shown must never take the whole chat down. */
class Safe extends Component<{ children: React.ReactNode }, { err: string | null }> {
  state = { err: null as string | null };
  static getDerivedStateFromError(e: Error) {
    return { err: e?.message || String(e) };
  }
  componentDidCatch(e: Error) {
    console.error(e);
  }
  render() {
    if (this.state.err) return <p className="rounded-2xl bg-caution-50 px-3 py-2 text-xs text-caution">Couldn't show this message ({this.state.err}).</p>;
    return this.props.children;
  }
}
