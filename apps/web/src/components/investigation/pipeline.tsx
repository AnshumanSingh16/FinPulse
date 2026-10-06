import type { Investigation, InvestigationProgress } from "@finpulse/contracts";
import { Check, CircleDashed, Loader2, Minus, TriangleAlert, X } from "lucide-react";

import { cn } from "@/lib/utils";

export type StepState = "pending" | "running" | "done" | "issues" | "failed" | "skipped";
export type Step = {
  stage: string;
  title: string;
  state: StepState;
  ms?: number;
  summary?: string;
};
export type AgentStep = {
  agent: string;
  title: string;
  state: StepState;
  claims?: number | null;
  attempts?: number | null;
  error?: string | null;
};

// The workflow's fixed stage order (as documented by the API), used to show what is still to come.
const STAGES: [string, string][] = [
  ["financial_data", "Financial data"],
  ["deterministic_analytics", "Deterministic analytics"],
  ["financial_passport", "Financial Passport"],
  ["early_warning_detection", "Early warning detection"],
  ["stress_testing", "Stress testing"],
  ["evidence_assembly", "Evidence assembly"],
  ["specialized_investigation", "Specialized AI investigation"],
  ["disagreement_detection", "Disagreement detection and review planning"],
  ["red_team_challenge", "Red-team challenge"],
  ["senior_synthesis", "Senior Financial Intelligence Agent"],
  ["final_assessment", "Final assessment"],
];
const DETERMINISTIC = new Set(STAGES.slice(0, 6).map(([s]) => s));
const ANALYSTS = [
  "financial_profile",
  "credit_intelligence",
  "early_warning_investigation",
  "risk_investigation",
  "stress_interpretation",
];

function stageState(status: string): StepState {
  return status === "completed"
    ? "done"
    : status === "completed_with_issues"
      ? "issues"
      : status === "failed"
        ? "failed"
        : "skipped";
}

export function stepsFromProgress(p: InvestigationProgress): {
  steps: Step[];
  agents: AgentStep[];
} {
  const done = new Map(p.stages.map((s) => [s.stage, s]));
  const steps = STAGES.map(([stage, title]) => {
    const rec = done.get(stage as never);
    if (rec)
      return {
        stage,
        title,
        state: stageState(rec.status),
        ms: rec.duration_ms,
        summary: rec.summary,
      };
    const running = p.status === "running" && p.current_stage === stage;
    return {
      stage,
      title,
      state: (running ? "running" : p.status === "failed" ? "skipped" : "pending") as StepState,
    };
  });
  const agents = p.agents.map((a) => ({
    agent: a.agent,
    title: a.title,
    state: (a.state === "succeeded"
      ? "done"
      : a.state === "pending" && p.status === "failed"
        ? "skipped"
        : a.state) as StepState,
    claims: a.claims,
    attempts: a.attempts,
    error: a.error,
  }));
  return { steps, agents };
}

export function stepsFromInvestigation(inv: Investigation): { steps: Step[]; agents: AgentStep[] } {
  const steps = inv.stages.map((s) => ({
    stage: s.stage,
    title: s.title,
    state: stageState(s.status),
    ms: s.duration_ms,
    summary: s.summary,
  }));
  const runs = [...Object.values(inv.agent_analyses), inv.red_team_run, inv.senior_synthesis_run];
  const agents = runs
    .filter((r): r is NonNullable<typeof r> => Boolean(r))
    .map((r) => ({
      agent: r.agent,
      title: r.title,
      state: (r.status === "succeeded" ? "done" : r.status) as StepState,
      claims: r.claims?.length ?? 0,
      attempts: r.attempts,
      error: r.error?.code ?? null,
    }));
  return { steps, agents };
}

