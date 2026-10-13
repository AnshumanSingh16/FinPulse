/**
 * Tools over the goal plan and the two decision simulators. Like every FinPulse tool, each one
 * validates its input with Zod and returns figures computed by tested, deterministic code.
 */
import "server-only";

import { z } from "zod";

import { formatINR } from "@/lib/format";

import {
  prepayVsInvest,
  rentVsBuy,
  type PrepayVsInvestResult,
  type RentVsBuyResult,
} from "../finance/decisions";
import {
  riskDrivers,
  simulatePlan,
  spendRoom,
  type PlanOdds,
  type RiskDriver,
  type SpendRoom,
  VARIABLE_INCOME_RISK,
} from "../finance/montecarlo";
import { optimizePlanAsync, type Proposal, type SearchRound } from "../finance/optimize";
import { planImpact, projectPlan, type PlanImpact, type PlanProjection } from "../finance/plan";
import { PlanAssumptionsSchema, PlanGoalSchema } from "../schemas";
import type { ToolDef } from "./runtime";

const money = z.number().finite().min(0).max(1e11);
const pct = (max: number) => z.number().min(0).max(max);
const month = z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/);

export const PlanHouseholdSchema = z.object({
  monthlyIncome: money,
  monthlyExpenses: money,
  existingEmis: money,
  otherMonthlyObligations: money,
  liquidSavings: money,
  investments: money,
});

export const PlanInputSchema = z.object({
  household: PlanHouseholdSchema,
  goals: z.array(PlanGoalSchema).max(13),
  assumptions: PlanAssumptionsSchema,
  startMonth: month,
});
const PlanInput = PlanInputSchema;
type PlanInput = z.infer<typeof PlanInput>;
const pct0 = (x: number) => `${Math.round(x * 100)}%`;

const statusText: Record<PlanProjection["summary"]["status"], string> = {
  on_track: "every goal on track",
  stretched: "some goals arrive late",
  off_track: "the plan doesn't hold",
  no_goals: "no goals saved",
};

export const projectPlanTool: ToolDef<PlanInput, PlanProjection> = {
  name: "project_goal_plan",
  agent: "analysis",
  description:
    "Project the household's money month by month across every saved goal: when each goal is reached, what it needs each month, and whether the emergency reserve holds.",
  input: PlanInput,
  run: (i) => projectPlan(i),
  summarize: (o) =>
    `${o.goals.length} goal(s): ${o.summary.onTrack} on track, ${o.summary.delayed} late, ${o.summary.notReached} out of reach — ${statusText[o.summary.status]}`,
  slim: (o) => ({ summary: o.summary, goals: o.goals }),
};

export const planImpactTool: ToolDef<
  PlanInput & { newGoal: z.infer<typeof PlanGoalSchema> },
  { impact: PlanImpact; before: PlanProjection; after: PlanProjection }
> = {
  name: "check_plan_impact",
  agent: "analysis",
  description:
    "Add one purchase to the household's goal plan and report which existing goals it pushes back, by how many months, or puts out of reach.",
  input: PlanInput.extend({ newGoal: PlanGoalSchema }),
  run: ({ newGoal, ...plan }) => {
    const before = projectPlan(plan);
    const after = projectPlan({ ...plan, goals: [...plan.goals, newGoal] });
    return { impact: planImpact(before, after, newGoal.id), before, after };
  },
  summarize: ({ impact }) => {
    if (!impact.affected.length)
      return impact.verdict === "fits"
        ? "fits alongside every saved goal"
        : "no saved goal moves, but the purchase itself can't be funded on time";
    return impact.affected
      .map((a) =>
        a.extraDelayMonths === null
          ? `${a.name}: out of reach`
          : `${a.name}: ${a.extraDelayMonths} month(s) later`,
      )
      .join("; ");
  },
  slim: ({ impact }) => ({ impact }),
};

const RentVsBuyInputSchema = z.object({
  price: money.min(100_000),
  downPaymentPct: pct(100).default(20),
  upfrontCostPct: pct(20).default(7),
  loanRatePct: pct(30).default(8.5),
  tenureMonths: z.number().int().min(12).max(360).default(240),
  monthlyRent: money,
  rentGrowthPct: pct(20).default(5),
  appreciationPct: pct(20).default(5),
  ownershipCostPct: pct(10).default(0.5),
  investReturnPct: pct(20).default(10),
  years: z.number().int().min(1).max(30).default(15),
});

export const rentVsBuyTool: ToolDef<z.infer<typeof RentVsBuyInputSchema>, RentVsBuyResult> = {
  name: "compare_rent_vs_buy",
  agent: "analysis",
  description:
    "Compare buying a home with renting a similar one and investing the difference, year by year, including appreciation, rent growth and ownership costs.",
  input: RentVsBuyInputSchema,
  run: (i) => rentVsBuy(i),
  summarize: (o) =>
    o.winner === "even"
      ? "buying and renting come out about level"
      : `${o.winner === "buy" ? "buying" : "renting"} ahead by ${formatINR(Math.abs(o.difference))} at the horizon`,
};

const PrepayInputSchema = z.object({
  outstanding: money.min(1000),
  loanRatePct: pct(30),
  remainingMonths: z.number().int().min(1).max(360),
  lumpSum: money.min(1000),
  investReturnPct: pct(20).default(10),
  taxOnGainsPct: pct(50).default(12.5),
});

