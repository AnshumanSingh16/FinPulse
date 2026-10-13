/**
 * Financial Planner Agent: decides what information the analysis needs, what is missing, which
 * gaps can be bridged with a disclosed assumption, and which agents/tools to run.
 */
import { formatINR } from "@/lib/format";

import {
  DEMO_PURCHASE,
  type FieldSource,
  type FinancialProfile,
  type PurchaseRequest,
  type PurchaseType,
} from "../schemas";
import { DEFAULT_TENURE } from "./research";
import type { Assumption, MissingInput, PlanStep, ResolvedInputs } from "./types";

const REQUIRED_PROFILE = [
  ["monthlyIncome", "Monthly take-home income", "What is your monthly take-home (in-hand) income?"],
  [
    "monthlyExpenses",
    "Monthly living expenses",
    "Roughly how much do you spend each month on living expenses (rent, food, bills, transport)?",
  ],
  [
    "liquidSavings",
    "Liquid savings",
    "How much do you have in savings you could use quickly (bank balance, FDs, liquid funds)?",
  ],
  [
    "existingEmis",
    "Existing EMIs",
    "Do you pay any EMIs today? Enter the monthly total (₹0 if none).",
  ],
] as const;

const DEFAULT_DOWN_PAYMENT: Record<PurchaseType, number> = {
  house: 20,
  car: 20,
  education: 10,
  business: 25,
  custom: 20,
};

/** Upfront cash costs when the user gave none, as a share of price, with the reason. */
const DEFAULT_UPFRONT: Record<PurchaseType, { share: number; note: string }> = {
  house: {
    share: 0.06,
    note: "Illustrative 6% of price for stamp duty, registration and fees. Stamp duty varies by state (roughly 5–8% incl. registration); replace with your actual figure.",
  },
  car: {
    share: 0,
    note: "Assumed the price is the on-road price (registration and first-year insurance included).",
  },
  education: {
    share: 0,
    note: "Assumed no separate upfront costs beyond the fees being financed.",
  },
  business: { share: 0, note: "Assumed no separate upfront costs; add setup costs if any." },
  custom: { share: 0, note: "Assumed no separate upfront costs." },
};

export type InputResolution = {
  missing: MissingInput[];
  assumptions: Assumption[];
  /** Null when required information is missing. */
  inputs: ResolvedInputs | null;
  /** True when no rate was given: the Research Agent must supply one (disclosed). */
  needsRate: boolean;
};

function basisOf(source: FieldSource | undefined): Assumption["basis"] {
  if (!source) return "user";
  if (source.kind === "demo") return "demo";
  if (source.kind === "document") return "document";
  return "user";
}

