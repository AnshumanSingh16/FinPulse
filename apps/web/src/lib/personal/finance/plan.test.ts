import { describe, expect, it } from "vitest";

import { calculateEMI } from "./loan";
import {
  addMonths,
  monthsBetween,
  planImpact,
  projectPlan,
  type PlanAssumptions,
  type PlanGoal,
  type PlanHousehold,
} from "./plan";

const START = "2026-01";
/** No growth, inflation, returns or reserve: every figure can be checked by hand. */
const FLAT: Partial<PlanAssumptions> = {
  incomeGrowthPct: 0,
  expenseInflationPct: 0,
  safeReturnPct: 0,
  growthReturnPct: 0,
  emergencyMonths: 0,
};
const HH: PlanHousehold = {
  monthlyIncome: 100_000,
  monthlyExpenses: 50_000,
  existingEmis: 0,
  otherMonthlyObligations: 0,
  liquidSavings: 0,
  investments: 0,
};
const goal = (
  p: Partial<PlanGoal> & Pick<PlanGoal, "id" | "targetAmount" | "targetMonth">,
): PlanGoal => ({
  kind: "custom",
  name: p.id,
  priority: 1,
  inflationPct: 0,
  upfrontCostPct: 0,
  funding: "cash",
  downPaymentPct: 100,
  loanRatePct: 0,
  loanTenureMonths: 12,
  ...p,
});

describe("months", () => {
  it("adds and diffs across year ends", () => {
    expect(addMonths("2026-11", 3)).toBe("2027-02");
    expect(monthsBetween("2026-11", "2027-02")).toBe(3);
    expect(addMonths("2026-01", -1)).toBe("2025-12");
  });
});

describe("projectPlan", () => {
  it("reports the surplus and no goals", () => {
    const p = projectPlan({ household: HH, goals: [], assumptions: FLAT, startMonth: START });
    expect(p.summary.status).toBe("no_goals");
    expect(p.summary.surplusNow).toBe(50_000);
    expect(p.summary.freeMonthlyNow).toBe(50_000);
    expect(p.years[0]!.freeSavings).toBe(600_000);
  });

  it("funds a reachable cash goal on time with level contributions", () => {
    const p = projectPlan({
      household: HH,
      goals: [goal({ id: "g", targetAmount: 650_000, targetMonth: addMonths(START, 12) })],
      assumptions: FLAT,
      startMonth: START,
    });
    const g = p.goals[0]!;
    // 13 month-end contributions (months 0–12) reach ₹6,50,000 → ₹50,000 a month.
    expect(g.requiredMonthly).toBe(50_000);
    expect(g.allocatedMonthly).toBe(50_000);
    expect(g.status).toBe("on_track");
    expect(g.achievedMonth).toBe("2027-01");
    expect(g.fundedPctAtTarget).toBe(100);
    expect(p.summary.commitmentPct).toBe(100);
    expect(p.summary.status).toBe("on_track");
  });

  it("delays a goal the surplus can't fund in time, and says by how much", () => {
    const p = projectPlan({
      household: HH,
      goals: [goal({ id: "g", targetAmount: 1_000_000, targetMonth: addMonths(START, 6) })],
      assumptions: FLAT,
      startMonth: START,
    });
    const g = p.goals[0]!;
    // ₹50,000 a month reaches ₹10,00,000 after 20 contributions: month index 19.
    expect(g.status).toBe("delayed");
    expect(g.achievedIndex).toBe(19);
    expect(g.delayMonths).toBe(13);
    expect(g.fundedPctAtTarget).toBe(35);
    expect(p.summary.status).toBe("stretched");
  });

  it("inflates the price to the target date and adds one-time costs", () => {
    const p = projectPlan({
      household: HH,
      goals: [
        goal({
          id: "g",
          targetAmount: 1_000_000,
          targetMonth: addMonths(START, 24),
          inflationPct: 10,
          upfrontCostPct: 5,
        }),
      ],
      assumptions: FLAT,
      startMonth: START,
    });
    expect(p.goals[0]!.priceAtTarget).toBe(1_210_000);
    expect(p.goals[0]!.cashNeededAtTarget).toBe(1_270_500);
  });

  it("earmarks existing savings for goals, highest priority first", () => {
    const p = projectPlan({
      household: { ...HH, liquidSavings: 300_000 },
      goals: [
        goal({ id: "low", priority: 2, targetAmount: 500_000, targetMonth: addMonths(START, 12) }),
        goal({ id: "high", priority: 1, targetAmount: 200_000, targetMonth: addMonths(START, 12) }),
      ],
      assumptions: FLAT,
      startMonth: START,
    });
    const high = p.goals.find((g) => g.id === "high")!;
    const low = p.goals.find((g) => g.id === "low")!;
    expect(high.startingAllocation).toBe(200_000);
    expect(low.startingAllocation).toBe(100_000);
    expect(high.requiredMonthly).toBe(0);
    expect(p.goals[0]!.id).toBe("high");
  });

  it("keeps the emergency reserve before funding goals", () => {
    const p = projectPlan({
      household: { ...HH, liquidSavings: 120_000 },
      goals: [goal({ id: "g", targetAmount: 100_000, targetMonth: addMonths(START, 1) })],
      assumptions: { ...FLAT, emergencyMonths: 3 },
      startMonth: START,
    });
    expect(p.summary.reserveTarget).toBe(150_000);
    expect(p.summary.reserveNow).toBe(120_000);
    expect(p.goals[0]!.startingAllocation).toBe(0);
    // Month 0: ₹30,000 tops the reserve up; ₹20,000 goes to the goal.
    expect(p.goals[0]!.allocatedMonthly).toBe(20_000);
    expect(p.summary.reserveFullMonth).toBe(START);
  });

  it("starts the EMI of a loan-funded goal once it is bought", () => {
    const p = projectPlan({
      household: HH,
      goals: [
        goal({
          id: "car",
          targetAmount: 1_000_000,
          targetMonth: addMonths(START, 3),
          funding: "loan",
          downPaymentPct: 20,
          loanRatePct: 9,
          loanTenureMonths: 60,
        }),
      ],
      assumptions: FLAT,
      startMonth: START,
    });
    const car = p.goals[0]!;
    expect(car.status).toBe("on_track");
    expect(car.loan!.principal).toBe(800_000);
    expect(car.loan!.emi).toBe(calculateEMI(800_000, 9, 60));
    expect(p.years[0]!.emis).toBe(Math.round(car.loan!.emi));
    expect(p.years[0]!.surplus).toBe(Math.round(50_000 - car.loan!.emi));
    expect(p.years[0]!.loanOutstanding).toBeGreaterThan(0);
  });

  it("counts deficit months and draws down the reserve", () => {
    const p = projectPlan({
      household: { ...HH, monthlyExpenses: 110_000, liquidSavings: 100_000 },
      goals: [],
      assumptions: { ...FLAT, emergencyMonths: 6 },
      startMonth: START,
    });
    expect(p.summary.surplusNow).toBe(-10_000);
    expect(p.summary.deficitMonths).toBe(p.horizonMonths);
    // ₹1,00,000 covers ten ₹10,000 deficits; after that the shortfall is money that isn't there.
    expect(p.years[0]!.reserve).toBe(0);
    expect(p.years[0]!.freeSavings).toBe(-20_000);
    expect(p.summary.shortfallMonths).toBe(p.horizonMonths - 10);
  });

  it("marks goals out of reach within the horizon", () => {
    const p = projectPlan({
      household: { ...HH, monthlyExpenses: 99_000 },
      goals: [goal({ id: "g", targetAmount: 50_000_000, targetMonth: addMonths(START, 12) })],
      assumptions: FLAT,
      startMonth: START,
    });
    expect(p.goals[0]!.status).toBe("not_reached");
    expect(p.goals[0]!.delayMonths).toBeNull();
    expect(p.summary.status).toBe("off_track");
  });

  it("is deterministic", () => {
    const args = {
      household: { ...HH, liquidSavings: 400_000, investments: 200_000 },
      goals: [
        goal({
          id: "g",
          targetAmount: 900_000,
          targetMonth: addMonths(START, 30),
          inflationPct: 6,
        }),
      ],
      startMonth: START,
    };
    expect(projectPlan(args)).toEqual(projectPlan(args));
  });
});

