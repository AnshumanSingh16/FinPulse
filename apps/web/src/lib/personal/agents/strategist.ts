/**
 * The Strategist agent. Where the other agents assess a plan, this one changes it — or rather
 * proposes changes, for the person to accept:
 *
 *   measure   simulate_plan       the plan's odds across 1,000 futures
 *   explain   rank_risks          which risk costs the plan most
 *   search    search_better_plan  greedy search over concrete changes, scored on shared futures
 *   check     (verification)      the proposal re-scored on fresh futures it was never tuned on
 *   propose   (action)            the changes, waiting for the person's decision
 *
 * Every step runs through RunContext, so each tool call is validated, limited and recorded, and
 * the browser shows exactly these events. Nothing changes in the plan until the person applies
 * the proposal (enforced by the route, which only applies a proposal to the plan it was made for).
 */
import "server-only";

import { currentMonth } from "../finance/plan";
import { effectiveAssumptions, householdFromProfile, planKey, summarizeOdds } from "../plan-model";
import { audit, newId, persist, type SessionState } from "../store";
import { rankRisksTool, searchPlanTool, simulatePlanTool } from "./plan-tools";
import { RunContext } from "./runtime";
import type { AgentEvent, PlanStep, StrategyRun } from "./types";

const pct = (x: number) => `${Math.round(x * 100)}%`;
const MAX_STRATEGIES = 5;

function step(id: string, agent: PlanStep["agent"], title: string, why: string): PlanStep {
  return { id, agent, title, why, status: "pending", toolCallIds: [] };
}

export function strategyKey(session: SessionState): string {
  return planKey({
    profile: session.profile.values,
    goals: session.goals,
    assumptions: session.planAssumptions,
    startMonth: currentMonth(),
  });
}

