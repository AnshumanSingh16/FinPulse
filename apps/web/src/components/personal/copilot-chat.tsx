"use client";

import { AlertTriangle, ArrowRight, Loader2, Send, Wrench } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { CopilotToolCall } from "@/lib/personal/agents/copilot";
import type { AgentEvent } from "@/lib/personal/agents/types";
import { copilot } from "@/lib/personal/client";
import { cn } from "@/lib/utils";

import { AgentTimeline, EventFeed } from "./agent-activity";
import { AgentGlyph, Kicker, PulseMark } from "./kit";
import { usePersonal } from "./provider";
import { Disclosure, Loading, ModeStrip, Notice } from "./ui";

type Assistant = {
  role: "assistant";
  text: string;
  pending: boolean;
  mode?: "ai" | "rule_based";
  notice?: string;
  unverified: string[];
  tools: CopilotToolCall[];
  events: AgentEvent[];
  runId?: string;
  runStatus?: string;
};
type Turn = { role: "user"; text: string; about?: string } | Assistant;

const SUGGESTIONS = [
  "Am I on track for my goals?",
  "Can I afford a ₹75 lakh house?",
  "Rent or buy: ₹75 lakh flat, rent ₹25,000",
  "Prepay or invest: ₹40 lakh loan at 8.5% with 15 years left, ₹5 lakh bonus",
  "Build an emergency fund",
  "Stress-test my finances",
];

/** What the copilot can actually do: these are the tools it is given. */
const CAPABILITIES = [
  { agent: "orchestrator", text: "Run the full multi-agent affordability analysis" },
  { agent: "planner", text: "Review your goal plan and monthly check-ins" },
  { agent: "risk", text: "Stress-test a purchase or your finances today" },
  { agent: "analysis", text: "Rent vs buy, prepay vs invest, EMIs and savings" },
  { agent: "verification", text: "Explain the risks and rules behind a result" },
] as const;