describe("planImpact", () => {
  it("shows which existing goals a new purchase pushes back", () => {
    const base = [
      goal({ id: "edu", priority: 2, targetAmount: 600_000, targetMonth: addMonths(START, 12) }),
    ];
    const car = goal({
      id: "car",
      priority: 1,
      targetAmount: 600_000,
      targetMonth: addMonths(START, 6),
    });
    const before = projectPlan({
      household: HH,
      goals: base,
      assumptions: FLAT,
      startMonth: START,
    });
    const after = projectPlan({
      household: HH,
      goals: [...base, car],
      assumptions: FLAT,
      startMonth: START,
    });
    const impact = planImpact(before, after, "car");
    expect(before.goals[0]!.status).toBe("on_track");
    expect(impact.verdict).toBe("delays_others");
    expect(impact.affected).toHaveLength(1);
    expect(impact.affected[0]!.id).toBe("edu");
    expect(impact.affected[0]!.extraDelayMonths).toBeGreaterThan(0);
  });

  it("says a purchase fits when nothing else moves", () => {
    const base = [
      goal({ id: "trip", priority: 1, targetAmount: 100_000, targetMonth: addMonths(START, 12) }),
    ];
    const tv = goal({
      id: "tv",
      priority: 2,
      targetAmount: 50_000,
      targetMonth: addMonths(START, 6),
    });
    const before = projectPlan({
      household: HH,
      goals: base,
      assumptions: FLAT,
      startMonth: START,
    });
    const after = projectPlan({
      household: HH,
      goals: [...base, tv],
      assumptions: FLAT,
      startMonth: START,
    });
    const impact = planImpact(before, after, "tv");
    expect(impact.verdict).toBe("fits");
    expect(impact.affected).toEqual([]);
    expect(impact.freeMonthlyAfter).toBeLessThan(impact.freeMonthlyBefore);
  });
});
