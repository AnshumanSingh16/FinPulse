import type { AgentProgress, InvestigationTimeline, TimelineStep } from "@finpulse/contracts";
import {
  Check,
  GitFork,
  Loader2,
  Minus,
  ShieldCheck,
  Swords,
  TriangleAlert,
  X,
} from "lucide-react";
import Link from "next/link";

import { StanceBadge, StatementTypeBadge, ToneBadge } from "@/components/fp/badges";
import { evidenceHref } from "@/lib/evidence-link";
import { label, type Tone } from "@/lib/presentation";
import { cn } from "@/lib/utils";

export type TimelineCtx = {
  entityId: string;
  asOf?: string;
  /** Set once the investigation is stored, so evidence links can trace its claims. */
  investigationId?: string;
};

const STATE_LABEL: Record<string, string> = {
  pending: "Waiting",
  running: "In progress",
  completed: "Complete",
  completed_with_issues: "Complete, with issues",
  failed: "Failed",
  skipped: "Skipped",
};
const RESOLUTION_TONE: Record<string, Tone> = {
  upheld: "serious",
  partially_upheld: "warning",
  rejected: "good",
};
const SEVERITY_TONE: Record<string, Tone> = {
  major: "serious",
  moderate: "warning",
  minor: "info",
};
const EVIDENCE_SHOWN = 5;

