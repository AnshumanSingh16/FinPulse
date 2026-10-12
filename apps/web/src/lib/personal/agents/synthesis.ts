/**
 * Synthesis: the orchestrator's final step. The recommendation label comes from the deterministic
 * rules; the alternatives are computed with the same tools; the optional AI narrative may only use
 * figures that a tool produced — a numeric verifier rejects it otherwise.
 */
import "server-only";

import { formatINR } from "@/lib/format";

import type { PurchaseAnalysis } from "../finance/affordability";
import { findINRAmounts } from "../finance/parse-inr";
import type { ScenarioResult } from "../finance/scenarios";
import { describeAiError, effort, getClient, modelId, textOf } from "./llm";
import type { RunContext } from "./runtime";
import { calculateEmiTool, comfortablePriceTool, savingsPlanTool } from "./tools";
import type { Alternative, Finding, Recommendation, ResolvedInputs } from "./types";

const HEADLINE = {
  comfortable: "Looks affordable under the stated assumptions",
  manageable_limited_buffer: "Possible, but the safety buffer would be thin",
  high_strain: "Not advisable as currently planned",
  insufficient_information: "Not enough information for a reliable answer",
} as const;

const MAX_TENURE: Record<string, number> = {
  house: 300,
  car: 84,
  education: 120,
  business: 84,
  custom: 60,
};

export async function buildAlternatives(
  ctx: RunContext,
  inputs: ResolvedInputs,
  analysis: PurchaseAnalysis,
  preferredBufferMonths: number,
  stepId: string,
): Promise<Alternative[]> {
  const out: Alternative[] = [];
  const { purchase } = inputs;

  const comfortable = await ctx.callTool(comfortablePriceTool, inputs, stepId);
  if (comfortable.price !== null && comfortable.price < purchase.purchasePrice) {
    out.push({
      id: "lower_price",
      title: `Target a price up to about ${formatINR(comfortable.price, { compact: true })}`,
      description:
        "The highest price that passes every affordability rule with the same down-payment %, rate and tenure.",
      figures: [
        { label: "Comfortable price", value: comfortable.price, unit: "INR" },
        {
          label: "Difference from asked price",
          value: purchase.purchasePrice - comfortable.price,
          unit: "INR",
        },
      ],
    });
  } else if (comfortable.price === null) {
    out.push({
      id: "lower_price",
      title: "No price passes every rule with these assumptions",
      description:
        "Even a much cheaper purchase would breach a rule, usually because current cash flow or savings are already tight. Strengthen the base first.",
      figures: [],
    });
  }

  if (analysis.label !== "comfortable" && analysis.after.cashFlow.totalMonthlyOutflow > 0) {
    const targetBuffer = preferredBufferMonths * analysis.after.cashFlow.totalMonthlyOutflow;
    const gap = Math.max(0, Math.round(targetBuffer - analysis.postPurchaseSavings));
    const monthlySaving = Math.max(0, Math.round(analysis.before.cashFlow.monthlySurplus * 0.5));
    if (gap > 0) {
      const plan = await ctx.callTool(
        savingsPlanTool,
        { targetAmount: gap, currentSavings: 0, monthlySaving, months: null },
        stepId,
      );
      if (plan.months !== null) {
        out.push({
          id: "save_first",
          title: `Save for about ${plan.months} months first`,
          description: `Builds ${preferredBufferMonths} months of post-purchase emergency cover. Assumes you save half of today's monthly surplus (${formatINR(monthlySaving)}); saving more shortens this.`,
          figures: [
            { label: "Additional savings needed", value: gap, unit: "INR" },
            { label: "Monthly saving assumed", value: monthlySaving, unit: "INR" },
            { label: "Months", value: plan.months, unit: "months" },
          ],
        });
      }
    }
  }

  const maxTenure = MAX_TENURE[String(ctx.run.request.type)] ?? 60;
  if (analysis.loanAmount > 0 && purchase.tenureMonths < maxTenure) {
    const longer = await ctx.callTool(
      calculateEmiTool,
      {
        principal: analysis.loanAmount,
        annualInterestRate: purchase.annualInterestRate,
        tenureMonths: maxTenure,
      },
      stepId,
    );
    out.push({
      id: "longer_tenure",
      title: `Stretch the tenure to ${maxTenure / 12} years`,
      description:
        "Lowers the EMI but raises total interest — a trade-off, not a free improvement. Prepaying later can claw some interest back.",
      figures: [
        { label: "EMI", value: longer.emi, unit: "INR" },
        { label: "EMI reduction", value: Math.round(analysis.emi - longer.emi), unit: "INR" },
        {
          label: "Extra total interest",
          value: Math.round(longer.totalInterest - analysis.totalInterest),
          unit: "INR",
        },
      ],
    });
  }
  return out;
}