export async function runStrategist(
  session: SessionState,
  listener: (event: AgentEvent) => void = () => {},
): Promise<StrategyRun> {
  const run: StrategyRun = {
    id: newId("strat"),
    createdAt: new Date().toISOString(),
    finishedAt: null,
    status: "running",
    planKey: strategyKey(session),
    plan: [
      step("measure", "risk", "Measuring your plan's odds", "1,000 possible futures, not one."),
      step("explain", "risk", "Finding what hurts most", "Each risk switched off in turn."),
      step(
        "search",
        "strategist",
        "Searching for a better plan",
        "Dates, budgets, loans, priorities and spending — the smallest changes that help most.",
      ),
      step(
        "check",
        "verification",
        "Checking on fresh futures",
        "The proposal is re-scored on futures the search never saw.",
      ),
      step("propose", "action", "Preparing the proposal", "Nothing changes until you apply it."),
    ],
    events: [],
    toolCalls: [],
    limits: { maxToolCalls: 10, maxDurationMs: 60_000, maxLlmCalls: 0, llmCalls: 0 },
    drivers: [],
    rounds: [],
    proposal: null,
    decision: "none",
    error: null,
  };
  session.strategies = [run, ...session.strategies].slice(0, MAX_STRATEGIES);
  const ctx = new RunContext(run, listener);
  const find = (id: string) => run.plan.find((s) => s.id === id)!;
  const start = (s: PlanStep) => {
    s.status = "running";
    ctx.emit(s.agent, "step_started", s.title, { stepId: s.id });
  };
  const finish = (s: PlanStep, summary: string) => {
    s.status = "done";
    s.summary = summary;
    ctx.emit(s.agent, "step_completed", summary, { stepId: s.id });
  };

  ctx.emit("strategist", "run_started", "Looking for a plan that is more likely to work");
  ctx.emit("strategist", "plan_created", `${run.plan.length} steps`, {
    plan: run.plan.map(({ id, agent, title, why }) => ({ id, agent, title, why })),
  });

  let current: PlanStep | null = null;
  try {
    current = find("measure");
    start(current);
    const h = householdFromProfile(session.profile.values);
    if (!h.household) throw new Error(`The profile is missing: ${h.missing.join(", ")}`);
    if (!session.goals.length) throw new Error("Add at least one goal to the plan first");
    const input = {
      household: h.household,
      goals: session.goals,
      assumptions: effectiveAssumptions(session.profile.values, session.planAssumptions),
      startMonth: currentMonth(),
    };

    const odds = await ctx.callTool(simulatePlanTool, { ...input, paths: 1000 }, current.id);
    for (const g of odds.goals)
      if (g.onTime < 0.6)
        ctx.emit(
          "risk",
          "finding",
          `“${g.name}” lands on time in only ${pct(g.onTime)} of futures.`,
          {
            stepId: current.id,
            level: "warning",
          },
        );
    finish(current, `Every goal lands on time in ${pct(odds.allOnTime)} of 1,000 futures.`);

    current = find("explain");
    start(current);
    run.drivers = await ctx.callTool(rankRisksTool, input, current.id);
    const top = run.drivers[0];
    finish(
      current,
      top && top.scoreCost >= 0.02
        ? `${top.label} costs the plan most.`
        : "No single risk stands out — the plan is limited by the money itself.",
    );

    current = find("search");
    start(current);
    const searchStep = current;
    const proposal = await ctx.callTool(
      searchPlanTool((r) => {
        run.rounds.push(r);
        ctx.emit(
          "strategist",
          "finding",
          r.accepted
            ? `Round ${r.round}: tried ${r.tried} changes. Best: ${r.accepted.text} (score ${pct(r.scoreAfter)}).`
            : `Round ${r.round}: tried ${r.tried} changes; none beat its disruption — stopping.`,
          { stepId: searchStep.id },
        );
      }),
      input,
      current.id,
    );
    finish(
      current,
      proposal.changes.length
        ? `${proposal.changes.length} change(s) after ${proposal.evaluations} simulations.`
        : `No change was worth making after ${proposal.evaluations} simulations.`,
    );

    current = find("check");
    start(current);
    const before = summarizeOdds(proposal.before);
    const after = summarizeOdds(proposal.after);
    if (proposal.changes.length && after.score <= before.score)
      ctx.emit("verification", "finding", "On fresh futures the proposal is no better — dropped.", {
        stepId: current.id,
        level: "warning",
      });
    finish(
      current,
      `On ${proposal.after.paths} fresh futures: every goal on time ${pct(before.allOnTime)} → ${pct(after.allOnTime)}.`,
    );

    current = find("propose");
    start(current);
    const useful = proposal.changes.length > 0 && after.score > before.score;
    run.proposal = useful
      ? {
          changes: proposal.changes,
          goals: proposal.goals.map((g) => ({
            ...session.goals.find((x) => x.id === g.id)!,
            ...g,
          })),
          spendingCut: proposal.spendingCut,
          before,
          after,
          evaluations: proposal.evaluations,
        }
      : null;
    run.decision = useful ? "pending" : "none";
    finish(
      current,
      useful ? "Proposal ready — waiting for your decision." : "Your plan stays as it is.",
    );
    audit(
      session,
      "strategy_proposed",
      "agent:strategist",
      useful
        ? `Proposed ${proposal.changes.length} change(s): every goal on time ${pct(before.allOnTime)} → ${pct(after.allOnTime)}`
        : "Searched for a better plan; no change was worth making",
    );
    run.status = "completed";
    ctx.emit("strategist", "run_completed", useful ? "Proposal ready" : "No changes proposed");
  } catch (error) {
    const message = error instanceof Error ? error.message : "The search failed";
    if (current?.status === "running") {
      current.status = "failed";
      current.summary = message;
      ctx.emit(current.agent, "step_failed", message, { stepId: current.id, level: "error" });
    }
    for (const s of run.plan) if (s.status === "pending") s.status = "skipped";
    run.status = "failed";
    run.error = message;
    ctx.emit("strategist", "run_failed", message, { level: "error" });
  } finally {
    run.finishedAt = new Date().toISOString();
    persist(session);
  }
  return run;
}

export class StrategyDecisionError extends Error {
  constructor(
    message: string,
    readonly status: 404 | 409,
  ) {
    super(message);
  }
}

/**
 * The person's decision on a proposal. Applying replaces the plan's goals and spending commitment
 * with the proposal — only if the plan and finances are exactly what the search ran on.
 */
export function decideStrategy(
  session: SessionState,
  id: string,
  action: "apply" | "dismiss",
): StrategyRun {
  const run = session.strategies.find((s) => s.id === id);
  if (!run || !run.proposal) throw new StrategyDecisionError("No proposal to decide on", 404);
  if (run.decision !== "pending")
    throw new StrategyDecisionError(`This proposal was already ${run.decision}`, 409);
  if (action === "dismiss") {
    run.decision = "dismissed";
    audit(session, "strategy_decision", "user", "Dismissed the Strategist's proposal");
    return run;
  }
  if (strategyKey(session) !== run.planKey)
    throw new StrategyDecisionError(
      "Your plan or finances changed since this search ran. Search again.",
      409,
    );
  session.goals = run.proposal.goals;
  session.planAssumptions = {
    ...session.planAssumptions,
    monthlySpendingCut: run.proposal.spendingCut,
  };
  run.decision = "applied";
  audit(
    session,
    "strategy_decision",
    "user",
    `Applied ${run.proposal.changes.length} change(s): ${run.proposal.changes.map((c) => c.text).join("; ")}`,
  );
  return run;
}
