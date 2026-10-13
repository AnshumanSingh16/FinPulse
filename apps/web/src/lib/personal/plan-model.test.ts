import { describe, expect, it } from "vitest";

import { addMonths } from "./finance/plan";
import { demoCheckIns, demoGoals, goalFromPurchase, pulse } from "./plan-model";
import { DEMO_PROFILE, DEMO_PURCHASE, PlanGoalSchema } from "./schemas";

const START = "2026-10";
const checkIns = (list: { month: string; income: number; spending: number }[]) =>
  list.map((c, i) => ({ ...c, id: `chk_${i}`, at: "2026-10-01T00:00:00Z" }));

describe("pulse", () => {
  it("compares each month with the profile and finds the streak", () => {
    const p = pulse({
      profile: DEMO_PROFILE,
      goals: [],
      assumptions: {},
      checkIns: checkIns(demoCheckIns(START)),
      startMonth: START,
    });
    // Profile: 2,00,000 in − 70,000 − 15,000 EMIs = 1,15,000 expected each month.
    expect(p.entries[0]!.month).toBe(addMonths(START, -1));
    expect(p.entries[0]!.expected).toBe(115_000);
    expect(p.entries[0]!.saved).toBe(91_000);
    expect(p.entries[0]!.gap).toBe(-24_000);
    expect(p.streak).toBe(3);
    expect(p.averageGap).toBe(Math.round((-11_000 - 18_000 - 24_000) / 3));
    expect(p.trend).toBe("behind");
    expect(p.due).toBe(false);
    expect(p.freeMonthly!.ifContinues).toBeLessThan(p.freeMonthly!.now);
  });

  it("shows which goals move when the shortfall eats into the plan", () => {
    const p = pulse({
      profile: DEMO_PROFILE,
      goals: demoGoals(START),
      assumptions: {},
      checkIns: checkIns([{ month: addMonths(START, -1), income: 200_000, spending: 190_000 }]),
      startMonth: START,
    });
    expect(p.trend).toBe("behind");
    expect(p.ifContinues.length).toBeGreaterThan(0);
  });

  it("breaks the streak on a missed month and asks for a check-in when overdue", () => {
    const p = pulse({
      profile: DEMO_PROFILE,
      goals: [],
      assumptions: {},
      checkIns: checkIns([
        { month: addMonths(START, -2), income: 200_000, spending: 85_000 },
        { month: addMonths(START, -5), income: 200_000, spending: 85_000 },
      ]),
      startMonth: START,
    });
    expect(p.streak).toBe(1);
    expect(p.trend).toBe("on_plan");
    expect(p.due).toBe(true);
  });
});

describe("goals", () => {
  it("demo goals and a goal made from a purchase pass validation", () => {
    for (const g of demoGoals(START)) expect(PlanGoalSchema.safeParse(g).success).toBe(true);
    const g = goalFromPurchase(
      DEMO_PURCHASE,
      {
        purchasePrice: 7_500_000,
        downPaymentPct: 20,
        upfrontCashCosts: 525_000,
        annualInterestRate: 8.5,
        tenureMonths: 240,
      },
      START,
      "run_abc",
    );
    expect(PlanGoalSchema.safeParse(g).success).toBe(true);
    expect(g.upfrontCostPct).toBe(7);
    expect(g.funding).toBe("loan");
    expect(g.targetMonth).toBe(START);
  });
});
