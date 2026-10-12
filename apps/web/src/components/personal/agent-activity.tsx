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
};

/** Derive plan-step status purely from the events the server emitted. */
export function stepsFromEvents(events: AgentEvent[], running: boolean): StepView[] {
  const plan = events.find((e) => e.kind === "plan_created")?.plan ?? [];
  const steps: StepView[] = plan.map((p) => ({ ...p, status: "pending" }));
  for (const e of events) {
    const s = steps.find((x) => x.id === e.stepId);
    if (!s) continue;
    if (e.kind === "step_started") s.status = "running";
    if (e.kind === "step_completed") Object.assign(s, { status: "done", summary: e.message });
    if (e.kind === "step_failed") Object.assign(s, { status: "failed", summary: e.message });
    if (e.kind === "needs_input") Object.assign(s, { status: "needs_input", summary: e.message });
  }
  const ended = events.some(
    (e) => e.kind === "run_completed" || e.kind === "run_failed" || e.kind === "needs_input",
  );
  if (ended || !running) for (const s of steps) if (s.status === "pending") s.status = "skipped";
  return steps;
}

const STEP_ICON: Record<StepStatus, { icon: typeof Check; className: string; label: string }> = {
  pending: { icon: CircleDashed, className: "text-muted-foreground", label: "Pending" },
  running: { icon: Loader2, className: "animate-spin text-primary", label: "Running" },
  done: { icon: Check, className: "text-text-good", label: "Done" },
  failed: { icon: OctagonAlert, className: "text-chart-negative", label: "Failed" },
  skipped: { icon: MinusCircle, className: "text-muted-foreground", label: "Not run" },
  needs_input: { icon: PauseCircle, className: "text-status-warning", label: "Needs your input" },
};

export function PlanTracker({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const steps = useMemo(() => stepsFromEvents(events, running), [events, running]);
  if (!steps.length) return null;
  return (
    <ol className="flex flex-col gap-1">
      {steps.map((s, i) => {
        const meta = STEP_ICON[s.status];
        const Icon = meta.icon;
        return (
          <li
            key={s.id}
            className={cn(
              "flex gap-3 rounded-lg px-2 py-2",
              s.status === "running" && "bg-primary/5",
            )}
          >
            <span className="flex flex-col items-center">
              <Icon className={cn("size-4 shrink-0", meta.className)} aria-label={meta.label} />
              {i < steps.length - 1 ? <span className="mt-1 w-px flex-1 bg-border" /> : null}
            </span>
            <div className="flex min-w-0 flex-col gap-0.5 pb-1">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-sm font-medium">{s.title}</span>
                <span className="text-[11px] text-muted-foreground">
                  {AGENT_LABELS[s.agent]} agent
                </span>
              </div>
              <span className="text-xs text-pretty text-muted-foreground">
                {s.summary ?? s.why}
              </span>
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
                warn && "text-status-warning",
                err && "text-chart-negative",
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
