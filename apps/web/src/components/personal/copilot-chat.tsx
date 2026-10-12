"use client";

import { AlertTriangle, Bot, Loader2, Send, Sparkles, User, Wrench } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type { CopilotToolCall } from "@/lib/personal/agents/copilot";
import type { AgentEvent } from "@/lib/personal/agents/types";
import { copilot } from "@/lib/personal/client";
import { cn } from "@/lib/utils";

import { EventFeed, PlanTracker } from "./agent-activity";
import { usePersonal } from "./provider";
import { Loading, ModeStrip, Notice } from "./ui";

type Turn =
  | { role: "user"; text: string }
  | {
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

const SUGGESTIONS = [
  "Can I afford a ₹75 lakh house?",
  "What if my income drops by 20%?",
  "Compare a ₹15 lakh car with a ₹20 lakh car.",
  "How much should I save before buying?",
  "Explain why this option is risky.",
];

export function CopilotChat() {
  const { state, refresh } = usePersonal();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    setTurns((t) => [...t, { role: "user", text: message }, { role: "assistant", text: "", pending: true, unverified: [], tools: [], events: [] }]);
    const patch = (fn: (a: Extract<Turn, { role: "assistant" }>) => Extract<Turn, { role: "assistant" }>) =>
      setTurns((t) => {
        const copy = [...t];
        const last = copy[copy.length - 1];
        if (last?.role === "assistant") copy[copy.length - 1] = fn(last);
        return copy;
      });
    try {
      await copilot(message, (item) => {
        if (item.type === "tool") patch((a) => ({ ...a, tools: [...a.tools, item.call] }));
        else if (item.type === "event") patch((a) => ({ ...a, events: [...a.events, item.event] }));
        else if (item.type === "run") patch((a) => ({ ...a, runId: item.runId, runStatus: item.status }));
        else if (item.type === "message") patch((a) => ({ ...a, text: item.text, mode: item.mode, notice: item.notice, unverified: item.unverifiedFigures, pending: false }));
        else if (item.type === "error") setError(item.message);
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The copilot request failed");
      patch((a) => ({ ...a, pending: false, text: a.text || "No reply — see the error above." }));
    } finally {
      setBusy(false);
    }
  }

  if (!state) return <Loading />;
  const profileEmpty = state.profile.values.monthlyIncome === null;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div className="flex flex-col gap-1">
          <div className="text-xs font-medium tracking-wide text-primary uppercase">AI Financial Copilot</div>
          <h1 className="text-2xl font-semibold tracking-tight">Ask, and the agents get to work</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">The copilot answers by calling FinPulse&apos;s tools — the full affordability workflow, stress scenarios, comparisons and savings plans — and shows every call.</p>
        </div>
        <ModeStrip status={state.status} />
      </header>

      {profileEmpty ? (
        <Notice tone="info" title="Your profile is empty">
          Most questions need your income, expenses and savings. <Link href="/profile" className="text-primary hover:underline">Add them</Link> or use <span className="font-medium">Try Demo</span> on the Overview page.
        </Notice>
      ) : null}

      <div className="flex min-h-[420px] flex-col gap-4 rounded-xl border bg-card p-4 sm:p-5">
        {turns.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 py-8 text-center">
            <Bot className="size-8 text-primary" />
            <p className="max-w-md text-sm text-muted-foreground">Try one of these:</p>
            <div className="flex max-w-2xl flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => send(s)} className="rounded-full border px-3 py-1.5 text-xs text-muted-foreground transition hover:border-primary/50 hover:text-foreground">
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <ol className="flex flex-col gap-5">
            {turns.map((t, i) => (
              <li key={i} className={cn("flex gap-3", t.role === "user" && "flex-row-reverse")}>
                <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-full", t.role === "user" ? "bg-muted" : "bg-primary/15 text-primary")}>
                  {t.role === "user" ? <User className="size-3.5" /> : <Bot className="size-3.5" />}
                </span>
                {t.role === "user" ? (
                  <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-primary/15 px-3.5 py-2 text-sm">{t.text}</div>
                ) : (
                  <div className="flex min-w-0 max-w-[90%] flex-col gap-2">
                    {t.tools.length ? (
                      <div className="flex flex-wrap gap-1.5">
                        {t.tools.map((c) => (
                          <span key={c.id} title={c.summary} className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-mono text-[11px]", c.status === "ok" ? "text-muted-foreground" : "border-status-critical/40 text-chart-negative")}>
                            <Wrench className="size-3" /> {c.tool} · {c.summary}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {t.events.length ? (
                      <details className="rounded-lg border bg-background/40 p-3" open={t.pending}>
                        <summary className="cursor-pointer text-xs text-muted-foreground select-none">Multi-agent workflow ({t.events.length} events){t.runStatus ? ` · ${t.runStatus.replace("_", " ")}` : ""}</summary>
                        <div className="mt-2 grid gap-3 lg:grid-cols-2">
                          <PlanTracker events={t.events} running={t.pending} />
                          <EventFeed events={t.events} />
                        </div>
                      </details>
                    ) : null}
                    {t.pending ? (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="size-4 animate-spin" /> Working…
                      </div>
                    ) : (
                      <div className="rounded-2xl rounded-tl-sm border bg-background/50 px-3.5 py-2.5 text-sm whitespace-pre-line">{t.text}</div>
                    )}
                    {!t.pending ? (
                      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                        {t.mode === "ai" ? (
                          <span className="inline-flex items-center gap-1 text-primary"><Sparkles className="size-3" /> AI reply grounded in tool outputs</span>
                        ) : (
                          <span>Rule-based reply (no AI) using the same tools</span>
                        )}
                        {t.runId && t.runStatus === "completed" ? (
                          <Link href={`/afford?run=${t.runId}`} className="text-primary hover:underline">Open full results, evidence & checklist →</Link>
                        ) : null}
                      </div>
                    ) : null}
                    {t.notice ? <p className="text-[11px] text-muted-foreground">{t.notice}</p> : null}
                    {t.unverified.length ? (
                      <p className="flex items-center gap-1 text-[11px] text-status-warning">
                        <AlertTriangle className="size-3" /> {t.unverified.length} figure(s) in this reply did not match any tool output: {t.unverified.join(", ")}. Treat them with caution.
                      </p>
                    ) : null}
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
        <div ref={endRef} />
      </div>

      {error ? <Notice tone="error">{error}</Notice> : null}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
        className="sticky bottom-4 flex gap-2 rounded-xl border bg-card p-2 shadow-lg"
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} maxLength={1000} placeholder='e.g. "Can I afford a ₹20 lakh car?"' className="h-10 min-w-0 flex-1 bg-transparent px-2 text-sm outline-none" aria-label="Message the copilot" />
        <Button type="submit" disabled={busy || !input.trim()} className="h-10">
          {busy ? <Loader2 className="animate-spin" /> : <Send />} <span className="hidden sm:inline">Send</span>
        </Button>
      </form>
    </div>
  );
}