export function buildSummary(
  analysis: PurchaseAnalysis,
  scenarios: ScenarioResult[],
  findings: Finding[],
): string[] {
  const a = analysis;
  const lines = [
    a.loanAmount > 0
      ? `Borrowing ${formatINR(a.loanAmount)} means an EMI of ${formatINR(a.emi)} a month, and ${formatINR(a.totalInterest)} of interest over the loan.`
      : `No loan is needed: the purchase is paid in cash.`,
    `You would pay ${formatINR(a.upfrontCash)} upfront, leaving ${formatINR(a.postPurchaseSavings)} in liquid savings (${a.after.emergencyMonths === null ? "—" : a.after.emergencyMonths.toFixed(1)} months of essential spending).`,
    `After all EMIs and expenses, ${a.after.cashFlow.monthlySurplus >= 0 ? `${formatINR(a.after.cashFlow.monthlySurplus)} would be left each month` : `you would be short by ${formatINR(-a.after.cashFlow.monthlySurplus)} each month`}; EMIs would take ${a.after.dti === null ? "—" : `${(a.after.dti * 100).toFixed(1)}%`} of take-home pay.`,
  ];
  const strained = scenarios.filter((s) => !s.isBaseline && s.label === "high_strain");
  if (strained.length)
    lines.push(
      `${strained.length} of ${scenarios.length - 1} stress scenarios breach a safety rule — worst: ${strained[0]!.params.name.toLowerCase()}.`,
    );
  else lines.push(`All ${scenarios.length - 1} stress scenarios stay within the rules.`);
  const critical = findings.filter((f) => f.severity === "critical").length;
  if (critical)
    lines.push(
      `Verification raised ${critical} critical issue${critical === 1 ? "" : "s"} to resolve before relying on this.`,
    );
  return lines;
}

/** Numbers in the narrative must match a tool-produced figure (₹ within 1%, % within 0.15 pp). */
export function verifyFigures(
  text: string,
  allowedRupees: number[],
  allowedPercents: number[],
): string[] {
  const bad: string[] = [];
  for (const a of findINRAmounts(text)) {
    if (!a.hasCurrency && !a.hasUnit) continue;
    const ok = allowedRupees.some((v) => Math.abs(v - a.value) <= Math.max(1, Math.abs(v) * 0.01));
    if (!ok) bad.push(a.text);
  }
  for (const m of text.matchAll(/(\d+(?:\.\d+)?)\s*%/g)) {
    const n = Number(m[1]);
    if (!allowedPercents.some((p) => Math.abs(p - n) <= 0.15)) bad.push(m[0]);
  }
  return bad;
}

function collectNumbers(value: unknown, out: number[] = []): number[] {
  if (typeof value === "number" && Number.isFinite(value)) out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => collectNumbers(v, out));
  else if (value && typeof value === "object")
    Object.values(value).forEach((v) => collectNumbers(v, out));
  return out;
}

export async function aiNarrative(
  ctx: RunContext,
  facts: Record<string, unknown>,
  stepId: string,
): Promise<Recommendation["narrative"]> {
  if (!ctx.run.mode.ai) return null;
  if (!ctx.useLlmCall()) {
    ctx.emit("planner", "llm", "Skipped AI explanation: model-call limit for this run reached", {
      stepId,
      level: "warning",
    });
    return null;
  }
  ctx.emit(
    "planner",
    "llm",
    "Asking the AI model for a plain-English explanation of the computed results",
    { stepId },
  );
  try {
    const response = await getClient().messages.create(
      {
        model: modelId(),
        max_tokens: 2000,
        output_config: { effort: effort() },
        system:
          "You are FinPulse's Financial Planner. Explain an affordability result to an Indian user in 3-4 short plain-English sentences. Use ONLY figures present in the JSON facts (Indian formatting like ₹52,069 or ₹60 lakh is fine). Never invent rates, lender offers or numbers; do not promise loan approval; it is decision support, not advice. No headings, no lists.",
        messages: [
          {
            role: "user",
            content: `Facts (computed by FinPulse's deterministic tools):\n${JSON.stringify(facts)}`,
          },
        ],
      },
      { signal: ctx.controller.signal },
    );
    if (response.stop_reason === "refusal") {
      ctx.emit("planner", "llm", "The AI model declined; the template summary is shown instead", {
        stepId,
        level: "warning",
      });
      return null;
    }
    const text = textOf(response.content);
    const numbers = collectNumbers(facts);
    const percents = numbers.flatMap((n) => (Math.abs(n) <= 1.5 ? [n * 100] : [n]));
    const unverified = verifyFigures(text, numbers, percents);
    if (unverified.length) {
      ctx.emit(
        "verification",
        "finding",
        `Rejected the AI explanation: ${unverified.length} figure(s) did not match any tool output (${unverified.slice(0, 3).join(", ")})`,
        { stepId, level: "warning" },
      );
      return null;
    }
    ctx.emit(
      "verification",
      "finding",
      "AI explanation passed the figure check: every number matches a tool output",
      { stepId },
    );
    return { text, mode: "ai", unverifiedFigures: [] };
  } catch (error) {
    ctx.emit(
      "planner",
      "llm",
      `AI explanation unavailable: ${describeAiError(error)}. Template summary shown instead.`,
      { stepId, level: "warning" },
    );
    return null;
  }
}

export function buildRecommendation(
  analysis: PurchaseAnalysis,
  summary: string[],
  alternatives: Alternative[],
  narrative: Recommendation["narrative"],
): Recommendation {
  return {
    label: analysis.label,
    headline: HEADLINE[analysis.label],
    summary,
    narrative,
    alternatives,
  };
}
