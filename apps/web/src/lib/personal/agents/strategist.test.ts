import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { currentMonth } from "../finance/plan";
import { demoGoals, goalFromPurchase } from "../plan-model";
import { DEMO_PROFILE, DEMO_PURCHASE } from "../schemas";
import { loadSession, resetSession } from "../store";
import { decideStrategy, runStrategist, StrategyDecisionError } from "./strategist";
import type { AgentEvent } from "./types";

function tightSession() {
  const s = loadSession("strat");
  s.profile = { values: { ...DEMO_PROFILE }, sources: {}, isDemo: true, updatedAt: null };
  const month = currentMonth();
  const house = goalFromPurchase(
    DEMO_PURCHASE,
    {
      purchasePrice: 7_500_000,
      downPaymentPct: 20,
      upfrontCashCosts: 525_000,
      annualInterestRate: 8.5,
      tenureMonths: 240,
    },
    month,
  );
  s.goals = [house, ...demoGoals(month).map((g, i) => ({ ...g, priority: i + 2 }))];
  s.planAssumptions = { existingEmiMonthsLeft: 30 };
  return s;
}

describe("Strategist agent", () => {
  beforeEach(() => resetSession("strat"));

  it("measures, explains, searches, checks and proposes — every step recorded", async () => {
    const s = tightSession();
    const events: AgentEvent[] = [];
    const run = await runStrategist(s, (e) => events.push(e));
    expect(run.status).toBe("completed");
    expect(run.plan.map((p) => p.status)).toEqual(["done", "done", "done", "done", "done"]);
    expect(run.toolCalls.map((c) => c.tool)).toEqual([
      "simulate_plan",
      "rank_risks",
      "search_better_plan",
    ]);
    expect(run.toolCalls.every((c) => c.status === "ok")).toBe(true);
    expect(run.drivers).toHaveLength(5);
    expect(run.rounds.length).toBeGreaterThan(0);
    expect(events.some((e) => e.kind === "finding" && e.message.startsWith("Round 1"))).toBe(true);
    expect(run.proposal).not.toBeNull();
    expect(run.proposal!.after.allOnTime).toBeGreaterThan(run.proposal!.before.allOnTime);
    expect(run.decision).toBe("pending");
    expect(s.strategies[0]).toBe(run);
    expect(s.audit.some((a) => a.type === "strategy_proposed")).toBe(true);
  }, 30_000);

  it("applies a proposal only to the plan it was made for, and only once", async () => {
    const s = tightSession();
    const run = await runStrategist(s);
    const goalsBefore = s.goals;
    // The plan changed after the search: refuse.
    s.goals = s.goals.map((g) => ({ ...g, name: `${g.name}!` }));
    expect(() => decideStrategy(s, run.id, "apply")).toThrow(StrategyDecisionError);
    s.goals = goalsBefore;
    decideStrategy(s, run.id, "apply");
    expect(run.decision).toBe("applied");
    expect(s.goals).toEqual(run.proposal!.goals);
    expect(s.planAssumptions.monthlySpendingCut).toBe(run.proposal!.spendingCut);
    expect(() => decideStrategy(s, run.id, "dismiss")).toThrow(/already applied/);
  }, 30_000);

  it("fails clearly without goals", async () => {
    const s = loadSession("strat");
    s.profile = { values: { ...DEMO_PROFILE }, sources: {}, isDemo: true, updatedAt: null };
    const run = await runStrategist(s);
    expect(run.status).toBe("failed");
    expect(run.error).toMatch(/Add at least one goal/);
    expect(run.plan[0]!.status).toBe("failed");
  });
});
