/**
 * The goal plan as the product uses it: turning the profile, saved goals and check-ins into the
 * engine's inputs, and the engine's outputs into a monthly "pulse". Pure and shared by the server
 * (agents, API) and the plan page, so both always compute the same thing.
 */
import {
  addMonths,
  DEFAULT_ASSUMPTIONS,
  GOAL_INFLATION_DEFAULTS,
  GOAL_UPFRONT_DEFAULTS,
  goalChanges,
  monthsBetween,
  projectPlan,
  type GoalImpact,
  type GoalKind,
  type PlanAssumptions,
  type PlanGoal,
  type PlanHousehold,
  type PlanProjection,
} from "./finance/plan";
import type { CheckInValues, PlanGoalValues, ProfileValues, PurchaseRequest } from "./schemas";

export type CheckIn = CheckInValues & { id: string; at: string };

export const GOAL_KIND_LABEL: Record<GoalKind, string> = {
  house: "Home",
  car: "Car",
  education: "Education",
  wedding: "Wedding",
  travel: "Travel",
  business: "Business",
  custom: "Other goal",
};

/** The profile figures the projection needs, or the list of what's missing. */
export function householdFromProfile(
  p: ProfileValues,
): { household: PlanHousehold; missing: [] } | { household: null; missing: string[] } {
  const missing: string[] = [];
  if (p.monthlyIncome === null) missing.push("monthly take-home income");
  if (p.monthlyExpenses === null) missing.push("monthly living expenses");
  if (p.liquidSavings === null) missing.push("liquid savings");
  if (missing.length) return { household: null, missing };
  return {
    household: {
      monthlyIncome: p.monthlyIncome!,
      monthlyExpenses: p.monthlyExpenses!,
      existingEmis: p.existingEmis ?? 0,
      otherMonthlyObligations: p.otherMonthlyObligations ?? 0,
      liquidSavings: p.liquidSavings!,
      investments: p.investments ?? 0,
    },
    missing: [],
  };
}

/** Defaults, then the profile's preferred buffer, then the person's own overrides. */
export function effectiveAssumptions(
  p: ProfileValues,
  overrides: Partial<PlanAssumptions>,
): PlanAssumptions {
  return {
    ...DEFAULT_ASSUMPTIONS,
    ...(p.emergencyBufferMonths !== null ? { emergencyMonths: p.emergencyBufferMonths } : {}),
    ...overrides,
  };
}

export function projectFor(input: {
  profile: ProfileValues;
  goals: PlanGoal[];
  assumptions: Partial<PlanAssumptions>;
  startMonth: string;
}): { projection: PlanProjection; missing: [] } | { projection: null; missing: string[] } {
  const h = householdFromProfile(input.profile);
  if (!h.household) return { projection: null, missing: h.missing };
  return {
    projection: projectPlan({
      household: h.household,
      goals: input.goals,
      assumptions: effectiveAssumptions(input.profile, input.assumptions),
      startMonth: input.startMonth,
    }),
    missing: [],
  };
}

