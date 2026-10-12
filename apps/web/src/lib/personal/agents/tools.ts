/**
 * The tool registry. Every financial number FinPulse shows comes out of one of these tools, and
 * every tool validates its input with a Zod schema before it runs.
 */
import "server-only";

import { z } from "zod";

import { formatINR } from "@/lib/format";

import {
  analysePurchase,
  findComfortablePrice,
  LABEL_TEXT,
  type PurchaseAnalysis,
} from "../finance/affordability";
import { monthlySavingsRequired, monthsToReachGoal } from "../finance/health";
import { calculateEMI, calculateTotalInterest, calculateTotalRepayment } from "../finance/loan";
import { runScenarioSet, STANDARD_SCENARIOS, type ScenarioResult } from "../finance/scenarios";
import { ProfileValuesSchema, PurchaseRequestSchema, PURCHASE_TYPES } from "../schemas";
import { buildActionPlan, type ActionPlanInput } from "./action";
import { resolveInputs } from "./planner";
import { IllustrativeResearchProvider, researchProvider } from "./research";
import type { ToolDef } from "./runtime";
import type { FinancingOption, ResearchResult } from "./types";
import { verify, type VerificationInput } from "./verification";

const money = z.number().finite().min(0).max(1e11);

export const ResolvedInputsSchema = z.object({
  purchase: z.object({
    purchasePrice: money,
    downPaymentPct: z.number().min(0).max(100),
    upfrontCashCosts: money,
    financedCosts: money,
    annualInterestRate: z.number().min(0).max(50),
    tenureMonths: z.number().int().min(1).max(600),
    monthlyOwnershipCost: money,
  }),
  household: z.object({
    monthlyIncome: money,
    monthlyExpenses: money,
    existingEmis: money,
    otherMonthlyObligations: money,
    liquidSavings: money,
  }),
});

export const ScenarioParamsSchema = z.object({
  id: z.string().min(1).max(40),
  name: z.string().min(1).max(80),
  incomeChangePct: z.number().min(-100).max(200).default(0),
  incomeStopMonths: z.number().int().min(0).max(36).default(0),
  expenseChangePct: z.number().min(-90).max(300).default(0),
  rateChangePp: z.number().min(-10).max(20).default(0),
  oneOffExpense: money.default(0),
});

const pct = (x: number | null) => (x === null ? "—" : `${(x * 100).toFixed(1)}%`);

export const resolveInputsTool: ToolDef<
  {
    profile: z.infer<typeof ProfileValuesSchema>;
    isDemo: boolean;
    request: z.infer<typeof PurchaseRequestSchema>;
  },
  ReturnType<typeof resolveInputs>
> = {
  name: "check_inputs",
  agent: "planner",
  description:
    "Check which required inputs are present, and disclose every assumption used to fill a gap.",
  input: z.object({
    profile: ProfileValuesSchema,
    isDemo: z.boolean(),
    request: PurchaseRequestSchema,
  }),
  run: ({ profile, isDemo, request }) =>
    resolveInputs({ values: profile, sources: {}, isDemo, updatedAt: null }, request),
  summarize: (o) =>
    o.missing.length
      ? `${o.missing.length} required input(s) missing: ${o.missing.map((m) => m.label).join(", ")}`
      : `all required inputs present; ${o.assumptions.filter((a) => a.basis === "illustrative" || a.basis === "default").length} disclosed assumption(s)`,
};

export const researchTool: ToolDef<
  {
    purchaseType: (typeof PURCHASE_TYPES)[number];
    loanAmount: number;
    tenureMonths: number | null;
  },
  ResearchResult
> = {
  name: "research_financing_options",
  agent: "research",
  description: "Find financing options and rates for a purchase, with sources.",
  input: z.object({
    purchaseType: z.enum(PURCHASE_TYPES),
    loanAmount: money,
    tenureMonths: z.number().int().min(1).max(600).nullable(),
  }),
  run: (q, signal) => researchProvider().research(q, signal),
  summarize: (o) =>
    `${o.options.length} option(s) from ${o.live ? `${o.sources.length} live source(s)` : "illustrative assumptions"}${o.warnings.length ? `; ${o.warnings.length} warning(s)` : ""}`,
};

