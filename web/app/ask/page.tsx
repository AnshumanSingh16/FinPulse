"use client";

import { AlertTriangle, ArrowUp, Check, ChevronDown, ShieldCheck, Sparkles } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useContext, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { DataVersion } from "@/components/data-version";
import { EvidenceSheet } from "@/components/evidence";
import { cx, Pill } from "@/components/ui";
import { post } from "@/lib/api";
import type { Evidence } from "@/lib/types";

interface Answer {
  conversation_id: string;
  answer: string;
  mode: "ai" | "rule-based";
  verified: boolean;
  has_figures: boolean;
  warnings: string[];
  steps: { label: string; ok: boolean; checks: number }[];
  evidence: Evidence[];
}

type Msg = { role: "user"; text: string } | { role: "assistant"; data: Answer } | { role: "error"; text: string };

const SUGGESTIONS = [
  "How is my business doing?",
  "Why did my costs go up last month?",
  "Who owes me money?",
  "Will I have enough cash for the next 3 months?",
  "Any double payments or odd expenses?",
  "Can I afford a ₹12 lakh machine on a loan at 11% for 3 years? It would save ₹45,000 a month.",
];

const THINKING = ["Reading your records", "Running the numbers", "Double-checking every figure"];

export default function AskPage() {
  return (
    <Suspense>
      <Ask />
    </Suspense>
  );
}

function Ask() {
  const params = useSearchParams();
  const { state, version } = useContext(DataVersion);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState(0);
  const conv = useRef<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const sentQ = useRef(false);

  useEffect(() => {
    setMsgs([]);
    conv.current = null;
  }, [version]);

  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth", block: "end" }), [msgs, busy]);

  useEffect(() => {
    if (!busy) return;
    setPhase(0);
    const t = setInterval(() => setPhase((p) => Math.min(p + 1, THINKING.length - 1)), 900);
    return () => clearInterval(t);
  }, [busy]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const a = await post<Answer>("/api/ask", { question: q, conversation_id: conv.current });
      conv.current = a.conversation_id;
      setMsgs((m) => [...m, { role: "assistant", data: a }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "error", text: e instanceof Error ? e.message : String(e) }]);
    } finally {
      setBusy(false);
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

  return (
    <div className="flex min-h-[calc(100dvh-8.5rem)] flex-col lg:min-h-[calc(100dvh-3rem)]">
      <div className="flex-1 space-y-5 pb-6">
        {msgs.length === 0 && !busy && (
          <div className="mx-auto max-w-2xl pt-6 text-center sm:pt-12">
            <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-brand-50 text-brand">
              <Sparkles className="size-7" aria-hidden />
            </span>
            <h1 className="mt-4 text-2xl font-semibold tracking-tight">Ask anything about your business</h1>
            <p className="mt-2 text-ink-2">Answers come straight from your records, and every figure is double-checked before you see it.</p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => send(s)} className="rounded-full border border-line bg-surface px-4 py-2 text-left text-sm text-ink shadow-sm transition hover:border-brand hover:text-brand">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex justify-end">
              <p className="max-w-[85%] rounded-3xl rounded-br-lg bg-brand px-4 py-2.5 text-white sm:max-w-[70%]">{m.text}</p>
            </div>
          ) : m.role === "error" ? (
            <div key={i} className="flex items-start gap-2 rounded-2xl bg-bad-50 p-4 text-sm text-bad">
              <AlertTriangle className="size-5 shrink-0" /> {m.text}
            </div>
          ) : (
            <AnswerCard key={i} a={m.data} />
          ),
        )}
        {busy && (
          <div className="card inline-flex items-center gap-3 px-4 py-3 text-sm text-ink-2">
            <span className="flex gap-1">
              <span className="dot size-1.5 rounded-full bg-brand" />
              <span className="dot size-1.5 rounded-full bg-brand" />
              <span className="dot size-1.5 rounded-full bg-brand" />
            </span>
            {THINKING[phase]}…
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
            placeholder="Ask about sales, costs, cash, customers, a purchase…"
            className="max-h-36 min-h-10 flex-1 resize-none bg-transparent py-2.5 outline-none placeholder:text-muted"
            aria-label="Your question"
          />
          <button type="submit" disabled={!input.trim() || busy} className="grid size-10 shrink-0 place-items-center rounded-full bg-brand text-white transition disabled:opacity-40" aria-label="Send">
            <ArrowUp className="size-5" />
          </button>
        </form>
        <p className="mt-2 text-center text-xs text-muted">
          {state?.ai.enabled
            ? "AI mode: your question and the relevant figures are sent to Anthropic to write the answer. Your files are not."
            : "Offline mode: answers come from FinPilot's built-in rules. Nothing leaves this computer."}{" "}
          Not financial advice.
        </p>
      </div>
    </div>
  );
}

function AnswerCard({ a }: { a: Answer }) {
  const [open, setOpen] = useState(false);
  const [ev, setEv] = useState<Evidence | null>(null);
  return (
    <div className="max-w-3xl">
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
                <ShieldCheck className="size-3.5" /> Every figure checked against your records
              </Pill>
            ) : (
              <Pill tone="caution">
                <AlertTriangle className="size-3.5" /> Some figures couldn&apos;t be checked
              </Pill>
            ))}
          {a.mode === "rule-based" && <Pill>Built-in answer (no AI)</Pill>}
          {a.steps.length > 0 && (
            <button onClick={() => setOpen((o) => !o)} className="ml-auto inline-flex items-center gap-1 text-sm font-medium text-ink-2 hover:text-ink" aria-expanded={open}>
              How I worked this out <ChevronDown className={cx("size-4 transition", open && "rotate-180")} />
            </button>
          )}
        </div>
        {open && (
          <div className="mt-3 space-y-3">
            <ol className="space-y-1.5">
              {a.steps.map((s, i) => (
                <li key={i} className="flex items-center gap-2 text-sm">
                  <span className={cx("grid size-5 place-items-center rounded-full", s.ok ? "bg-good-50 text-good" : "bg-caution-50 text-caution")}>
                    {s.ok ? <Check className="size-3.5" /> : <AlertTriangle className="size-3" />}
                  </span>
                  {s.label}
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
      {ev && <EvidenceSheet evidence={ev} open={!!ev} onClose={() => setEv(null)} />}
    </div>
  );
}