function StateIcon({ state, className }: { state: StepState; className?: string }) {
  const base = cn("size-4 shrink-0", className);
  switch (state) {
    case "done":
      return (
        <span className="flex size-6 items-center justify-center rounded-full bg-status-good/15">
          <Check className={cn(base, "text-text-good")} aria-label="done" />
        </span>
      );
    case "issues":
      return (
        <span className="flex size-6 items-center justify-center rounded-full bg-status-warning/20">
          <TriangleAlert
            className={cn(base, "text-foreground")}
            aria-label="completed with issues"
          />
        </span>
      );
    case "failed":
      return (
        <span className="flex size-6 items-center justify-center rounded-full bg-status-critical/15">
          <X className={cn(base, "text-status-critical")} aria-label="failed" />
        </span>
      );
    case "running":
      return (
        <span className="flex size-6 items-center justify-center rounded-full bg-primary/10">
          <Loader2 className={cn(base, "animate-spin text-primary")} aria-label="running" />
        </span>
      );
    case "skipped":
      return (
        <span className="flex size-6 items-center justify-center rounded-full bg-muted">
          <Minus className={cn(base, "text-muted-foreground")} aria-label="skipped" />
        </span>
      );
    default:
      return (
        <span className="flex size-6 items-center justify-center rounded-full bg-muted">
          <CircleDashed className={cn(base, "text-muted-foreground")} aria-label="pending" />
        </span>
      );
  }
}

function StageRow({ step }: { step: Step }) {
  return (
    <li className="flex gap-3">
      <StateIcon state={step.state} />
      <div className="min-w-0 flex-1 pb-1">
        <div className="flex items-baseline justify-between gap-2">
          <span
            className={cn(
              "text-sm font-medium",
              step.state === "pending" && "text-muted-foreground",
            )}
          >
            {step.title}
          </span>
          {step.ms !== undefined ? (
            <span className="tabular shrink-0 text-[11px] text-muted-foreground">
              {step.ms >= 1000 ? `${(step.ms / 1000).toFixed(1)} s` : `${step.ms} ms`}
            </span>
          ) : null}
        </div>
        {step.summary ? (
          <p className="line-clamp-2 text-xs text-pretty text-muted-foreground">{step.summary}</p>
        ) : null}
      </div>
    </li>
  );
}

function AgentRow({ a }: { a: AgentStep }) {
  return (
    <li className="flex items-center gap-2.5 rounded-lg border bg-card px-3 py-2">
      <StateIcon state={a.state} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{a.title}</div>
        <div className="text-[11px] text-muted-foreground">
          {a.state === "done"
            ? `${a.claims ?? 0} verified claims · ${a.attempts ?? 1} attempt${a.attempts === 1 ? "" : "s"}`
            : a.state === "failed"
              ? `Failed${a.error ? ` · ${a.error}` : ""}`
              : a.state === "running"
                ? "Working on verified evidence…"
                : a.state === "skipped"
                  ? "Skipped"
                  : "Waiting"}
        </div>
      </div>
    </li>
  );
}

/** The investigation as a process: deterministic engines, then the agents, then the synthesis. */
export function Pipeline({ steps, agents }: { steps: Step[]; agents: AgentStep[] }) {
  const byStage = new Map(steps.map((s) => [s.stage, s]));
  const deterministic = steps.filter((s) => DETERMINISTIC.has(s.stage));
  const agent = (name: string) => agents.find((a) => a.agent === name);
  const step = (stage: string) => byStage.get(stage);
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
      <section className="flex flex-col gap-3">
        <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          1 · Deterministic engines
        </h3>
        <ol className="flex flex-col gap-2.5">
          {deterministic.map((s) => (
            <StageRow key={s.stage} step={s} />
          ))}
        </ol>
      </section>
      <section className="flex flex-col gap-3">
        <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          2 · AI investigation on verified evidence
        </h3>
        <div className="flex flex-col gap-2 rounded-xl border border-dashed p-3">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Specialist agents (in parallel)</span>
            {step("specialized_investigation")?.ms !== undefined ? (
              <span className="tabular">
                {((step("specialized_investigation")!.ms ?? 0) / 1000).toFixed(1)} s
              </span>
            ) : null}
          </div>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {ANALYSTS.map((n) => {
              const a = agent(n);
              return a ? <AgentRow key={n} a={a} /> : null;
            })}
          </ul>
        </div>
        <ol className="flex flex-col gap-2.5">
          {step("disagreement_detection") ? (
            <StageRow step={step("disagreement_detection")!} />
          ) : null}
        </ol>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {["red_team", "senior_synthesis"].map((n) => {
            const a = agent(n);
            return a ? <AgentRow key={n} a={a} /> : null;
          })}
        </ul>
        <ol className="flex flex-col gap-2.5">
          {step("final_assessment") ? <StageRow step={step("final_assessment")!} /> : null}
        </ol>
      </section>
    </div>
  );
}