/** Fallback when live research fails: the illustrative provider, as its own recorded tool call. */
export const illustrativeResearchTool: typeof researchTool = {
  ...researchTool,
  name: "illustrative_financing_assumptions",
  description:
    "Clearly labelled illustrative financing ranges (used when live research is unavailable).",
  run: (q) => new IllustrativeResearchProvider().research(q),
};

export const compareFinancingTool: ToolDef<
  { loanAmount: number; options: { id: string; rate: number; tenureMonths: number }[] },
  { id: string; emi: number; totalInterest: number; totalRepayment: number }[]
> = {
  name: "compare_financing_options",
  agent: "analysis",
  description: "EMI, total interest and total repayment for each financing option.",
  input: z.object({
    loanAmount: money,
    options: z
      .array(
        z.object({
          id: z.string(),
          rate: z.number().min(0).max(50),
          tenureMonths: z.number().int().min(1).max(600),
        }),
      )
      .max(20),
  }),
  run: ({ loanAmount, options }) =>
    options.map((o) => {
      const emi = calculateEMI(loanAmount, o.rate, o.tenureMonths);
      const totalRepayment =
        loanAmount > 0 ? calculateTotalRepayment(loanAmount, emi, o.tenureMonths) : 0;
      return {
        id: o.id,
        emi,
        totalRepayment,
        totalInterest: calculateTotalInterest(loanAmount, totalRepayment),
      };
    }),
  summarize: (o) => {
    const best = [...o].sort((a, b) => a.totalInterest - b.totalInterest)[0];
    return best
      ? `${o.length} option(s) compared; lowest total interest ${formatINR(best.totalInterest)}`
      : "no options";
  },
};

export const calculateEmiTool: ToolDef<
  { principal: number; annualInterestRate: number; tenureMonths: number },
  { emi: number; totalRepayment: number; totalInterest: number }
> = {
  name: "calculate_emi",
  agent: "analysis",
  description: "Monthly EMI, total repayment and total interest for a loan (reducing balance).",
  input: z.object({
    principal: money,
    annualInterestRate: z.number().min(0).max(50),
    tenureMonths: z.number().int().min(1).max(600),
  }),
  run: ({ principal, annualInterestRate, tenureMonths }) => {
    const emi = calculateEMI(principal, annualInterestRate, tenureMonths);
    const totalRepayment =
      principal > 0 ? calculateTotalRepayment(principal, emi, tenureMonths) : 0;
    return {
      emi,
      totalRepayment,
      totalInterest: calculateTotalInterest(principal, totalRepayment),
    };
  },
  summarize: (o) => `EMI ${formatINR(o.emi)}, total interest ${formatINR(o.totalInterest)}`,
};

export const analysePurchaseTool: ToolDef<
  z.infer<typeof ResolvedInputsSchema>,
  PurchaseAnalysis
> = {
  name: "analyse_purchase",
  agent: "analysis",
  description:
    "Down payment, loan, EMI, post-purchase savings, debt-to-income and emergency cover, classified against the affordability rules.",
  input: ResolvedInputsSchema,
  run: ({ purchase, household }) => analysePurchase(purchase, household),
  summarize: (a) =>
    `EMI ${formatINR(a.emi)} on a ${formatINR(a.loanAmount)} loan; surplus after purchase ${formatINR(a.after.cashFlow.monthlySurplus)}/month; DTI ${pct(a.after.dti)}; ${LABEL_TEXT[a.label].toLowerCase()}`,
};

export const scenariosTool: ToolDef<
  {
    inputs: z.infer<typeof ResolvedInputsSchema>;
    scenarios?: z.infer<typeof ScenarioParamsSchema>[];
  },
  ScenarioResult[]