export function CopilotChat() {
  const { state, refresh } = usePersonal();
  const params = useSearchParams();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [about, setAbout] = useState<string>(params.get("run") ?? "");
  const endRef = useRef<HTMLDivElement>(null);
  const autoSent = useRef(false);

  useEffect(() => {
    if (turns.length) endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    const aboutLabel = state?.runs.find((r) => r.id === about)?.label;
    setTurns((t) => [
      ...t,
      { role: "user", text: message, about: aboutLabel },
      { role: "assistant", text: "", pending: true, unverified: [], tools: [], events: [] },
    ]);
    const patch = (fn: (a: Assistant) => Assistant) =>
      setTurns((t) => {
        const copy = [...t];
        const last = copy[copy.length - 1];
        if (last?.role === "assistant") copy[copy.length - 1] = fn(last);
        return copy;
      });
    try {
      await copilot(
        message,
        (item) => {
          if (item.type === "tool") patch((a) => ({ ...a, tools: [...a.tools, item.call] }));
          else if (item.type === "event")
            patch((a) => ({ ...a, events: [...a.events, item.event] }));
          else if (item.type === "run") {
            patch((a) => ({ ...a, runId: item.runId, runStatus: item.status }));
            if (item.status === "completed") setAbout(item.runId);
          } else if (item.type === "message")
            patch((a) => ({
              ...a,
              text: item.text,
              mode: item.mode,
              notice: item.notice,
              unverified: item.unverifiedFigures,
              pending: false,
            }));
          else if (item.type === "error") setError(item.message);
        },
        about || undefined,
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The request failed");
      patch((a) => ({ ...a, pending: false, text: a.text || "No reply — see the error above." }));
    } finally {
      setBusy(false);
    }
  }

  // A prompt handed over from the home page (?q=…) is sent once, as if typed.
  const q = params.get("q");
  useEffect(() => {
    if (!q || autoSent.current || !state) return;
    autoSent.current = true;
    void send(q);
    // send is stable enough for a one-time hand-over; state gates it until data has loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, state]);

  if (!state) return <Loading />;
  const completed = state.runs.filter((r) => r.status === "completed");
  const profileEmpty = state.profile.values.monthlyIncome === null;

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="flex min-w-0 flex-col gap-4">
        <header className="flex items-start gap-3">
          <PulseMark size="lg" active={busy} />
          <div className="flex flex-col gap-0.5">
            <Kicker>FinPulse AI</Kicker>
            <h1 className="text-[24px] leading-tight font-extrabold sm:text-[28px]">
              Ask FinPulse
            </h1>
            <ModeStrip status={state.status} />
          </div>
        </header>

        {profileEmpty ? (
          <Notice tone="info" title="Your profile is empty">
            Most answers need your income, spending and savings.{" "}
            <Link href="/profile" className="font-semibold text-brand-700 hover:underline">
              Add them
            </Link>{" "}
            or try the demo from Home.
          </Notice>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <label htmlFor="about" className="text-ink-500">
            Talking about
          </label>
          <select
            id="about"
            value={about}
            onChange={(e) => setAbout(e.target.value)}
            className="h-9 max-w-full rounded-lg border border-line-strong bg-surface px-2.5 text-[13px] font-medium"
          >
            <option value="">Your finances in general</option>
            {completed.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label} ·{" "}
                {new Date(r.createdAt).toLocaleTimeString("en-IN", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </option>
            ))}
          </select>
        </div>

        <section
          className="flex min-h-[380px] flex-col gap-5 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-6"
          aria-label="Conversation"
        >
          {turns.length === 0 ? (
            <div className="flex flex-1 flex-col justify-center gap-4 py-6">
              <p className="text-[15px] font-semibold">Try asking</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => send(s)}
                    className="group flex items-center justify-between gap-2 rounded-xl border border-line px-3.5 py-3 text-left text-[14px] text-ink-700 transition-colors hover:border-line-strong hover:bg-surface-sunken"
                  >
                    {s}
                    <ArrowRight
                      className="size-4 shrink-0 text-ink-400 transition group-hover:translate-x-0.5"
                      aria-hidden
                    />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <ol className="flex flex-col gap-6">
              {turns.map((t, i) =>
                t.role === "user" ? (
                  <li key={i} className="flex flex-col items-end gap-1">
                    <p className="max-w-[85%] rounded-2xl rounded-br-md bg-ink-900 px-4 py-2.5 text-[15px] text-white">
                      {t.text}
                    </p>
                    {t.about ? (
                      <span className="text-[11px] text-ink-400">about {t.about}</span>
                    ) : null}
                  </li>
                ) : (
                  <li key={i} className="fp-rise flex gap-3">
                    <PulseMark size="sm" active={t.pending} />
                    <div className="flex min-w-0 flex-1 flex-col gap-2.5">
                      {t.tools.length ? (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-[11px] font-semibold tracking-wide text-ink-400 uppercase">
                            Used
                          </span>
                          {t.tools.map((c) => (
                            <span
                              key={c.id}
                              title={c.summary}
                              className={cn(
                                "inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-mono text-[11px]",
                                c.status === "ok"
                                  ? "bg-agent-50 text-agent-700"
                                  : "bg-danger-50 text-danger-text",
                              )}
                            >
                              <Wrench className="size-3" aria-hidden /> {c.tool}
                              <span className="font-sans text-ink-500">· {c.summary}</span>
                            </span>
                          ))}
                        </div>
                      ) : null}
                      {t.events.length ? (
                        <div className="rounded-xl border border-line p-4">
                          <div className="mb-3 flex items-center justify-between gap-2">
                            <span className="text-[13px] font-semibold">Multi-agent analysis</span>
                            {t.runId && t.runStatus === "completed" ? (
                              <Link
                                href={`/afford?run=${t.runId}`}
                                className="text-[12.5px] font-semibold text-brand-700 hover:underline"
                              >
                                Open full results →
                              </Link>
                            ) : null}
                          </div>
                          <AgentTimeline events={t.events} running={t.pending} />
                          <Disclosure title="Technical log" className="mt-1">
                            <EventFeed events={t.events} />
                          </Disclosure>
                        </div>
                      ) : null}
                      {t.pending ? (
                        <p className="flex items-center gap-2 text-[14px] text-ink-500">
                          <Loader2 className="size-4 animate-spin" aria-hidden /> Working on it…
                        </p>
                      ) : (
                        <p className="text-[15px] leading-relaxed whitespace-pre-line text-ink-900">
                          {t.text}
                        </p>
                      )}
                      {!t.pending ? (
                        <p className="text-[11.5px] text-ink-400">
                          {t.mode === "ai"
                            ? "AI answer grounded in tool outputs"
                            : "Rule-based answer using the same tools (AI off)"}
                        </p>
                      ) : null}
                      {t.unverified.length ? (
                        <p className="flex items-start gap-1 text-[12px] text-caution-text">
                          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                          {t.unverified.length} figure(s) didn&apos;t match any tool output:{" "}
                          {t.unverified.join(", ")}. Treat them with caution.
                        </p>
                      ) : null}
                    </div>
                  </li>
                ),
              )}
            </ol>
          )}
          <div ref={endRef} />
        </section>

        {error ? <Notice tone="error">{error}</Notice> : null}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send(input);
          }}
          className="sticky bottom-[calc(4.75rem+env(safe-area-inset-bottom))] flex items-center gap-2 rounded-2xl border border-line-strong bg-surface p-1.5 pl-4 shadow-md focus-within:border-brand-600 lg:bottom-4"
        >
          <label htmlFor="ask" className="sr-only">
            Message FinPulse
          </label>
          <input
            id="ask"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            maxLength={1000}
            placeholder={
              about ? "Ask a follow-up about this analysis…" : "Ask about any money decision…"
            }
            className="h-11 min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-ink-400"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            aria-label="Send"
            className="flex size-11 items-center justify-center rounded-xl bg-ink-900 text-white transition disabled:opacity-40"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Send className="size-4" aria-hidden />
            )}
          </button>
        </form>
      </div>

      <aside className="hidden flex-col gap-4 rounded-2xl border border-line bg-surface p-5 shadow-xs lg:flex">
        <h2 className="text-[15px] font-bold">What FinPulse can do here</h2>
        <ul className="flex flex-col gap-3">
          {CAPABILITIES.map((c) => (
            <li key={c.text} className="flex items-center gap-3 text-[13.5px] text-ink-700">
              <AgentGlyph agent={c.agent} size="sm" />
              {c.text}
            </li>
          ))}
        </ul>
        <p className="border-t border-line pt-3 text-[12px] leading-relaxed text-ink-500">
          Every number comes from FinPulse&apos;s calculation tools. With AI on, any figure in a
          reply that doesn&apos;t match a tool output is flagged. FinPulse can&apos;t submit
          applications or move money.
        </p>
      </aside>
    </div>
  );
}