export function resolveInputs(
  profile: FinancialProfile,
  request: PurchaseRequest,
): InputResolution {
  const v = profile.values;
  const missing: MissingInput[] = [];
  const assumptions: Assumption[] = [];
  for (const [field, label, question] of REQUIRED_PROFILE) {
    const value = v[field];
    if (value === null || value === undefined) missing.push({ field, label, question });
    else
      assumptions.push({
        id: `in_${field}`,
        field: label,
        value: formatINR(value),
        basis: basisOf(profile.sources[field]),
        note: profile.sources[field]?.note ?? "From your financial profile",
      });
  }
  assumptions.push({
    id: "in_price",
    field: "Purchase price",
    value: formatINR(request.price),
    basis: "user",
    note: request.label,
  });

  const downPaymentPct = request.downPaymentPct ?? DEFAULT_DOWN_PAYMENT[request.type];
  assumptions.push({
    id: "in_down",
    field: "Down payment",
    value: `${downPaymentPct}%`,
    basis: request.downPaymentPct === null ? "default" : "user",
    note:
      request.downPaymentPct === null
        ? "No down payment given: a common starting point was assumed. Change it to match your plan."
        : "As entered",
  });

  let upfront = request.upfrontCosts;
  if (upfront === null) {
    const d = DEFAULT_UPFRONT[request.type];
    upfront = Math.round(request.price * d.share);
    assumptions.push({
      id: "in_upfront",
      field: "Upfront costs",
      value: formatINR(upfront),
      basis: "illustrative",
      note: d.note,
    });
  } else {
    assumptions.push({
      id: "in_upfront",
      field: "Upfront costs",
      value: formatINR(upfront),
      basis: "user",
      note: request.financeUpfrontCosts ? "Added to the loan" : "Paid in cash",
    });
  }

  const tenure = request.tenureMonths ?? DEFAULT_TENURE[request.type];
  assumptions.push({
    id: "in_tenure",
    field: "Loan tenure",
    value: `${tenure} months (${(tenure / 12).toFixed(tenure % 12 ? 1 : 0)} years)`,
    basis: request.tenureMonths === null ? "default" : "user",
    note:
      request.tenureMonths === null
        ? "No tenure given: a typical tenure for this loan type was assumed."
        : "As entered",
  });

  if (request.interestRate !== null) {
    const demoRate = profile.isDemo && request.interestRate === DEMO_PURCHASE.interestRate;
    assumptions.push({
      id: "in_rate",
      field: "Interest rate",
      value: `${request.interestRate}% p.a.`,
      basis: demoRate ? "demo" : "user",
      note: demoRate
        ? "Illustrative demo assumption, not a current lender quote."
        : "As entered. Floating rates can change over the loan's life.",
    });
  }

  const ownership = request.monthlyOwnershipCost ?? 0;
  assumptions.push({
    id: "in_ownership",
    field: "Monthly ownership costs",
    value: formatINR(ownership),
    basis: request.monthlyOwnershipCost === null ? "default" : "user",
    note:
      request.monthlyOwnershipCost === null
        ? "Not provided, so none are included. Maintenance, insurance, fuel or society charges would reduce your monthly surplus."
        : "As entered",
  });

  const other = v.otherMonthlyObligations ?? 0;
  if (v.otherMonthlyObligations === null) {
    assumptions.push({
      id: "in_other",
      field: "Other fixed obligations",
      value: "₹0",
      basis: "default",
      note: "Not provided; assumed none (insurance premiums, SIP commitments, family support).",
    });
  }

  if (missing.length)
    return { missing, assumptions, inputs: null, needsRate: request.interestRate === null };

  return {
    missing,
    assumptions,
    needsRate: request.interestRate === null,
    inputs: {
      purchase: {
        purchasePrice: request.price,
        downPaymentPct,
        upfrontCashCosts: request.financeUpfrontCosts ? 0 : upfront,
        financedCosts: request.financeUpfrontCosts ? upfront : 0,
        annualInterestRate: request.interestRate ?? 0,
        tenureMonths: tenure,
        monthlyOwnershipCost: ownership,
      },
      household: {
        monthlyIncome: v.monthlyIncome!,
        monthlyExpenses: v.monthlyExpenses!,
        existingEmis: v.existingEmis!,
        otherMonthlyObligations: other,
        liquidSavings: v.liquidSavings!,
      },
    },
  };
}

/** The task plan for an affordability question. Steps run in order; each names its agent. */
export function buildPlan(opts: {
  research: boolean;
  liveResearch: boolean;
  /** Number of goals saved in the person's plan; 0 skips the plan-impact step. */
  goals?: number;
}): PlanStep[] {
  const step = (id: string, agent: PlanStep["agent"], title: string, why: string): PlanStep => ({
    id,
    agent,
    title,
    why,
    status: "pending",
    toolCallIds: [],
  });
  return [
    step(
      "understand",
      "planner",
      "Understanding your goal",
      "Reading what you want to buy and the details you mentioned.",
    ),
    step(
      "collect",
      "planner",
      "Checking your financial profile",
      "A reliable answer needs income, expenses, savings and existing EMIs.",
    ),
    ...(opts.research
      ? [
          step(
            "research",
            "research",
            "Researching available options",
            opts.liveResearch
              ? "Live web search for published rates; each kept only with a retrieved source."
              : "Live research isn't configured, so clearly labelled illustrative ranges are used.",
          ),
        ]
      : []),
    step(
      "analyse",
      "analysis",
      "Calculating costs",
      "EMI, interest, upfront cash and what's left each month, from tested formulas.",
    ),
    step(
      "stress",
      "risk",
      "Stress-testing your finances",
      "What happens if income falls, costs or rates rise, or a shock hits.",
    ),
    ...(opts.goals
      ? [
          step(
            "plan",
            "analysis",
            "Checking your other goals",
            `All ${opts.goals} saved goal(s), with and without this purchase, across 400 possible futures.`,
          ),
          step(
            "fit",
            "strategist",
            "Finding the best way to fit it in",
            "If it hurts your other goals: the smallest changes to dates, budgets, loans or spending that help most.",
          ),
        ]
      : []),
    step(
      "verify",
      "verification",
      "Verifying assumptions",
      "Flagging missing, inconsistent or optimistic inputs.",
    ),
    step(
      "synthesise",
      "planner",
      "Preparing your recommendation",
      "Combining the findings and working out safer alternatives.",
    ),
    step(
      "act",
      "action",
      "Preparing your next steps",
      "A checklist for you to review. Nothing is submitted anywhere.",
    ),
  ];
}
