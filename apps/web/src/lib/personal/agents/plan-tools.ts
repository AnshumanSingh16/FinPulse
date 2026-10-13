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

const PlanInput = z.object({
  household: PlanHouseholdSchema,
  goals: z.array(PlanGoalSchema).max(13),
  assumptions: PlanAssumptionsSchema,
  startMonth: month,
});
type PlanInput = z.infer<typeof PlanInput>;

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
