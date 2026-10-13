import { describe, expect, it } from "vitest";

import type { SimInput } from "./montecarlo";
import { optimizePlan } from "./optimize";
import { addMonths, type PlanGoal } from "./plan";

const START = "2026-10";
const goal = (
  p: Partial<PlanGoal> & Pick<PlanGoal, "id" | "targetAmount" | "targetMonth">,
): PlanGoal => ({
  kind: "custom",
  name: p.id,
  priority: 1,
  inflationPct: 6,
  upfrontCostPct: 0,
  funding: "cash",
  downPaymentPct: 100,
  loanRatePct: 0,
  loanTenureMonths: 12,
  ...p,
});
const HOUSEHOLD = {
  monthlyIncome: 200_000,
  monthlyExpenses: 70_000,
  existingEmis: 15_000,
  otherMonthlyObligations: 0,
  liquidSavings: 2_500_000,
  investments: 800_000,
};
const FAST = { screenPaths: 60, confirmPaths: 150, checkPaths: 300 };

/** Buying a ₹75 lakh home now squeezes a car and a trip that were on track. */
const TIGHT: SimInput = {
  household: HOUSEHOLD,
  goals: [
    goal({
      id: "house",
      kind: "house",
      priority: 1,
      targetAmount: 7_500_000,
      targetMonth: START,
      funding: "loan",
      downPaymentPct: 20,
      loanRatePct: 8.5,
      loanTenureMonths: 240,
      upfrontCostPct: 7,
    }),
    goal({
      id: "car",
      kind: "car",
      priority: 2,
      targetAmount: 1_400_000,
      targetMonth: addMonths(START, 18),
      funding: "loan",
      downPaymentPct: 30,
      loanRatePct: 9.5,
      loanTenureMonths: 60,
    }),
    goal({ id: "trip", priority: 3, targetAmount: 450_000, targetMonth: addMonths(START, 10) }),
  ],
  assumptions: { existingEmiMonthsLeft: 30 },
  startMonth: START,
};

describe("optimizePlan", () => {
  it("finds changes that raise the odds, confirmed on fresh futures", () => {
    const rounds: number[] = [];
    const p = optimizePlan(TIGHT, { ...FAST, onRound: (r) => rounds.push(r.round) });
    expect(p.changes.length).toBeGreaterThan(0);
    expect(p.changes.length).toBeLessThanOrEqual(3);
    expect(p.after.score).toBeGreaterThan(p.before.score);
    expect(p.after.allOnTime).toBeGreaterThan(p.before.allOnTime);
    expect(rounds[0]).toBe(1);
    // Every accepted change is described in plain words.
    for (const c of p.changes) expect(c.text.length).toBeGreaterThan(10);
    expect(p.evaluations).toBeGreaterThan(p.rounds[0]!.tried);
  });

  it("never touches a locked goal", () => {
    const p = optimizePlan(TIGHT, { ...FAST, locked: ["house"] });
    const house = p.goals.find((g) => g.id === "house")!;
    expect(house).toEqual(TIGHT.goals.find((g) => g.id === "house"));
    expect(p.changes.every((c) => !("goalId" in c) || c.goalId !== "house")).toBe(true);
  });

  it("leaves a plan that already works alone", () => {
    const easy: SimInput = {
      ...TIGHT,
      goals: [goal({ id: "tv", targetAmount: 100_000, targetMonth: addMonths(START, 12) })],
    };
    const p = optimizePlan(easy, FAST);
    expect(p.changes).toEqual([]);
    expect(p.goals).toEqual(easy.goals);
  });

  it("applies the changes it reports", () => {
    const p = optimizePlan(TIGHT, FAST);
    for (const c of p.changes) {
      if (c.kind === "delay") {
        const before = TIGHT.goals.find((g) => g.id === c.goalId)!;
        const after = p.goals.find((g) => g.id === c.goalId)!;
        expect(after.targetMonth > before.targetMonth).toBe(true);
      }
      if (c.kind === "spend_less") expect(p.spendingCut).toBeGreaterThan(0);
    }
  });
});
