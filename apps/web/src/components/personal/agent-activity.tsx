"use client";

import {
  AlertTriangle,
  Check,
  CircleDashed,
  Loader2,
  MinusCircle,
  OctagonAlert,
  PauseCircle,
  Wrench,
} from "lucide-react";
import { useMemo } from "react";

import { AGENT_LABELS, type AgentEvent, type StepStatus } from "@/lib/personal/agents/types";
import { cn } from "@/lib/utils";

type StepView = {
  id: string;
  agent: keyof typeof AGENT_LABELS;
  title: string;
  why: string;
  status: StepStatus;
  summary?: string;
  warnings: string[];
  tools: number;
};

/** Derive plan-step status purely from the events the server emitted. */
export function stepsFromEvents(events: AgentEvent[], running: boolean): StepView[] {
  const plan = events.find((e) => e.kind === "plan_created")?.plan ?? [];
  const steps: StepView[] = plan.map((p) => ({ ...p, status: "pending", warnings: [], tools: 0 }));
  for (const e of events) {
    const s = steps.find((x) => x.id === e.stepId);
    if (!s) continue;
    if (e.kind === "step_started") s.status = "running";
    if (e.kind === "step_completed") Object.assign(s, { status: "done", summary: e.message });
    if (e.kind === "step_failed") Object.assign(s, { status: "failed", summary: e.message });
    if (e.kind === "needs_input") Object.assign(s, { status: "needs_input", summary: e.message });
    if (e.kind === "tool_result") s.tools += 1;
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

const STEP_ICON: Record<StepStatus, { icon: typeof Check; className: string; label: string }> = {
  pending: { icon: CircleDashed, className: "text-muted-foreground/60", label: "Waiting" },
  running: { icon: Loader2, className: "animate-spin text-primary", label: "In progress" },
  done: { icon: Check, className: "text-primary-foreground", label: "Done" },
  failed: { icon: OctagonAlert, className: "text-text-critical", label: "Failed" },
  skipped: { icon: MinusCircle, className: "text-muted-foreground/60", label: "Not run" },
  needs_input: { icon: PauseCircle, className: "text-text-warning", label: "Needs your input" },
};

/**
 * The workflow stages, in plain language. A stage shows "Done" only after the server reports
 * that step finished; failures, skipped stages and degraded tools are shown as such.
 */
export function PlanTracker({
  events,
  running,
  showAgents = false,
}: {
  events: AgentEvent[];
  running: boolean;
  showAgents?: boolean;
}) {
  const steps = useMemo(() => stepsFromEvents(events, running), [events, running]);
  if (!steps.length) return null;
  return (
    <ol className="flex flex-col" aria-live="polite">
      {steps.map((s, i) => {
        const meta = STEP_ICON[s.status];
        const Icon = meta.icon;
        return (
          <li key={s.id} className="flex gap-3">
            <span className="flex flex-col items-center">
              <span
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full",
                  s.status === "done"
                    ? "bg-primary"
                    : s.status === "running"
                      ? "bg-accent"
                      : "bg-muted",
                )}
              >
                <Icon className={cn("size-3.5", meta.className)} aria-hidden />
              </span>
              {i < steps.length - 1 ? (
                <span
                  className={cn(
                    "my-1 w-px flex-1",
                    s.status === "done" ? "bg-primary/40" : "bg-border",
                  )}
                />
              ) : null}
            </span>
            <div className="flex min-w-0 flex-col gap-0.5 pb-4">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span
                  className={cn(
                    "text-sm font-medium",
                    (s.status === "pending" || s.status === "skipped") && "text-muted-foreground",
                  )}
                >
                  {s.title}
                </span>
                <span className="sr-only">{meta.label}</span>
                {s.status === "skipped" ? (
                  <span className="text-xs text-muted-foreground">Not run</span>
                ) : null}
                {showAgents ? (
                  <span className="text-xs text-muted-foreground">
                    {AGENT_LABELS[s.agent]} agent
                  </span>
                ) : null}
              </div>
              {s.status !== "pending" && s.status !== "skipped" ? (
                <span
                  className={cn(
                    "text-xs text-pretty",
                    s.status === "failed"
                      ? "text-text-critical"
                      : s.status === "needs_input"
                        ? "text-text-warning"
                        : "text-muted-foreground",
                  )}
                >
                  {s.summary ?? s.why}
                </span>
              ) : null}
              {s.warnings.slice(0, 2).map((w) => (
                <span key={w} className="flex items-start gap-1 text-xs text-text-warning">
                  <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden /> {w}
                </span>
              ))}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function time(iso: string) {
  return new Date(iso).toLocaleTimeString("en-IN", { hour12: false });
}

export function EventFeed({ events, max = 60 }: { events: AgentEvent[]; max?: number }) {
  const shown = events.slice(-max);
  return (
    <ol
      className="flex max-h-96 flex-col gap-1 overflow-y-auto pr-1 font-mono text-[11.5px]"
      aria-live="polite"
    >
      {shown.map((e) => {
        const tool = e.kind === "tool_call" || e.kind === "tool_result";
        const warn = e.level === "warning";
        const err = e.level === "error";
        return (
          <li key={e.id} className="flex gap-2 leading-snug">
            <span className="tabular shrink-0 text-muted-foreground/70">{time(e.at)}</span>
            <span
              className={cn(
                "w-24 shrink-0 truncate",
                tool ? "text-muted-foreground" : "text-primary",
              )}
            >
              {AGENT_LABELS[e.agent]}
            </span>
            <span
              className={cn(
                "min-w-0 break-words",
                tool && "text-muted-foreground",
                warn && "text-text-warning",
                err && "text-text-critical",
              )}
            >
              {tool ? <Wrench className="mr-1 inline size-3" aria-hidden /> : null}
              {warn || err ? <AlertTriangle className="mr-1 inline size-3" aria-hidden /> : null}
              {e.message}
            </span>
          </li>
        );
      })}
      {events.length === 0 ? (
        <li className="text-muted-foreground">No agent activity yet.</li>
      ) : null}
    </ol>
  );
}