export const prepayVsInvestTool: ToolDef<
  z.infer<typeof PrepayInputSchema>,
  PrepayVsInvestResult
> = {
  name: "compare_prepay_vs_invest",
  agent: "analysis",
  description:
    "Compare prepaying a loan (keeping the EMI, ending sooner) with investing the same lump sum, valued on the loan's original end date after tax on gains.",
  input: PrepayInputSchema,
  run: (i) => prepayVsInvest(i),
  summarize: (o) =>
    `${o.winner === "even" ? "about level" : `${o.winner} ahead by ${formatINR(Math.abs(o.difference))}`}; prepaying saves ${formatINR(o.prepay.interestSaved)} interest`,
};

export const DecideBodySchema = z.discriminatedUnion("kind", [
  z.object({ kind: z.literal("rent_vs_buy"), input: RentVsBuyInputSchema }),
  z.object({ kind: z.literal("prepay_vs_invest"), input: PrepayInputSchema }),
]);

// ---------------------------------------------------------------- probabilistic tools

const Variability = z.enum(["stable", "variable"]).nullable().optional();
const riskOf = (v: "stable" | "variable" | null | undefined) =>
  v === "variable" ? VARIABLE_INCOME_RISK : {};

export const simulatePlanTool: ToolDef<
  PlanInput & { paths?: number; incomeVariability?: "stable" | "variable" | null },
  PlanOdds
> = {
  name: "simulate_plan",
  agent: "risk",
  description:
    "Run the plan through many possible futures (market swings, inflation, raises, job loss, emergencies) and report how often each goal lands on time and whether money ever runs out.",
  input: PlanInput.extend({
    paths: z.number().int().min(50).max(2000).optional(),
    incomeVariability: Variability,
  }),
  run: ({ paths, incomeVariability, ...plan }) =>
    simulatePlan(plan, { paths: paths ?? 1000, risk: riskOf(incomeVariability) }),
  summarize: (o) =>
    `${o.paths} futures: every goal on time in ${pct0(o.allOnTime)}; money never runs out in ${pct0(o.neverShort)}`,
  slim: (o) => ({
    paths: o.paths,
    allOnTime: o.allOnTime,
    neverShort: o.neverShort,
    goals: o.goals,
    score: o.score,
  }),
};

export const rankRisksTool: ToolDef<
  PlanInput & { incomeVariability?: "stable" | "variable" | null },
  RiskDriver[]
> = {
  name: "rank_risks",
  agent: "risk",
  description:
    "Re-run the futures with each risk switched off in turn to see which one costs the plan most.",
  input: PlanInput.extend({ incomeVariability: Variability }),
  run: ({ incomeVariability, ...plan }) =>
    riskDrivers(plan, { paths: 300, risk: riskOf(incomeVariability) }),
  summarize: (o) =>
    o[0] && o[0].scoreCost >= 0.02
      ? `biggest risk: ${o[0].label.toLowerCase()}`
      : "no single risk stands out",
};

export const spendRoomTool: ToolDef<PlanInput & { target?: number }, SpendRoom> = {
  name: "find_spending_room",
  agent: "risk",
  description:
    "How much more (or less) the household could spend each month and still have every goal land on time in at least 80% of futures.",
  input: PlanInput.extend({ target: z.number().min(0.5).max(0.99).optional() }),
  run: ({ target, ...plan }) => spendRoom(plan, { target, paths: 300 }),
  summarize: (o) =>
    o.kind === "spare"
      ? `${formatINR(o.monthly)}/month of room at ${pct0(o.target)} confidence`
      : o.kind === "cut"
        ? `needs ${formatINR(o.monthly)}/month less spending to reach ${pct0(o.target)}`
        : `spending cuts alone don't reach ${pct0(o.target)}`,
};

/** The search, with a callback so each round can be reported as it finishes. */
export function searchPlanTool(
  onRound: (r: SearchRound) => void,
  speed: "thorough" | "quick" = "thorough",
): ToolDef<
  PlanInput & { locked?: string[]; incomeVariability?: "stable" | "variable" | null },
  Proposal
> {
  return {
    name: "search_better_plan",
    agent: "strategist",
    description:
      "Search concrete changes (dates, budgets, down payments, tenures, priorities, spending) for the smallest set that most improves the plan's odds; confirm the result on fresh futures.",
    input: PlanInput.extend({
      locked: z.array(z.string().max(40)).max(13).optional(),
      incomeVariability: Variability,
    }),
    run: ({ locked, incomeVariability, ...plan }) =>
      optimizePlanAsync(plan, {
        locked,
        risk: riskOf(incomeVariability),
        onRound,
        ...(speed === "quick"
          ? { screenPaths: 80, confirmPaths: 250, checkPaths: 500, maxChanges: 2 }
          : {}),
      }),
    summarize: (o) =>
      o.changes.length
        ? `${o.changes.length} change(s) found; every goal on time ${pct0(o.before.allOnTime)} → ${pct0(o.after.allOnTime)} on fresh futures`
        : "no change beats its disruption",
    slim: (o) => ({
      changes: o.changes,
      evaluations: o.evaluations,
      before: { allOnTime: o.before.allOnTime, score: o.before.score },
      after: { allOnTime: o.after.allOnTime, score: o.after.score },
    }),
  };
}