function fmtMs(ms?: number | null) {
  if (ms === null || ms === undefined) return null;
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`;
}

export function StepMarker({
  state,
  number,
  size = "md",
}: {
  state: string;
  number: number;
  size?: "sm" | "md";
}) {
  const box = cn(
    "flex shrink-0 items-center justify-center rounded-full border-2 font-semibold",
    size === "md" ? "size-9 text-xs" : "size-6 text-[10px]",
  );
  const icon = size === "md" ? "size-4" : "size-3";
  switch (state) {
    case "completed":
      return (
        <span
          className={cn(box, "border-status-good bg-status-good/15 text-text-good")}
          aria-label="complete"
        >
          <Check className={icon} strokeWidth={3} />
        </span>
      );
    case "completed_with_issues":
      return (
        <span
          className={cn(box, "border-status-warning bg-status-warning/20 text-foreground")}
          aria-label="complete with issues"
        >
          <TriangleAlert className={icon} />
        </span>
      );
    case "failed":
      return (
        <span
          className={cn(box, "border-status-critical bg-status-critical/10 text-status-critical")}
          aria-label="failed"
        >
          <X className={icon} strokeWidth={3} />
        </span>
      );
    case "running":
      return (
        <span
          className={cn(box, "relative border-primary bg-primary/10 text-primary")}
          aria-label="in progress"
        >
          <span className="absolute inset-0 animate-ping rounded-full bg-primary/20" aria-hidden />
          <Loader2 className={cn(icon, "animate-spin")} />
        </span>
      );
    case "skipped":
      return (
        <span
          className={cn(box, "border-border bg-muted text-muted-foreground")}
          aria-label="skipped"
        >
          <Minus className={icon} />
        </span>
      );
    default:
      return (
        <span
          className={cn(box, "border-dashed border-border text-muted-foreground")}
          aria-label="waiting"
        >
          {number}
        </span>
      );
  }
}

function StateText({ step }: { step: TimelineStep }) {
  const ms = fmtMs(step.duration_ms);
  return (
    <span
      className={cn(
        "text-[11px] font-medium",
        step.state === "running" && "text-primary",
        step.state === "failed" && "text-status-critical",
        (step.state === "pending" || step.state === "skipped") && "text-muted-foreground",
        step.state.startsWith("completed") && "text-muted-foreground",
      )}
    >
      {STATE_LABEL[step.state] ?? step.state}
      {ms && step.state !== "running" ? ` · ${ms}` : ""}
    </span>
  );
}

function Highlights({ lines }: { lines: string[] }) {
  if (!lines.length) return null;
  return (
    <ul className="flex flex-col gap-1">
      {lines.map((l, i) => (
        <li key={i} className="flex gap-2 text-xs text-pretty">
          <span
            className="mt-1.5 size-1 shrink-0 rounded-full bg-muted-foreground/60"
            aria-hidden
          />
          <span className={l.startsWith("Input:") ? "text-muted-foreground" : ""}>
            {l.startsWith("Input: ") ? (
              <>
                <span className="font-medium">From the engines:</span> {l.slice(7)}
              </>
            ) : (
              l
            )}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ChallengeStatus({ agent, redTeam }: { agent: AgentProgress; redTeam?: AgentProgress }) {
  if (agent.state !== "succeeded") return null;
  const challenges = agent.challenges ?? [];
  if (challenges.length) {
    return (
      <div className="flex flex-col gap-1.5">
        {challenges.map((c, i) => (
          <div
            key={i}
            className="flex flex-col gap-1 rounded-md border border-status-warning/40 bg-status-warning/5 p-2"
          >
            <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
              <Swords className="size-3 text-foreground" aria-hidden />
              <span className="font-medium">Challenged by the Red-Team Agent</span>
              <span className="font-mono text-muted-foreground">on {c.target_claim_id}</span>
              <ToneBadge tone={SEVERITY_TONE[c.severity] ?? "neutral"} size="sm">
                {label(c.severity)}
              </ToneBadge>
            </div>
            <p className="text-xs text-pretty">{c.summary}</p>
            {c.resolution ? (
              <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                Senior agent ruling:
                <ToneBadge tone={RESOLUTION_TONE[c.resolution] ?? "neutral"} size="sm">
                  Challenge {label(c.resolution).toLowerCase()}
                </ToneBadge>
              </div>
            ) : null}
          </div>
        ))}
      </div>
    );
  }
  const text =
    !redTeam || redTeam.state === "pending" || redTeam.state === "running"
      ? "Awaiting red-team review"
      : redTeam.state === "succeeded"
        ? "Not challenged by the red team"
        : "No red-team review: the red team did not run";
  return (
    <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <ShieldCheck className="size-3" aria-hidden /> {text}
    </p>
  );
}

export function AgentCard({
  agent,
  ctx,
  redTeam,
  showChallenges = true,
}: {
  agent: AgentProgress;
  ctx: TimelineCtx;
  redTeam?: AgentProgress;
  showChallenges?: boolean;
}) {
  const kf = agent.key_finding;
  const link = (id: string) =>
    evidenceHref(ctx.entityId, id, {
      asOf: ctx.asOf,
      investigation: ctx.investigationId,
      claim: ctx.investigationId ? kf?.claim_id : null,
    });
  const all = agent.evidence_ids ?? [];
  const cited = kf ? [...kf.evidence_ids, ...all.filter((e) => !kf.evidence_ids.includes(e))] : all;
  return (
    <article
      className={cn(
        "flex min-w-0 flex-col gap-3 rounded-lg border bg-card p-3 sm:p-3.5",
        agent.state === "running" &&
          "border-primary/40 shadow-[0_0_0_3px_color-mix(in_oklch,var(--primary)_10%,transparent)]",
      )}
    >
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">{agent.title}</span>
        {agent.stance ? <StanceBadge stance={agent.stance} /> : null}
        <span className="ml-auto text-[11px] text-muted-foreground">
          {agent.state === "succeeded"
            ? `${agent.claims ?? 0} verified claims · ${agent.attempts ?? 1} attempt${agent.attempts === 1 ? "" : "s"}`
            : (STATE_LABEL[agent.state] ?? agent.state)}
        </span>
      </header>
      <div className="text-xs">
        <span className="font-medium text-muted-foreground">Analyzing · </span>
        <span className="text-pretty">{agent.focus}</span>
      </div>
      {agent.state === "running" ? (
        <p className="flex items-center gap-2 text-xs text-primary">
          <Loader2 className="size-3.5 animate-spin" aria-hidden /> Agent running. Its output is
          shown once it passes the verifier.
        </p>
      ) : agent.state === "failed" ? (
        <p className="text-xs text-status-critical">
          Failed{agent.error ? ` · ${agent.error}` : ""}. No unverified output is used.
        </p>
      ) : agent.state === "skipped" ? (
        <p className="text-xs text-muted-foreground">Did not run.</p>
      ) : agent.state === "pending" ? (
        <p className="text-xs text-muted-foreground">Waiting for its inputs.</p>
      ) : null}
      {kf ? (
        <div className="flex flex-col gap-1.5 rounded-md bg-muted/40 p-2.5">
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span className="font-medium text-foreground">Key finding</span>
            <StatementTypeBadge type={kf.statement_type} />
            <span>{kf.confidence} confidence</span>
            <span className="ml-auto font-mono">{kf.claim_id}</span>
          </div>
          <p className="text-sm text-pretty">{kf.statement}</p>
        </div>
      ) : null}
      {cited.length ? (
        <div className="flex flex-col gap-1">
          <span className="text-[11px] text-muted-foreground">
            Evidence used · {cited.length} item{cited.length === 1 ? "" : "s"}
          </span>
          <div className="flex flex-wrap gap-1">
            {cited.slice(0, EVIDENCE_SHOWN).map((id) => (
              <Link
                key={id}
                href={link(id)}
                className="max-w-full truncate rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground hover:border-primary/40 hover:text-primary"
              >
                {id}
              </Link>
            ))}
            {cited.length > EVIDENCE_SHOWN ? (
              <span className="px-1 py-0.5 text-[10px] text-muted-foreground">
                +{cited.length - EVIDENCE_SHOWN} more
              </span>
            ) : null}
          </div>
        </div>
      ) : null}
      {showChallenges ? <ChallengeStatus agent={agent} redTeam={redTeam} /> : null}
    </article>
  );
}

function VerificationTable({ agents }: { agents: AgentProgress[] }) {
  const audited = agents.filter((a) => a.state === "succeeded" && a.agent !== "senior_synthesis");
  if (!audited.length) return null;
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="tabular w-full text-xs">
        <thead className="bg-muted/60 text-muted-foreground">
          <tr>
            <th className="px-3 py-1.5 text-left font-medium">Agent</th>
            <th className="px-3 py-1.5 text-right font-medium">Claims passed</th>
            <th className="px-3 py-1.5 text-right font-medium">Pruned</th>
            <th className="px-3 py-1.5 text-right font-medium">Issues caught</th>
            <th className="px-3 py-1.5 text-right font-medium">Attempts</th>
          </tr>
        </thead>
        <tbody>
          {audited.map((a) => (
            <tr key={a.agent} className="border-t">
              <td className="px-3 py-1.5">{a.title}</td>
              <td className="px-3 py-1.5 text-right">{a.claims ?? "—"}</td>
              <td className="px-3 py-1.5 text-right">{a.pruned ?? "—"}</td>
              <td className="px-3 py-1.5 text-right">{a.issues_caught ?? "—"}</td>
              <td className="px-3 py-1.5 text-right">{a.attempts ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StepBody({
  step,
  agents,
  ctx,
}: {
  step: TimelineStep;
  agents: Map<string, AgentProgress>;
  ctx: TimelineCtx;
}) {
  const redTeam = agents.get("red_team");
  const mine = step.agents.map((n) => agents.get(n)).filter((a): a is AgentProgress => Boolean(a));
  const showDetail = step.state !== "pending" && step.state !== "skipped";
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <p className="text-xs text-pretty text-muted-foreground">{step.description}</p>
      {showDetail ? <Highlights lines={step.highlights} /> : null}
      {step.key === "verify_evidence" && showDetail ? (
        <VerificationTable agents={[...agents.values()]} />
      ) : null}
      {mine.length ? (
        <div className="grid grid-cols-1 gap-2">
          {mine.map((a) => (
            <AgentCard
              key={a.agent}
              agent={a}
              ctx={ctx}
              redTeam={redTeam}
              showChallenges={a.agent !== "red_team" && a.agent !== "senior_synthesis"}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StepRow({
  step,
  agents,
  ctx,
  last,
}: {
  step: TimelineStep;
  agents: Map<string, AgentProgress>;
  ctx: TimelineCtx;
  last: boolean;
}) {
  return (
    <li className="relative flex gap-3 sm:gap-4">
      {!last ? (
        <span
          className={cn(
            "absolute top-10 bottom-0 left-[17px] w-0.5",
            step.state.startsWith("completed") ? "bg-status-good/50" : "bg-border",
          )}
          aria-hidden
        />
      ) : null}
      <StepMarker state={step.state} number={step.number} />
      <div className="flex min-w-0 flex-1 flex-col gap-2 pb-7">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 pt-1.5">
          <h3
            className={cn(
              "text-sm font-semibold",
              step.state === "pending" && "text-muted-foreground",
            )}
          >
            <span className="tabular mr-1.5 text-muted-foreground">
              {String(step.number).padStart(2, "0")}
            </span>
            {step.title}
          </h3>
          <StateText step={step} />
        </div>
        <StepBody step={step} agents={agents} ctx={ctx} />
      </div>
    </li>
  );
}

/** The eight investigation steps, each mapped to the backend stages and agents that execute it. */
export function TimelineView({
  timeline,
  ctx,
}: {
  timeline: InvestigationTimeline;
  ctx: TimelineCtx;
}) {
  const agents = new Map(timeline.agents.map((a) => [a.agent, a]));
  const steps = timeline.steps;
  const groups: (TimelineStep | TimelineStep[])[] = [];
  for (const s of steps) {
    const prev = groups.at(-1);
    if (s.parallel_group && Array.isArray(prev) && prev[0]?.parallel_group === s.parallel_group)
      prev.push(s);
    else groups.push(s.parallel_group ? [s] : s);
  }
  return (
    <ol className="flex flex-col">
      {groups.map((g, gi) => {
        const last = gi === groups.length - 1;
        if (!Array.isArray(g))
          return <StepRow key={g.key} step={g} agents={agents} ctx={ctx} last={last} />;
        const running = g.some((s) => s.state === "running");
        const allDone = g.every((s) => s.state.startsWith("completed"));
        return (
          <li key={g[0]!.key} className="relative flex gap-3 sm:gap-4">
            {!last ? (
              <span
                className={cn(
                  "absolute top-10 bottom-0 left-[17px] w-0.5",
                  allDone ? "bg-status-good/50" : "bg-border",
                )}
                aria-hidden
              />
            ) : null}
            <span
              className={cn(
                "flex size-9 shrink-0 items-center justify-center rounded-full border-2",
                running
                  ? "border-primary bg-primary/10 text-primary"
                  : allDone
                    ? "border-status-good bg-status-good/15 text-text-good"
                    : "border-dashed text-muted-foreground",
              )}
              aria-hidden
            >
              <GitFork className="size-4" />
            </span>
            <div className="flex min-w-0 flex-1 flex-col gap-3 pb-7">
              <div className="pt-1.5">
                <h3 className="text-sm font-semibold">
                  Steps {g[0]!.number}–{g.at(-1)!.number} · Specialist investigation
                </h3>
                <p className="text-xs text-muted-foreground">
                  These four steps run concurrently: the orchestrator starts the specialist agents
                  together, each on the verified evidence pack only.
                </p>
              </div>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {g.map((s) => (
                  <section
                    key={s.key}
                    className={cn(
                      "flex min-w-0 flex-col gap-2 rounded-xl border p-2.5 sm:p-3.5",
                      s.state === "running" && "border-primary/40 bg-primary/[0.03]",
                    )}
                  >
                    <div className="flex items-center gap-2.5">
                      <StepMarker state={s.state} number={s.number} size="sm" />
                      <h4 className="min-w-0 flex-1 text-sm font-semibold">
                        <span className="tabular mr-1.5 text-muted-foreground">
                          {String(s.number).padStart(2, "0")}
                        </span>
                        {s.title}
                      </h4>
                      <StateText step={s} />
                    </div>
                    <StepBody step={s} agents={agents} ctx={ctx} />
                  </section>
                ))}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Overall progress, counted from step states (no estimate of time remaining). */
export function timelineCounts(timeline: InvestigationTimeline) {
  const done = timeline.steps.filter((s) => s.state.startsWith("completed")).length;
  return { done, total: timeline.steps.length };
}