> = {
  name: "run_stress_scenarios",
  agent: "risk",
  description:
    "Replay the next 12 months under hypothetical stress scenarios and compare each with the baseline.",
  input: z.object({
    inputs: ResolvedInputsSchema,
    scenarios: z.array(ScenarioParamsSchema).max(10).optional(),
  }),
  run: ({ inputs, scenarios }) => {
    const baseline = analysePurchase(inputs.purchase, inputs.household);
    return runScenarioSet(
      inputs.purchase,
      inputs.household,
      baseline,
      scenarios ?? STANDARD_SCENARIOS,
    );
  },
  summarize: (o) => {
    const strained = o.filter((s) => !s.isBaseline && s.label === "high_strain").length;
    return `${o.length - 1} scenario(s) run; ${strained} breach a safety rule`;
  },
};

export const comfortablePriceTool: ToolDef<
  z.infer<typeof ResolvedInputsSchema>,
  { price: number | null }
> = {
  name: "find_comfortable_price",
  agent: "analysis",
  description:
    "Highest purchase price classed as comfortable under the same down payment, rate and tenure.",
  input: ResolvedInputsSchema,
  run: ({ purchase, household }) => ({ price: findComfortablePrice(purchase, household) }),
  summarize: (o) =>
    o.price === null
      ? "no price is comfortable under these assumptions"
      : `comfortable up to about ${formatINR(o.price)}`,
};

export const savingsPlanTool: ToolDef<
  {
    targetAmount: number;
    currentSavings: number;
    monthlySaving: number | null;
    months: number | null;
  },
  { monthlySaving: number | null; months: number | null }
> = {
  name: "plan_savings",
  agent: "analysis",
  description:
    "Monthly saving needed to reach a target in N months, or months needed at a given monthly saving.",
  input: z.object({
    targetAmount: money,
    currentSavings: money,
    monthlySaving: money.nullable(),
    months: z.number().int().min(1).max(600).nullable(),
  }),
  run: ({ targetAmount, currentSavings, monthlySaving, months }) => {
    if (months !== null)
      return {
        monthlySaving: monthlySavingsRequired(targetAmount, currentSavings, months),
        months,
      };
    return {
      monthlySaving,
      months: monthsToReachGoal(targetAmount - currentSavings, monthlySaving ?? 0),
    };
  },
  summarize: (o) =>
    o.months === null
      ? "goal not reachable at this saving rate"
      : `${formatINR(o.monthlySaving ?? 0)}/month for ${o.months} month(s)`,
};

export const verifyTool: ToolDef<VerificationInput, ReturnType<typeof verify>> = {
  name: "verify_inputs_and_assumptions",
  agent: "verification",
  description:
    "Consistency checks, document cross-checks and challenges to optimistic assumptions.",
  // Internal objects produced by other tools: validated structurally where it matters.
  input: z.custom<VerificationInput>(
    (v) =>
      typeof v === "object" &&
      v !== null &&
      ResolvedInputsSchema.safeParse((v as VerificationInput).inputs).success,
    "verification input must include valid resolved inputs",
  ),
  run: (input) => verify(input),
  summarize: (o) => {
    const by = (s: string) => o.filter((f) => f.severity === s).length;
    return `${o.length} finding(s): ${by("critical")} critical, ${by("warning")} warning, ${by("info")} info`;
  },
};

export const actionPlanTool: ToolDef<ActionPlanInput, ReturnType<typeof buildActionPlan>> = {
  name: "prepare_action_plan",
  agent: "action",
  description:
    "Draft a next-step checklist, document list and application answers for the user to review.",
  input: z.custom<ActionPlanInput>(
    (v) => typeof v === "object" && v !== null && "request" in v && "analysis" in v,
  ),
  run: (input) => buildActionPlan(input),
  summarize: (o) =>
    `${o.items.length} checklist item(s), ${o.documentsNeeded.length} document(s), ${o.draftAnswers.length} draft answer(s)`,
};

export function optionsForComparison(
  research: ResearchResult,
): { id: string; rate: number; tenureMonths: number }[] {
  return research.options.map((o: FinancingOption) => ({
    id: o.id,
    rate: o.rateUsed,
    tenureMonths: o.tenureMonths,
  }));
}
