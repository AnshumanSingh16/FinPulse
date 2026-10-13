"use client";

import { AlertTriangle, ArrowRight, Loader2, Send, Wrench } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import type { CopilotToolCall } from "@/lib/personal/agents/copilot";
import type { WorkflowRun } from "@/lib/personal/agents/types";
import { copilot } from "@/lib/personal/client";
import type { ActionPlan } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

import { AgentTimeline, stepsFromEvents } from "../agent-activity";
import { PulseMark } from "../kit";
import { usePersonal } from "../provider";
import { ApprovalBadge } from "../ui";

type QA = {
  q: string;
  a: string;
  pending: boolean;
  tools: CopilotToolCall[];
  mode?: "ai" | "rule_based";
  unverified: string[];
  error?: string;
};

function suggestions(run: WorkflowRun): string[] {
  const out: string[] = [];
  const checks = run.analysis?.checks ?? [];
  if (checks.some((c) => c.id === "emergency_cover" && c.status !== "pass"))
    out.push("Why is my safety buffer thin?");
  if (run.recommendation?.alternatives.some((a) => a.id === "save_first"))
    out.push("How much should I save before buying?");
  out.push("What if my income drops by 20%?");
  if ((run.analysis?.loanAmount ?? 0) > 0) out.push("What if interest rates rise 2%?");
  return out.slice(0, 3);
}

