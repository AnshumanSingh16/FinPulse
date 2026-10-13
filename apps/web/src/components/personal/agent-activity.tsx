"use client";

import {
  AlertTriangle,
  Check,
  ChevronDown,
  Loader2,
  MinusCircle,
  OctagonAlert,
  PauseCircle,
  Wrench,
} from "lucide-react";
import { useMemo, useState } from "react";

import { AGENT_LABELS, type AgentEvent, type StepStatus } from "@/lib/personal/agents/types";
import { cn } from "@/lib/utils";

import { AGENT_META, AgentGlyph } from "./kit";

export type StepView = {
  id: string;
  agent: keyof typeof AGENT_LABELS;
  title: string;
  why: string;
  status: StepStatus;
  summary?: string;
  /** Tool results and tool errors the server reported for this step, in order. */
  tools: { name: string; detail: string; ok: boolean }[];
  /** Warnings and errors the server reported for this step (findings, degraded tools, AI issues). */
  warnings: string[];
  startedAt?: string;
  endedAt?: string;
};

/**
 * Derive each stage purely from the events the server emitted while the workflow ran. Nothing is
 * inferred or animated client-side: a stage is "done" only after its step_completed event.
 */
export function stepsFromEvents(events: AgentEvent[], running: boolean): StepView[] {
  const plan = events.find((e) => e.kind === "plan_created")?.plan ?? [];
  const steps: StepView[] = plan.map((p) => ({ ...p, status: "pending", tools: [], warnings: [] }));
  for (const e of events) {
    const s = steps.find((x) => x.id === e.stepId);
    if (!s) continue;
    if (e.kind === "step_started") Object.assign(s, { status: "running", startedAt: e.at });
    if (e.kind === "step_completed")
      Object.assign(s, { status: "done", summary: e.message, endedAt: e.at });
    if (e.kind === "step_failed")
      Object.assign(s, { status: "failed", summary: e.message, endedAt: e.at });
    if (e.kind === "needs_input") Object.assign(s, { status: "needs_input", summary: e.message });
    if (e.kind === "tool_result") {
      const [name, ...rest] = e.message.split(": ");
      s.tools.push({ name: name ?? e.message, detail: rest.join(": "), ok: true });
    }
    if (e.kind === "tool_error") s.tools.push({ name: "tool error", detail: e.message, ok: false });
    if (
      (e.kind === "tool_error" || e.kind === "llm" || e.kind === "finding") &&
      e.level &&
      e.level !== "info"
    )
      s.warnings.push(e.message);
  }
  const ended = events.some(
    (e) => e.kind === "run_completed" || e.kind === "run_failed" || e.kind === "needs_input",
  );
  if (ended || !running) for (const s of steps) if (s.status === "pending") s.status = "skipped";
  return steps;
}

const STATUS: Record<StepStatus, { icon: typeof Check; dot: string; label: string }> = {
  pending: { icon: MinusCircle, dot: "bg-surface-sunken text-ink-400", label: "Waiting" },
  running: { icon: Loader2, dot: "bg-agent-50 text-agent-700", label: "Working" },
  done: { icon: Check, dot: "bg-brand-600 text-white", label: "Done" },
  failed: { icon: OctagonAlert, dot: "bg-danger-50 text-danger-text", label: "Failed" },
  skipped: { icon: MinusCircle, dot: "bg-surface-sunken text-ink-400", label: "Not run" },
  needs_input: { icon: PauseCircle, dot: "bg-caution-50 text-caution-text", label: "Needs input" },
};