export function newGoalId(): string {
  return `goal_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
}

/** A sensible starting point for a new goal of a given kind. */
export function goalTemplate(kind: GoalKind, startMonth: string, priority: number): PlanGoalValues {
  const loan = kind === "house" || kind === "car";
  return {
    id: newGoalId(),
    kind,
    name: GOAL_KIND_LABEL[kind],
    targetAmount: kind === "house" ? 7_500_000 : kind === "car" ? 1_200_000 : 500_000,
    targetMonth: addMonths(startMonth, kind === "education" ? 120 : kind === "house" ? 36 : 24),
    priority,
    inflationPct: GOAL_INFLATION_DEFAULTS[kind],
    upfrontCostPct: GOAL_UPFRONT_DEFAULTS[kind],
    funding: loan ? "loan" : "cash",
    downPaymentPct: kind === "house" ? 20 : loan ? 30 : 100,
    loanRatePct: kind === "house" ? 8.5 : kind === "car" ? 9.5 : 0,
    loanTenureMonths: kind === "house" ? 240 : 60,
  };
}

const PURCHASE_KIND: Record<PurchaseRequest["type"], GoalKind> = {
  house: "house",
  car: "car",
  education: "education",
  business: "business",
  custom: "custom",
};

/** The purchase being analysed, as a goal bought this month on the analysed terms. */
export function goalFromPurchase(
  request: PurchaseRequest,
  purchase: {
    purchasePrice: number;
    downPaymentPct: number;
    upfrontCashCosts: number;
    annualInterestRate: number;
    tenureMonths: number;
  },
  startMonth: string,
  runId?: string,
): PlanGoalValues {
  const kind = PURCHASE_KIND[request.type];
  const loan = purchase.downPaymentPct < 100;
  return {
    id: newGoalId(),
    kind,
    name: request.label.slice(0, 60),
    targetAmount: Math.round(purchase.purchasePrice),
    targetMonth: startMonth,
    priority: 1,
    inflationPct: GOAL_INFLATION_DEFAULTS[kind],
    upfrontCostPct:
      purchase.purchasePrice > 0
        ? Math.min(30, Math.round((purchase.upfrontCashCosts / purchase.purchasePrice) * 1000) / 10)
        : 0,
    funding: loan ? "loan" : "cash",
    downPaymentPct: purchase.downPaymentPct,
    loanRatePct: Math.min(30, purchase.annualInterestRate),
    loanTenureMonths: Math.min(360, Math.max(6, purchase.tenureMonths)),
    ...(runId ? { fromRunId: runId } : {}),
  };
}

/** Fictional goals for the demo profile. */
export function demoGoals(startMonth: string): PlanGoalValues[] {
  return [
    {
      ...goalTemplate("education", startMonth, 1),
      name: "Daughter's higher education",
      targetAmount: 2_500_000,
      targetMonth: addMonths(startMonth, 144),
    },
    {
      ...goalTemplate("car", startMonth, 2),
      name: "Replace the family car",
      targetAmount: 1_400_000,
      targetMonth: addMonths(startMonth, 18),
    },
    {
      ...goalTemplate("travel", startMonth, 3),
      name: "Family trip to Japan",
      targetAmount: 450_000,
      targetMonth: addMonths(startMonth, 10),
    },
  ];
}

/** Fictional check-ins for the demo: spending has crept above the profile's figures. */
export function demoCheckIns(startMonth: string): CheckInValues[] {
  return [
    { month: addMonths(startMonth, -3), income: 200_000, spending: 96_000 },
    { month: addMonths(startMonth, -2), income: 200_000, spending: 103_000, note: "Diwali" },
    { month: addMonths(startMonth, -1), income: 200_000, spending: 109_000 },
  ];
}

// ---------------------------------------------------------------- pulse

export type PulseEntry = CheckIn & {
  /** Income minus spending. */
  saved: number;
  /** What the profile's figures say should be left over each month. */
  expected: number;
  gap: number;
};

export type Pulse = {
  entries: PulseEntry[];
  /** Consecutive months checked in, counting back from the latest. */
  streak: number;
  /** Average monthly gap over the last three check-ins (negative = saving less than planned). */
  averageGap: number | null;
  trend: "ahead" | "on_plan" | "behind" | "none";
  /** If the recent average continues: goals that move, and when. */
  ifContinues: GoalImpact[];
  /** Spare money each month after goals: today, and if the recent average continues. */
  freeMonthly: { now: number; ifContinues: number } | null;
  lastMonth: string | null;
  /** True when the latest check-in is more than a month old (or there is none). */
  due: boolean;
};

export function pulse(input: {
  profile: ProfileValues;
  goals: PlanGoal[];
  assumptions: Partial<PlanAssumptions>;
  checkIns: CheckIn[];
  startMonth: string;
}): Pulse {
  const p = input.profile;
  const expected =
    (p.monthlyIncome ?? 0) -
    (p.monthlyExpenses ?? 0) -
    (p.otherMonthlyObligations ?? 0) -
    (p.existingEmis ?? 0);
  const entries: PulseEntry[] = [...input.checkIns]
    .sort((a, b) => monthsBetween(a.month, b.month))
    .map((c) => {
      const saved = c.income - c.spending;
      return { ...c, saved, expected, gap: saved - expected };
    });
  let streak = 0;
  for (let i = 0; i < entries.length; i++) {
    if (i === 0 || monthsBetween(entries[i]!.month, entries[i - 1]!.month) === 1) streak++;
    else break;
  }
  const recent = entries.slice(0, 3);
  const averageGap = recent.length
    ? Math.round(recent.reduce((t, e) => t + e.gap, 0) / recent.length)
    : null;
  const tolerance = Math.max(1000, (p.monthlyIncome ?? 0) * 0.02);
  const trend =
    averageGap === null
      ? "none"
      : averageGap < -tolerance
        ? "behind"
        : averageGap > tolerance
          ? "ahead"
          : "on_plan";

  let ifContinues: GoalImpact[] = [];
  let freeMonthly: Pulse["freeMonthly"] = null;
  const h = householdFromProfile(p);
  if (h.household && averageGap !== null && trend !== "on_plan") {
    const assumptions = effectiveAssumptions(p, input.assumptions);
    const base = projectPlan({
      household: h.household,
      goals: input.goals,
      assumptions,
      startMonth: input.startMonth,
    });
    const adjusted = projectPlan({
      household: {
        ...h.household,
        // Saving less than planned is modelled as higher spending (and more as lower spending).
        monthlyExpenses: Math.max(0, h.household.monthlyExpenses - averageGap),
      },
      goals: input.goals,
      assumptions,
      startMonth: input.startMonth,
    });
    ifContinues = goalChanges(base, adjusted);
    freeMonthly = {
      now: base.summary.freeMonthlyNow,
      ifContinues: adjusted.summary.freeMonthlyNow,
    };
  }
  const lastMonth = entries[0]?.month ?? null;
  return {
    entries,
    streak,
    averageGap,
    trend,
    ifContinues,
    freeMonthly,
    lastMonth,
    due: lastMonth === null || monthsBetween(lastMonth, input.startMonth) > 1,
  };
}