/** Follow-up questions about this analysis; the copilot keeps it in focus and uses real tools. */
function AskAboutThis({ run }: { run: WorkflowRun }) {
  const { refresh } = usePersonal();
  const [text, setText] = useState("");
  const [log, setLog] = useState<QA[]>([]);
  const busy = log.some((x) => x.pending);

  async function ask(q: string) {
    const question = q.trim();
    if (!question || busy) return;
    setText("");
    setLog((l) => [...l, { q: question, a: "", pending: true, tools: [], unverified: [] }]);
    const patch = (fn: (x: QA) => QA) =>
      setLog((l) => l.map((x, i) => (i === l.length - 1 ? fn(x) : x)));
    try {
      await copilot(
        question,
        (item) => {
          if (item.type === "tool") patch((x) => ({ ...x, tools: [...x.tools, item.call] }));
          else if (item.type === "message")
            patch((x) => ({
              ...x,
              a: item.text,
              mode: item.mode,
              unverified: item.unverifiedFigures,
              pending: false,
            }));
          else if (item.type === "error")
            patch((x) => ({ ...x, error: item.message, pending: false }));
        },
        run.id,
      );
      await refresh();
    } catch (e) {
      patch((x) => ({
        ...x,
        pending: false,
        error: e instanceof Error ? e.message : "The question couldn't be answered",
      }));
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-[14px] font-bold">Ask about this analysis</h3>
      {log.length ? (
        <ol className="flex flex-col gap-3">
          {log.map((x, i) => (
            <li key={i} className="flex flex-col gap-1.5">
              <p className="self-end rounded-2xl rounded-br-sm bg-ink-900 px-3 py-2 text-[13px] text-white">
                {x.q}
              </p>
              {x.tools.length ? (
                <p className="flex flex-wrap gap-1">
                  {x.tools.map((t) => (
                    <span
                      key={t.id}
                      title={t.summary}
                      className={cn(
                        "inline-flex items-center gap-1 rounded-md bg-agent-50 px-1.5 py-0.5 font-mono text-[10.5px] text-agent-700",
                        t.status !== "ok" && "bg-danger-50 text-danger-text",
                      )}
                    >
                      <Wrench className="size-2.5" aria-hidden /> {t.tool}
                    </span>
                  ))}
                </p>
              ) : null}
              {x.pending ? (
                <p className="flex items-center gap-2 text-[13px] text-ink-500">
                  <Loader2 className="size-3.5 animate-spin" aria-hidden /> Working on it…
                </p>
              ) : x.error ? (
                <p className="text-[13px] text-danger-text">{x.error}</p>
              ) : (
                <>
                  <p className="rounded-2xl rounded-bl-sm bg-surface-sunken px-3 py-2 text-[13px] leading-relaxed whitespace-pre-line">
                    {x.a}
                  </p>
                  <p className="text-[11px] text-ink-400">
                    {x.mode === "ai"
                      ? "AI answer grounded in tool outputs"
                      : "Rule-based answer from the same tools (AI off)"}
                  </p>
                  {x.unverified.length ? (
                    <p className="flex items-start gap-1 text-[11px] text-caution-text">
                      <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />
                      {x.unverified.join(", ")} didn&apos;t match any tool output — treat with
                      caution.
                    </p>
                  ) : null}
                </>
              )}
            </li>
          ))}
        </ol>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {suggestions(run).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => ask(s)}
              className="rounded-full border border-line bg-surface px-3 py-1.5 text-left text-[12.5px] text-ink-700 transition-colors hover:border-line-strong hover:bg-surface-sunken"
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void ask(text);
        }}
        className="flex items-center gap-1.5 rounded-xl border border-line-strong bg-surface p-1 pl-3 focus-within:border-brand-600 focus-within:ring-3 focus-within:ring-brand-500/15"
      >
        <label htmlFor="ask-this" className="sr-only">
          Ask a follow-up question about this analysis
        </label>
        <input
          id="ask-this"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={500}
          placeholder="Ask a follow-up…"
          className="h-9 min-w-0 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-ink-400"
        />
        <button
          type="submit"
          disabled={busy || !text.trim()}
          aria-label="Send question"
          className="flex size-9 items-center justify-center rounded-lg bg-ink-900 text-white transition disabled:opacity-40"
        >
          <Send className="size-4" aria-hidden />
        </button>
      </form>
      <Link href="/copilot" className="text-[12px] font-semibold text-brand-700 hover:underline">
        Continue in Ask FinPulse →
      </Link>
    </div>
  );
}

export function AgentRail({
  run,
  plan,
  onReview,
}: {
  run: WorkflowRun;
  plan: ActionPlan | undefined;
  onReview: () => void;
}) {
  const steps = stepsFromEvents(run.events, false);
  const done = steps.filter((s) => s.status === "done").length;
  const findings = run.findings.filter((f) => f.severity !== "info").length;
  return (
    <aside
      className="flex flex-col gap-5 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-5"
      aria-label="How FinPulse worked on this"
    >
      <header className="flex items-start gap-3">
        <PulseMark size="sm" />
        <div className="flex min-w-0 flex-col">
          <h2 className="text-[15px] font-bold">How FinPulse worked on this</h2>
          <p className="tabular text-[12px] text-ink-500">
            {done}/{steps.length} stages · {run.toolCalls.length} tool calls · {findings} finding
            {findings === 1 ? "" : "s"}
          </p>
          <p className="text-[12px] text-ink-500">
            {run.mode.ai ? "AI agents on" : "AI off — deterministic & rule-based agents"} · rates{" "}
            {run.mode.research === "live" ? "researched live" : "are illustrative"}
          </p>
        </div>
      </header>

      {plan ? (
        <div className="flex flex-col gap-2 rounded-xl bg-surface-sunken p-3">
          <span className="text-[12px] font-semibold tracking-wide text-ink-500 uppercase">
            Proposed next action
          </span>
          <p className="text-[13.5px] font-semibold text-pretty">
            {plan.items[0]?.title ?? plan.title}
          </p>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <ApprovalBadge status={plan.status} />
            <button
              type="button"
              onClick={onReview}
              className="inline-flex items-center gap-1 text-[13px] font-semibold text-brand-700 hover:underline"
            >
              {plan.status === "awaiting_review" ? "Review & approve" : "Open checklist"}{" "}
              <ArrowRight className="size-3.5" aria-hidden />
            </button>
          </div>
        </div>
      ) : null}

      <div>
        <AskAboutThis run={run} />
      </div>
      <div className="flex flex-col gap-3 border-t border-line pt-4">
        <h3 className="text-[14px] font-bold">What each agent did</h3>
        <AgentTimeline events={run.events} running={false} />
      </div>
    </aside>
  );
}