function duration(s: StepView): string | null {
  if (!s.startedAt || !s.endedAt) return null;
  const ms = new Date(s.endedAt).getTime() - new Date(s.startedAt).getTime();
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/**
 * The FinPulse agent timeline. Each stage names the agent that ran it, what it concluded, and —
 * on expand — every tool it called and any warning it raised.
 */
export function AgentTimeline({
  events,
  running,
  expandable = true,
  className,
}: {
  events: AgentEvent[];
  running: boolean;
  expandable?: boolean;
  className?: string;
}) {
  const steps = useMemo(() => stepsFromEvents(events, running), [events, running]);
  const [open, setOpen] = useState<string | null>(null);
  if (!steps.length) return null;
  return (
    <ol className={cn("flex flex-col", className)} aria-live="polite" aria-busy={running}>
      {steps.map((s, i) => {
        const meta = STATUS[s.status];
        const Icon = meta.icon;
        const isOpen = open === s.id;
        const canOpen = expandable && (s.tools.length > 0 || s.warnings.length > 0);
        const dim = s.status === "pending" || s.status === "skipped";
        return (
          <li key={s.id} className="flex gap-3">
            <span className="flex flex-col items-center">
              <span
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full",
                  meta.dot,
                  s.status === "running" && "fp-pulse",
                )}
              >
                <Icon
                  className={cn("size-3.5", s.status === "running" && "animate-spin")}
                  aria-hidden
                />
              </span>
              {i < steps.length - 1 ? (
                <span
                  className={cn(
                    "my-1 w-px flex-1",
                    s.status === "done" ? "bg-brand-200" : "bg-line",
                  )}
                  aria-hidden
                />
              ) : null}
            </span>
            <div className={cn("flex min-w-0 flex-1 flex-col gap-1 pb-4", dim && "opacity-60")}>
              <button
                type="button"
                disabled={!canOpen}
                onClick={() => setOpen(isOpen ? null : s.id)}
                aria-expanded={canOpen ? isOpen : undefined}
                className="flex w-full items-start gap-2 rounded-md text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:cursor-default"
              >
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-[14px] leading-snug font-semibold text-ink-900">
                    {s.title}
                    <span className="sr-only"> — {meta.label}</span>
                  </span>
                  <span className="flex flex-wrap items-center gap-x-2 text-[12px] text-ink-500">
                    <span>{AGENT_META[s.agent].label} agent</span>
                    {s.tools.length ? (
                      <span>
                        · {s.tools.length} tool call{s.tools.length === 1 ? "" : "s"}
                      </span>
                    ) : null}
                    {duration(s) ? <span>· {duration(s)}</span> : null}
                    {s.status === "skipped" ? <span>· not run</span> : null}
                  </span>
                </span>
                {canOpen ? (
                  <ChevronDown
                    className={cn(
                      "mt-1 size-4 shrink-0 text-ink-400 transition-transform",
                      isOpen && "rotate-180",
                    )}
                    aria-hidden
                  />
                ) : null}
              </button>
              {s.status !== "pending" && s.status !== "skipped" ? (
                <p
                  className={cn(
                    "text-[13px] leading-snug text-pretty",
                    s.status === "failed"
                      ? "text-danger-text"
                      : s.status === "needs_input"
                        ? "text-caution-text"
                        : "text-ink-700",
                  )}
                >
                  {s.summary ?? s.why}
                </p>
              ) : null}
              {s.warnings.length && !isOpen ? (
                <p className="flex items-start gap-1 text-[12px] text-caution-text">
                  <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />
                  {s.warnings.length === 1
                    ? s.warnings[0]
                    : `${s.warnings.length} warnings — expand to see`}
                </p>
              ) : null}
              {isOpen ? (
                <div className="fp-rise mt-1 flex flex-col gap-2 rounded-xl bg-surface-sunken p-3">
                  <div className="flex items-center gap-2 text-[12px] text-ink-500">
                    <AgentGlyph agent={s.agent} size="sm" />
                    {AGENT_META[s.agent].role}
                  </div>
                  {s.tools.length ? (
                    <ul className="flex flex-col gap-1.5">
                      {s.tools.map((t, k) => (
                        <li key={k} className="flex items-start gap-2 text-[12px]">
                          <Wrench
                            className={cn(
                              "mt-0.5 size-3 shrink-0",
                              t.ok ? "text-agent-500" : "text-danger-text",
                            )}
                            aria-hidden
                          />
                          <span className="min-w-0">
                            <code className="font-mono text-[11.5px] font-medium text-ink-900">
                              {t.name}
                            </code>
                            {t.detail ? <span className="text-ink-500"> — {t.detail}</span> : null}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {s.warnings.map((w) => (
                    <p key={w} className="flex items-start gap-1.5 text-[12px] text-caution-text">
                      <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden /> {w}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Back-compat name used by the copilot transcript. */
export const PlanTracker = AgentTimeline;

function time(iso: string) {
  return new Date(iso).toLocaleTimeString("en-IN", { hour12: false });
}

/** The raw event log, for people who want every line. */
export function EventFeed({ events, max = 60 }: { events: AgentEvent[]; max?: number }) {
  const shown = events.slice(-max);
  return (
    <ol className="flex max-h-96 flex-col gap-1 overflow-y-auto pr-1 font-mono text-[11.5px]">
      {shown.map((e) => {
        const tool = e.kind === "tool_call" || e.kind === "tool_result";
        const warn = e.level === "warning";
        const err = e.level === "error";
        return (
          <li key={e.id} className="flex gap-2 leading-snug">
            <span className="tabular shrink-0 text-ink-400">{time(e.at)}</span>
            <span
              className={cn("w-24 shrink-0 truncate", tool ? "text-ink-400" : "text-agent-700")}
            >
              {AGENT_LABELS[e.agent]}
            </span>
            <span
              className={cn(
                "min-w-0 break-words",
                tool && "text-ink-500",
                warn && "text-caution-text",
                err && "text-danger-text",
              )}
            >
              {e.message}
            </span>
          </li>
        );
      })}
      {events.length === 0 ? <li className="text-ink-500">No agent activity yet.</li> : null}
    </ol>
  );
}
