import { describe, expect, it } from "vitest";

import {
  drawPath,
  NO_RISK,
  planScore,
  riskDrivers,
  simulatePlan,
  spendRoom,
  type SimInput,
} from "./montecarlo";
import { addMonths, expectedPath, preparePlan, projectPlan, runPlan, type PlanGoal } from "./plan";

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

/** The demo household's shape, with three goals of different horizons. */
const INPUT: SimInput = {
  household: {
    monthlyIncome: 200_000,
    monthlyExpenses: 70_000,
    existingEmis: 15_000,
    otherMonthlyObligations: 0,
    liquidSavings: 2_500_000,
    investments: 800_000,
  },
  goals: [
    goal({
      id: "edu",
      priority: 1,
      targetAmount: 2_500_000,
      targetMonth: addMonths(START, 144),
      inflationPct: 10,
    }),
    goal({
      id: "car",
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

describe("drawPath", () => {
  it("with every risk switched off, reproduces the expected path", () => {
    const prep = preparePlan(INPUT);
    const exp = expectedPath(prep);
    const path = drawPath(prep, NO_RISK, 42);
    for (let m = 0; m < prep.horizon; m += 7) {
      expect(path.income[m]).toBeCloseTo(exp.income[m]!, 10);
      expect(path.spending[m]).toBeCloseTo(exp.spending[m]!, 10);
      expect(path.growth[m]).toBeCloseTo(exp.growth[m]!, 12);
      expect(path.safe[m]).toBeCloseTo(exp.safe[m]!, 12);
      expect(path.shock[m]).toBe(0);
      prep.goals.forEach((_, i) => expect(path.price[i]![m]).toBeCloseTo(exp.price[i]![m]!, 9));
    }
  });

  it("gives each goal its own random stream, so other goals don't change its prices", () => {
    const withAll = preparePlan(INPUT);
    const withoutCar = preparePlan({ ...INPUT, goals: INPUT.goals.filter((g) => g.id !== "car") });
    const risk = { ...NO_RISK, goalPriceVolatilityPct: 3 };
    const a = drawPath(withAll, risk, 7).price[withAll.goals.findIndex((g) => g.id === "trip")]!;
    const b = drawPath(withoutCar, risk, 7).price[
      withoutCar.goals.findIndex((g) => g.id === "trip")
    ]!;
    expect(Array.from(a.slice(0, 24))).toEqual(Array.from(b.slice(0, 24)));
  });

  it("job loss zeroes income for the drawn months", () => {
    const prep = preparePlan(INPUT);
    const path = drawPath(
      prep,
      { ...NO_RISK, jobLossYearlyPct: 100, jobLossMonthsMin: 4, jobLossMonthsMax: 4 },
      3,
    );
    const zeros = Array.from(path.income.slice(0, 12)).filter((x) => x === 0).length;
    expect(zeros).toBeGreaterThanOrEqual(1);
    expect(zeros).toBeLessThanOrEqual(4);
  });
});

describe("simulatePlan", () => {
  it("with no risk, every future matches the deterministic projection", () => {
    const det = projectPlan(INPUT);
    const odds = simulatePlan(INPUT, { risk: NO_RISK, paths: 20 });
    for (const g of odds.goals) {
      const d = det.goals.find((x) => x.id === g.id)!;
      expect(g.onTime).toBe(d.status === "on_track" ? 1 : 0);
      expect(g.reached).toBe(d.status === "not_reached" ? 0 : 1);
    }
    const sameRun = runPlan(preparePlan(INPUT), drawPath(preparePlan(INPUT), NO_RISK, 1));
    sameRun.years.forEach((y, i) => {
      expect(Math.abs(y.freeSavings - det.years[i]!.freeSavings)).toBeLessThanOrEqual(5);
    });
  });

  it("is reproducible for a seed", () => {
    expect(simulatePlan(INPUT, { paths: 120, seed: 9 })).toEqual(
      simulatePlan(INPUT, { paths: 120, seed: 9 }),
    );
  });

  it("reports probabilities, a fan of outcomes and a score", () => {
    const o = simulatePlan(INPUT, { paths: 300 });
    expect(o.allOnTime).toBeGreaterThan(0);
    expect(o.allOnTime).toBeLessThanOrEqual(1);
    for (const g of o.goals) {
      expect(g.onTime).toBeLessThanOrEqual(g.withinYear);
      expect(g.withinYear).toBeLessThanOrEqual(g.reached);
    }
    expect(o.fan.length).toBeGreaterThan(5);
    for (const f of o.fan) {
      expect(f.p10).toBeLessThanOrEqual(f.p50);
      expect(f.p50).toBeLessThanOrEqual(f.p90);
    }
    expect(o.score).toBeCloseTo(planScore(o), 12);
  });

  it("more risk never makes the plan safer", () => {
    const calm = simulatePlan(INPUT, { paths: 300 });
    const rough = simulatePlan(INPUT, {
      paths: 300,
      risk: { jobLossYearlyPct: 25, emergencyYearlyPct: 40, growthVolatilityPct: 25 },
    });
    expect(rough.allOnTime).toBeLessThanOrEqual(calm.allOnTime);
    expect(rough.score).toBeLessThan(calm.score);
  });

  it("a bigger goal is less likely to land on time", () => {
    const bigger = {
      ...INPUT,
      goals: INPUT.goals.map((g) => (g.id === "car" ? { ...g, targetAmount: 3_000_000 } : g)),
    };
    const a = simulatePlan(INPUT, { paths: 300 }).goals.find((g) => g.id === "car")!;
    const b = simulatePlan(bigger, { paths: 300 }).goals.find((g) => g.id === "car")!;
    expect(b.onTime).toBeLessThan(a.onTime);
  });
});

describe("riskDrivers and spendRoom", () => {
  it("ranks the five risks by what they cost the plan", () => {
    const d = riskDrivers(INPUT, { paths: 200 });
    expect(d.map((x) => x.id).sort()).toEqual([
      "emergencies",
      "income",
      "inflation",
      "job_loss",
      "markets",
    ]);
    for (let i = 1; i < d.length; i++)
      expect(d[i - 1]!.scoreCost).toBeGreaterThanOrEqual(d[i]!.scoreCost);
    expect(d.every((x) => x.allOnTimeCost >= 0 && x.scoreCost >= 0)).toBe(true);
  });

  it("finds spare room in a comfortable plan and a needed cut in a tight one", () => {
    const easy: SimInput = {
      ...INPUT,
      goals: [goal({ id: "tv", targetAmount: 100_000, targetMonth: addMonths(START, 12) })],
    };
    const room = spendRoom(easy, { paths: 150 });
    expect(room.kind).toBe("spare");
    expect(room.monthly).toBeGreaterThan(10_000);

    const tight: SimInput = {
      ...INPUT,
      goals: [goal({ id: "flat", targetAmount: 6_500_000, targetMonth: addMonths(START, 24) })],
    };
    const need = spendRoom(tight, { paths: 150 });
    expect(need.current).toBeLessThan(0.8);
    expect(["cut", "out_of_reach"]).toContain(need.kind);
  });
});
