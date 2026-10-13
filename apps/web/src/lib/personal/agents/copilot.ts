/**
 * AI Financial Copilot. Natural-language requests are answered by calling FinPulse's tools:
 *  - with an AI key: a real tool-use loop (Claude chooses tools; the app validates and runs them;
 *    capped at 6 model turns), and every figure in the reply is checked against tool outputs;
 *  - without one: a rule-based router that recognises the common requests, runs the same tools,
 *    and answers from templates. It is labelled as such and never presented as AI output.
 */
import "server-only";

import type Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";

import { formatINR } from "@/lib/format";

import { analysePurchase, LABEL_TEXT } from "../finance/affordability";
import {
  emergencyFundCoverageMonths,
  monthlySavingsRequired,
  summariseCashFlow,
} from "../finance/health";
import { findINRAmounts, inrWords } from "../finance/parse-inr";
import { runScenarioSet, type ScenarioParams } from "../finance/scenarios";
import { detectPurchaseType } from "../goal";
import { PURCHASE_TYPES, type PurchaseRequest } from "../schemas";
import { audit, newId, type SessionState } from "../store";
import { aiStatus, describeAiError, effort, getClient, modelId, UNTRUSTED_DATA_RULE } from "./llm";
import { runAffordabilityWorkflow, type WorkflowListener } from "./orchestrator";
import { illustrativeRate, DEFAULT_TENURE } from "./research";
import { verifyFigures } from "./synthesis";
import { currentMonth } from "../finance/plan";
import { GOAL_KIND_LABEL, projectFor, pulse } from "../plan-model";
import { prepayVsInvestTool, rentVsBuyTool } from "./plan-tools";
import { calculateEmiTool, savingsPlanTool } from "./tools";
import type { AgentEvent, WorkflowRun } from "./types";

export type CopilotToolCall = {
  id: string;
  tool: string;
  input: unknown;
  summary: string;
  status: "ok" | "error";
};

export type CopilotStreamItem =
  | { type: "tool"; call: CopilotToolCall }
  | { type: "event"; event: AgentEvent }
  | { type: "run"; runId: string; status: WorkflowRun["status"] }
  | {
      type: "message";
      text: string;
      mode: "ai" | "rule_based";
      unverifiedFigures: string[];
      notice?: string;
    };

type Emit = (item: CopilotStreamItem) => void;

// ---------------------------------------------------------------- shared tool implementations

const AffordArgs = z.object({
  purchase_type: z.enum(PURCHASE_TYPES),
  price: z.number().min(1000).max(1e11),
  label: z.string().max(80).optional(),
  down_payment_pct: z.number().min(0).max(100).optional(),
  interest_rate: z.number().min(0).max(50).optional(),
  tenure_months: z.number().int().min(1).max(600).optional(),
});
const ScenarioArgs = z.object({
  name: z.string().max(80).optional(),
  income_change_pct: z.number().min(-100).max(200).optional(),
  income_stop_months: z.number().int().min(0).max(36).optional(),
  expense_change_pct: z.number().min(-90).max(300).optional(),
  rate_change_pp: z.number().min(-10).max(20).optional(),
  one_off_expense: z.number().min(0).max(1e11).optional(),
});
const CompareArgs = z.object({
  purchase_type: z.enum(PURCHASE_TYPES),
  prices: z.array(z.number().min(1000).max(1e11)).min(2).max(4),
  down_payment_pct: z.number().min(0).max(100).optional(),
  interest_rate: z.number().min(0).max(50).optional(),
  tenure_months: z.number().int().min(1).max(600).optional(),
});
const SavingsArgs = z.object({
  target_amount: z.number().min(0).max(1e11),
  months: z.number().int().min(1).max(600),
});
const EmiArgs = z.object({
  principal: z.number().min(0).max(1e11),
  annual_interest_rate: z.number().min(0).max(50),
  tenure_months: z.number().int().min(1).max(600),
});
const Empty = z.object({});

/** The analysis the user is looking at (focus), else the most recent completed one. */
function latestCompleted(session: SessionState): WorkflowRun | undefined {
  const usable = (r: WorkflowRun) => r.status === "completed" && r.inputs && r.analysis;
  const focused = session.focusRunId
    ? session.runs.find((r) => r.id === session.focusRunId && usable(r))
    : undefined;
  return focused ?? session.runs.find(usable);
}

/** Core household figures from the profile, or which are missing. */
function household(session: SessionState) {
  const v = session.profile.values;
  const missing = (
    ["monthlyIncome", "monthlyExpenses", "liquidSavings", "existingEmis"] as const
  ).filter((k) => v[k] === null);
  if (missing.length) return { missing };
  const flow = summariseCashFlow({
    monthlyIncome: v.monthlyIncome!,
    monthlyExpenses: v.monthlyExpenses!,
    monthlyDebtPayments: v.existingEmis!,
    monthlyOtherObligations: v.otherMonthlyObligations ?? 0,
  });
  return { missing, v, flow };
}

function runDigest(run: WorkflowRun) {
  const a = run.analysis!;
  return {
    run_id: run.id,
    purchase: run.request.label,
    assessment: LABEL_TEXT[a.label],
    price: run.inputs!.purchase.purchasePrice,
    loan_amount: a.loanAmount,
    emi: a.emi,
    rate_percent: run.inputs!.purchase.annualInterestRate,
    rate_basis: run.assumptions.find((x) => x.id === "in_rate")?.basis,
    total_interest: a.totalInterest,
    savings_after_purchase: a.postPurchaseSavings,
    monthly_surplus_after: a.after.cashFlow.monthlySurplus,
    debt_to_income_after: a.after.dti,
    emergency_months_after: a.after.emergencyMonths,
    failed_or_warning_checks: a.checks
      .filter((c) => c.status !== "pass")
      .map((c) => `${c.label}: ${c.status}`),
    scenarios: run.scenarios
      ?.filter((s) => !s.isBaseline)
      .map((s) => ({
        name: s.params.name,
        assessment: s.label,
        savings_run_out_month: s.monthExhausted,
        monthly_surplus: s.monthlySurplus,
      })),
    key_findings: run.findings
      .filter((f) => f.severity !== "info")
      .map((f) => f.message)
      .slice(0, 8),
    alternatives: run.recommendation?.alternatives.map((x) => ({
      title: x.title,
      figures: x.figures,
    })),
  };
}

type ToolImpl = {
  description: string;
  schema: z.ZodType;
  run: (
    args: never,
    session: SessionState,
    listener: WorkflowListener,
    emit: Emit,
  ) => Promise<unknown>;
  summarize: (output: unknown) => string;
};

function purchaseFromArgs(a: z.infer<typeof AffordArgs>): PurchaseRequest {
  return {
    type: a.purchase_type,
    label:
      a.label?.trim() ||
      `${inrWords(a.price)} ${a.purchase_type === "custom" ? "purchase" : a.purchase_type}`,
    price: a.price,
    downPaymentPct: a.down_payment_pct ?? null,
    upfrontCosts: null,
    financeUpfrontCosts: false,
    interestRate: a.interest_rate ?? null,
    tenureMonths: a.tenure_months ?? null,
    monthlyOwnershipCost: null,
    researchFinancing: true,
  };
}

const TOOLS: Record<string, ToolImpl> = {
  review_goal_plan: {
    description:
      "The person's saved goal plan projected month by month: each goal's status (on track / late / out of reach), when it is reached, what it needs each month, the spare money left after goals, and the monthly check-in trend.",
    schema: Empty,
    run: async (_args, session) => {
      const month = currentMonth();
      const input = {
        profile: session.profile.values,
        goals: session.goals,
        assumptions: session.planAssumptions,
        startMonth: month,
      };
      const p = projectFor(input);
      if (!p.projection) return { error: `The profile is missing: ${p.missing.join(", ")}.` };
      const pl = pulse({ ...input, checkIns: session.checkIns });
      return {
        goals: p.projection.goals.map((g) => ({
          name: g.name,
          type: GOAL_KIND_LABEL[g.kind],
          priority: g.priority,
          wanted_by: g.targetMonth,
          status: g.status,
          reached_in: g.achievedMonth,
          months_late: g.delayMonths,
          monthly_needed: g.requiredMonthly,
          monthly_funded: g.allocatedMonthly,
          cash_needed_on_date: g.cashNeededAtTarget,
        })),
        monthly_surplus_now: p.projection.summary.surplusNow,
        spare_monthly_after_goals: p.projection.summary.freeMonthlyNow,
        emergency_reserve_target: p.projection.summary.reserveTarget,
        plan_status: p.projection.summary.status,
        check_in_trend: pl.trend,
        average_monthly_gap_vs_plan: pl.averageGap,
        goals_moved_if_trend_continues: pl.ifContinues.map((c) => ({
          name: c.name,
          moves_to: c.after.achievedMonth,
          extra_months: c.extraDelayMonths,
        })),
      };
    },
    summarize: (o) => {
      const r = o as { error?: string; goals?: { status: string }[]; plan_status?: string };
      if (r.error) return "profile incomplete";
      return `${r.goals!.length} goal(s), ${r.goals!.filter((g) => g.status === "on_track").length} on track`;
    },
  },
  compare_rent_vs_buy: {
    description:
      "Rent vs buy for a home: buying (EMI, maintenance, appreciation) against renting a similar home and investing the difference, year by year. Unspecified rates use disclosed defaults.",
    schema: z.object({
      price: z.number().min(100_000),
      monthly_rent: z.number().min(0),
      years: z.number().int().min(1).max(30).optional(),
      appreciation_pct: z.number().min(0).max(20).optional(),
      loan_rate_pct: z.number().min(0).max(30).optional(),
    }),
    run: async (a: {
      price: number;
      monthly_rent: number;
      years?: number;
      appreciation_pct?: number;
      loan_rate_pct?: number;
    }) => {
      const input = rentVsBuyTool.input.parse({
        price: a.price,
        monthlyRent: a.monthly_rent,
        ...(a.years ? { years: a.years } : {}),
        ...(a.appreciation_pct !== undefined ? { appreciationPct: a.appreciation_pct } : {}),
        ...(a.loan_rate_pct !== undefined ? { loanRatePct: a.loan_rate_pct } : {}),
      });
      const r = await rentVsBuyTool.run(input, new AbortController().signal);
      const last = r.years[r.years.length - 1]!;
      return {
        assumptions: input,
        emi: r.emi,
        cash_needed_to_buy: r.upfrontCash,
        winner: r.winner,
        buyer_wealth_at_horizon: last.buyerWealth,
        renter_wealth_at_horizon: last.renterWealth,
        difference: r.difference,
        buying_ahead_from_year: r.breakevenYear,
        appreciation_needed_to_break_even_pct: r.breakevenAppreciationPct,
      };
    },
    summarize: (o) => `${(o as { winner: string }).winner} ahead at the horizon`,
  },
  compare_prepay_vs_invest: {
    description:
      "Prepaying a loan (EMI kept, loan ends sooner) vs investing the same lump sum, compared on the loan's original end date after tax on gains. Also returns the break-even investment return.",
    schema: z.object({
      outstanding: z.number().min(1000),
      loan_rate_pct: z.number().min(0).max(30),
      remaining_months: z.number().int().min(1).max(360),
      lump_sum: z.number().min(1000),
      invest_return_pct: z.number().min(0).max(20).optional(),
    }),
    run: async (a: {
      outstanding: number;
      loan_rate_pct: number;
      remaining_months: number;
      lump_sum: number;
      invest_return_pct?: number;
    }) => {
      const input = prepayVsInvestTool.input.parse({
        outstanding: a.outstanding,
        loanRatePct: a.loan_rate_pct,
        remainingMonths: a.remaining_months,
        lumpSum: a.lump_sum,
        ...(a.invest_return_pct !== undefined ? { investReturnPct: a.invest_return_pct } : {}),
      });
      const r = await prepayVsInvestTool.run(input, new AbortController().signal);
      return {
        assumptions: input,
        emi: r.emi,
        interest_saved_by_prepaying: r.prepay.interestSaved,
        months_saved: r.prepay.monthsSaved,
        prepay_corpus_at_loan_end: r.prepay.corpusAtOriginalEnd,
        invest_corpus_at_loan_end: r.invest.corpusAtOriginalEnd,
        winner: r.winner,
        difference: r.difference,
        breakeven_return_pct: r.breakevenReturnPct,
      };
    },
    summarize: (o) => `${(o as { winner: string }).winner} ahead`,
  },
  plan_emergency_fund: {
    description:
      "Emergency-fund plan from the saved profile: target (months of essential spending), current cover, gap, and the monthly saving needed to close it in N months (default 12).",
    schema: z.object({
      target_months: z.number().min(1).max(24).optional(),
      months_to_build: z.number().int().min(1).max(120).optional(),
    }),
    run: async (args: { target_months?: number; months_to_build?: number }, session) => {
      const h = household(session);
      if (!h.flow) return { error: `The profile is missing: ${h.missing.join(", ")}.` };
      const targetMonths = args.target_months ?? h.v.emergencyBufferMonths ?? 6;
      const months = args.months_to_build ?? 12;
      const outflow = h.flow.totalMonthlyOutflow;
      const target = Math.round(targetMonths * outflow);
      const gap = Math.max(0, target - h.v.liquidSavings!);
      return {
        monthly_essential_spending: outflow,
        target_months: targetMonths,
        target_amount: target,
        current_savings: h.v.liquidSavings,
        current_cover_months: emergencyFundCoverageMonths(h.v.liquidSavings!, outflow),
        gap,
        months_to_build: months,
        monthly_saving_needed: gap ? monthlySavingsRequired(gap, 0, months) : 0,
        monthly_surplus_now: h.flow.monthlySurplus,
      };
    },
    summarize: (o) => {
      const r = o as { error?: string; gap?: number };
      return r.error ?? (r.gap ? `gap of ${formatINR(r.gap)}` : "target already met");
    },
  },
  stress_test_profile: {
    description:
      "Stress-test the household as it is today (no purchase): what happens if income stops, falls 20%, or expenses rise 15%. Uses the saved profile.",
    schema: z.object({}),
    run: async (_args, session) => {
      const h = household(session);
      if (!h.flow) return { error: `The profile is missing: ${h.missing.join(", ")}.` };
      const { v, flow } = h;
      const outflow = flow.totalMonthlyOutflow;
      return {
        monthly_surplus_now: flow.monthlySurplus,
        months_savings_last_with_no_income: emergencyFundCoverageMonths(v.liquidSavings!, outflow),
        surplus_if_income_falls_20pct: Math.round(v.monthlyIncome! * 0.8 - outflow),
        surplus_if_expenses_rise_15pct: Math.round(
          v.monthlyIncome! - (outflow + v.monthlyExpenses! * 0.15),
        ),
        note: "Hypothetical scenarios on today's finances, not predictions.",
      };
    },
    summarize: (o) => ((o as { error?: string }).error ? "profile incomplete" : "3 scenarios run"),
  },
  get_financial_profile: {
    description: "The user's financial profile (values and where each came from).",
    schema: Empty,
    run: async (_args, session) => ({
      values: session.profile.values,
      sources: session.profile.sources,
      is_demo: session.profile.isDemo,
    }),
    summarize: () => "profile loaded",
  },
  analyse_affordability: {
    description:
      "Run FinPulse's full multi-agent affordability workflow (plan, research, calculations, stress tests, verification, recommendation, action checklist) for a purchase, using the saved profile. Use for any 'can I afford X' question. Omit optional fields the user did not state.",
    schema: AffordArgs,
    run: async (args: z.infer<typeof AffordArgs>, session, listener, emit) => {
      const run = await runAffordabilityWorkflow(
        session,
        `Copilot: can I afford ${purchaseFromArgs(args).label}?`,
        purchaseFromArgs(args),
        listener,
      );
      emit({ type: "run", runId: run.id, status: run.status });
      if (run.status === "needs_input") return { status: "needs_input", missing: run.missing };
      if (run.status === "failed") return { status: "failed", error: run.error };
      return { status: "completed", ...runDigest(run) };
    },
    summarize: (o) => {
      const r = o as { status: string; assessment?: string };
      return r.status === "completed"
        ? `workflow completed: ${r.assessment}`
        : `workflow ${r.status}`;
    },
  },
  run_stress_scenario: {
    description:
      "Hypothetical what-if on the latest completed affordability analysis: income change %, months without income, expense change %, interest-rate change in percentage points, one-off expense in ₹.",
    schema: ScenarioArgs,
    run: async (args: z.infer<typeof ScenarioArgs>, session) => {
      const run = latestCompleted(session);
      if (!run) return { error: "No completed affordability analysis yet. Run one first." };
      const params: ScenarioParams = {
        id: "copilot",
        name: args.name ?? "Custom scenario",
        incomeChangePct: args.income_change_pct ?? 0,
        incomeStopMonths: args.income_stop_months ?? 0,
        expenseChangePct: args.expense_change_pct ?? 0,
        rateChangePp: args.rate_change_pp ?? 0,
        oneOffExpense: args.one_off_expense ?? 0,
      };
      const { purchase, household } = run.inputs!;
      const [base, s] = runScenarioSet(purchase, household, run.analysis!, [params]);
      return {
        based_on: run.request.label,
        changed: s!.changedAssumptions,
        baseline: {
          monthly_surplus: base!.monthlySurplus,
          savings_after_12_months: base!.savingsAfterHorizon,
          assessment: LABEL_TEXT[base!.label],
        },
        scenario: {
          monthly_surplus: s!.monthlySurplus,
          emi: s!.emi,
          savings_after_12_months: s!.savingsAfterHorizon,
          lowest_savings: s!.lowestSavings,
          savings_run_out_month: s!.monthExhausted,
          emergency_months: s!.emergencyMonths,
          breaches: s!.breaches,
          assessment: LABEL_TEXT[s!.label],
        },
        note: "Hypothetical scenario, not a prediction.",
      };
    },
    summarize: (o) => {
      const r = o as { error?: string; scenario?: { assessment: string } };
      return r.error ?? `scenario: ${r.scenario?.assessment}`;
    },
  },
  compare_purchases: {
    description:
      "Compare 2-4 purchase prices of the same type against the saved profile (deterministic calculation; illustrative rate if none given).",
    schema: CompareArgs,
    run: async (args: z.infer<typeof CompareArgs>, session) => {
      const v = session.profile.values;
      if (
        v.monthlyIncome === null ||
        v.monthlyExpenses === null ||
        v.liquidSavings === null ||
        v.existingEmis === null
      )
        return { error: "The profile is missing income, expenses, savings or existing EMIs." };
      const rate = args.interest_rate ?? illustrativeRate(args.purchase_type);
      const tenure = args.tenure_months ?? DEFAULT_TENURE[args.purchase_type];
      const dp = args.down_payment_pct ?? 20;
      return {
        assumptions: {
          rate_percent: rate,
          rate_basis: args.interest_rate === undefined ? "illustrative" : "user",
          tenure_months: tenure,
          down_payment_pct: dp,
          upfront_costs: "not included",
        },
        options: args.prices.map((price) => {
          const a = analysePurchase(
            {
              purchasePrice: price,
              downPaymentPct: dp,
              upfrontCashCosts: 0,
              financedCosts: 0,
              annualInterestRate: rate,
              tenureMonths: tenure,
              monthlyOwnershipCost: 0,
            },
            {
              monthlyIncome: v.monthlyIncome!,
              monthlyExpenses: v.monthlyExpenses!,
              existingEmis: v.existingEmis!,
              otherMonthlyObligations: v.otherMonthlyObligations ?? 0,
              liquidSavings: v.liquidSavings!,
            },
          );
          return {
            price,
            emi: a.emi,
            total_interest: a.totalInterest,
            savings_after_purchase: a.postPurchaseSavings,
            monthly_surplus_after: a.after.cashFlow.monthlySurplus,
            debt_to_income_after: a.after.dti,
            emergency_months_after: a.after.emergencyMonths,
            assessment: LABEL_TEXT[a.label],
          };
        }),
      };
    },
    summarize: (o) =>
      (o as { error?: string }).error
        ? "error"
        : `${(o as { options: unknown[] }).options.length} options compared`,
  },
  plan_savings: {
    description:
      "Monthly saving needed to accumulate a target amount in N months (no investment returns assumed).",
    schema: SavingsArgs,
    run: async (args: z.infer<typeof SavingsArgs>) =>
      savingsPlanTool.run(
        {
          targetAmount: args.target_amount,
          currentSavings: 0,
          monthlySaving: null,
          months: args.months,
        },
        new AbortController().signal,
      ),
    summarize: (o) => savingsPlanTool.summarize(o as never),
  },
  calculate_emi: {
    description: "EMI, total repayment and total interest for a loan.",
    schema: EmiArgs,
    run: async (args: z.infer<typeof EmiArgs>) =>
      calculateEmiTool.run(
        {
          principal: args.principal,
          annualInterestRate: args.annual_interest_rate,
          tenureMonths: args.tenure_months,
        },
        new AbortController().signal,
      ),
    summarize: (o) => calculateEmiTool.summarize(o as never),
  },
  get_latest_analysis: {
    description:
      "The most recent completed affordability analysis: figures, failed checks, scenario results, findings and alternatives. Use to explain risks or follow up.",
    schema: Empty,
    run: async (_args, session) => {
      const run = latestCompleted(session);
      return run ? runDigest(run) : { error: "No completed analysis yet." };
    },
    summarize: (o) =>
      (o as { error?: string }).error ? "no analysis yet" : "latest analysis loaded",
  },
};

async function executeTool(
  name: string,
  raw: unknown,
  session: SessionState,
  listener: WorkflowListener,
  emit: Emit,
): Promise<{ ok: boolean; output: unknown }> {
  const impl = TOOLS[name];
  const call: CopilotToolCall = {
    id: newId("call"),
    tool: name,
    input: raw,
    summary: "",
    status: "ok",
  };
  if (!impl) {
    call.status = "error";
    call.summary = "unknown tool";
    emit({ type: "tool", call });
    return { ok: false, output: { error: `Unknown tool ${name}` } };
  }
  const parsed = impl.schema.safeParse(raw ?? {});
  if (!parsed.success) {
    call.status = "error";
    call.summary = `invalid input: ${parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")}`;
    emit({ type: "tool", call });
    return { ok: false, output: { error: call.summary } };
  }
  try {
    const output = await impl.run(parsed.data as never, session, listener, emit);
    call.summary = impl.summarize(output);
    emit({ type: "tool", call });
    return { ok: true, output };
  } catch (error) {
    call.status = "error";
    call.summary = error instanceof Error ? error.message : "tool failed";
    emit({ type: "tool", call });
    return { ok: false, output: { error: call.summary } };
  }
}

function collectNumbers(value: unknown, out: number[] = []): number[] {
  if (typeof value === "number" && Number.isFinite(value)) out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => collectNumbers(v, out));
  else if (value && typeof value === "object")
    Object.values(value).forEach((v) => collectNumbers(v, out));
  return out;
}

// ---------------------------------------------------------------- AI mode

const SYSTEM = `You are the FinPulse Copilot, an agentic financial assistant for individuals in India. Every person has a goal plan (house, car, education, travel…) that competes for the same income and savings; you help them decide "Can I afford this — alongside everything else I am planning — and what should I do next?".

How you work:
- Always use the tools for facts and figures. Never calculate or invent financial numbers yourself, never invent interest rates, lender offers or approvals. Quote figures exactly as tools return them, in Indian formatting (₹52,069, ₹60 lakh).
- For "can I afford X" questions call analyse_affordability (it runs the full multi-agent workflow, including the impact on the person's saved goals). For "am I on track", "my goals" or "my plan" use review_goal_plan. For rent-or-buy and prepay-or-invest questions use compare_rent_vs_buy and compare_prepay_vs_invest; ask for any figure they need that the person hasn't given. For what-ifs on an existing analysis use run_stress_scenario; for comparisons use compare_purchases; to explain risks use get_latest_analysis.
- If information is missing, say exactly what is needed rather than guessing.
- Distinguish hypothetical scenarios from predictions, and illustrative assumptions from sourced facts.
- You provide decision support, not regulated financial advice; never promise loan approval. You cannot submit applications, move money or contact lenders.
- Be concise: a short answer (under 160 words), plain sentences, at most one short list.
${UNTRUSTED_DATA_RULE}`;

async function aiTurn(
  session: SessionState,
  message: string,
  listener: WorkflowListener,
  emit: Emit,
) {
  const client = getClient();
  const tools: Anthropic.Tool[] = Object.entries(TOOLS).map(([name, t]) => ({
    name,
    description: t.description,
    input_schema: z.toJSONSchema(t.schema) as Anthropic.Tool.InputSchema,
  }));
  const history: Anthropic.MessageParam[] = session.copilot
    .slice(-10)
    .map((m) => ({ role: m.role, content: m.text }));
  const messages: Anthropic.MessageParam[] = [...history, { role: "user", content: message }];
  const numbers: number[] = [];
  for (let turn = 0; turn < 6; turn++) {
    const response = await client.messages.create({
      model: modelId(),
      max_tokens: 4000,
      output_config: { effort: effort() },
      system: SYSTEM,
      tools,
      messages,
    });
    if (response.stop_reason === "refusal") {
      return {
        text: "I can't help with that request. I can analyse purchases, run what-if scenarios and explain your results.",
        numbers,
      };
    }
    messages.push({ role: "assistant", content: response.content });
    const uses = response.content.filter((b): b is Anthropic.ToolUseBlock => b.type === "tool_use");
    if (response.stop_reason !== "tool_use" || uses.length === 0) {
      const text = response.content
        .filter((b): b is Anthropic.TextBlock => b.type === "text")
        .map((b) => b.text)
        .join("\n")
        .trim();
      return { text, numbers };
    }
    const results: Anthropic.ToolResultBlockParam[] = [];
    for (const use of uses) {
      const { ok, output } = await executeTool(use.name, use.input, session, listener, emit);
      collectNumbers(output, numbers);
      results.push({
        type: "tool_result",
        tool_use_id: use.id,
        content: JSON.stringify(output),
        is_error: !ok,
      });
    }
    messages.push({ role: "user", content: results });
  }
  return {
    text: "I reached the tool-call limit for one message. The results above are what completed.",
    numbers,
  };
}

// ---------------------------------------------------------------- rule-based mode

function scenarioFromText(text: string): z.infer<typeof ScenarioArgs> | null {
  const t = text.toLowerCase();
  const args: z.infer<typeof ScenarioArgs> = {};
  const pctNear = (re: RegExp) => {
    const m = t.match(re);
    return m ? Number(m[1]) : undefined;
  };
  const incomeDown =
    pctNear(
      /(?:income|salary|pay)[^%]*?(?:drops?|falls?|reduces?|decreases?|cut|down)[^\d]*(\d+(?:\.\d+)?)\s*%/,
    ) ??
    pctNear(
      /(\d+(?:\.\d+)?)\s*%\s*(?:drop|fall|cut|decrease|reduction)\s+in\s+(?:income|salary|pay)/,
    );
  if (incomeDown !== undefined) args.income_change_pct = -incomeDown;
  const stop = t.match(
    /(?:income\s+stops?|lose\s+(?:my\s+)?job|job\s+loss|no\s+income|unemployed)[^\d]*(\d+)\s*months?/,
  );
  if (stop) args.income_stop_months = Number(stop[1]);
  else if (/(income\s+stops?|lose\s+(my\s+)?job|job\s+loss)/.test(t)) args.income_stop_months = 6;
  const exp = pctNear(
    /(?:expenses?|costs?|spending)[^%]*?(?:rises?|increases?|goes up|up)[^\d]*(\d+(?:\.\d+)?)\s*%/,
  );
  if (exp !== undefined) args.expense_change_pct = exp;
  const rate = pctNear(
    /(?:rate|interest)[^\d]*?(?:rises?|increases?|goes up|up|hike)[^\d]*(\d+(?:\.\d+)?)\s*(?:%|pp|percentage)/,
  );
  if (rate !== undefined) args.rate_change_pp = rate;
  if (/(unexpected|emergency|medical|one-off|sudden)\s+(expense|bill|cost)/.test(t)) {
    const amt = findINRAmounts(text).find((a) => a.hasCurrency || a.hasUnit);
    if (amt) args.one_off_expense = amt.value;
  }
  return Object.keys(args).length ? args : null;
}

async function ruleTurn(
  session: SessionState,
  message: string,
  listener: WorkflowListener,
  emit: Emit,
): Promise<string> {
  const t = message.toLowerCase();

  // The saved goal plan: are my goals on track?
  if (/\b(my|our) (plan|goals)\b|on track|which goal/.test(t)) {
    const { output } = await executeTool("review_goal_plan", {}, session, listener, emit);
    const o = output as {
      error?: string;
      goals: {
        name: string;
        status: string;
        wanted_by: string;
        reached_in: string | null;
        months_late: number | null;
        monthly_needed: number;
      }[];
      spare_monthly_after_goals: number;
      check_in_trend: string;
      average_monthly_gap_vs_plan: number | null;
      goals_moved_if_trend_continues: {
        name: string;
        moves_to: string | null;
        extra_months: number | null;
      }[];
    };
    if (o.error) return `${o.error} Add them on My finances (or load the demo) and ask again.`;
    if (!o.goals.length)
      return "You haven't saved any goals yet. Add them on the Plan page — FinPulse then checks every purchase against all of them.";
    const lines = o.goals.map((g) =>
      g.status === "on_track"
        ? `• ${g.name}: on track for ${g.wanted_by} (${formatINR(g.monthly_needed)}/month).`
        : g.status === "delayed"
          ? `• ${g.name}: ${g.months_late} month(s) late — reached ${g.reached_in} instead of ${g.wanted_by}.`
          : `• ${g.name}: out of reach within the plan's horizon.`,
    );
    const pulseLine =
      o.check_in_trend === "behind" && o.average_monthly_gap_vs_plan !== null
        ? `\nYour recent check-ins show ${formatINR(Math.abs(o.average_monthly_gap_vs_plan))} a month less saved than planned${o.goals_moved_if_trend_continues.length ? `; if that continues, ${o.goals_moved_if_trend_continues.map((g) => `${g.name} moves to ${g.moves_to ?? "out of reach"}`).join(", ")}` : ", which your spare money still absorbs"}.`
        : "";
    return `${lines.join("\n")}\nAfter funding these you have ${formatINR(o.spare_monthly_after_goals)} spare each month.${pulseLine}`;
  }

  // Rent or buy a home.
  if (/rent (or|vs\.?|versus) buy|buy (or|vs\.?|versus) rent|renting|rent instead/.test(t)) {
    const nums = findINRAmounts(message)
      .map((a) => a.value)
      .sort((a, b) => b - a);
    if (nums.length < 2)
      return 'Tell me the home\'s price and the rent for a similar home, e.g. "Rent or buy: ₹75 lakh flat, rent ₹25,000". Or open Decide → Rent vs buy.';
    const { output } = await executeTool(
      "compare_rent_vs_buy",
      { price: nums[0], monthly_rent: nums[nums.length - 1] },
      session,
      listener,
      emit,
    );
    const o = output as {
      error?: string;
      assumptions: { years: number; appreciationPct: number; investReturnPct: number };
      winner: string;
      difference: number;
      cash_needed_to_buy: number;
      emi: number;
      appreciation_needed_to_break_even_pct: number | null;
    };
    if (o.error) return o.error;
    const who =
      o.winner === "even"
        ? "Buying and renting come out about level"
        : `${o.winner === "buy" ? "Buying" : "Renting and investing the difference"} comes out ahead by ${formatINR(Math.abs(o.difference))}`;
    return `${who} after ${o.assumptions.years} years, assuming ${o.assumptions.appreciationPct}% yearly price growth and ${o.assumptions.investReturnPct}% investment returns (assumptions, not forecasts). Buying needs ${formatINR(o.cash_needed_to_buy)} upfront and an EMI of ${formatINR(o.emi)}.${o.appreciation_needed_to_break_even_pct !== null ? ` Buying wins only if prices grow faster than ${o.appreciation_needed_to_break_even_pct}% a year.` : ""}`;
  }

  // Prepay a loan or invest.
  if (/prepay|pre-pay|part.?pay|foreclose/.test(t)) {
    const nums = findINRAmounts(message)
      .filter((a) => a.hasCurrency || a.hasUnit)
      .map((a) => a.value)
      .sort((a, b) => b - a);
    const rate = /(\d+(?:\.\d+)?)\s*%/.exec(message);
    const years = /(\d+(?:\.\d+)?)\s*(?:years?|yrs?)/.exec(t);
    if (nums.length < 2 || !rate || !years)
      return 'I need four things: the loan outstanding, its interest rate, the years left and the lump sum — e.g. "Prepay or invest: ₹40 lakh loan at 8.5% with 15 years left, ₹5 lakh bonus". Or open Decide → Prepay vs invest.';
    const { output } = await executeTool(
      "compare_prepay_vs_invest",
      {
        outstanding: nums[0],
        lump_sum: nums[nums.length - 1],
        loan_rate_pct: Number(rate[1]),
        remaining_months: Math.round(Number(years[1]) * 12),
      },
      session,
      listener,
      emit,
    );
    const o = output as {
      error?: string;
      assumptions: { investReturnPct: number; taxOnGainsPct: number };
      interest_saved_by_prepaying: number;
      months_saved: number;
      winner: string;
      difference: number;
      breakeven_return_pct: number | null;
    };
    if (o.error) return o.error;
    return `Prepaying saves ${formatINR(o.interest_saved_by_prepaying)} of interest and ends the loan ${o.months_saved} months early. At an assumed ${o.assumptions.investReturnPct}% return (${o.assumptions.taxOnGainsPct}% tax on gains), ${o.winner === "even" ? "the two come out about level" : `${o.winner === "prepay" ? "prepaying" : "investing"} is ahead by ${formatINR(Math.abs(o.difference))} on the loan's original end date`}.${o.breakeven_return_pct !== null ? ` Investing wins only if you reliably earn more than ${o.breakeven_return_pct}% a year.` : ""}`;
  }

  if (/emergency fund|rainy day|safety net/.test(t)) {
    const { output } = await executeTool("plan_emergency_fund", {}, session, listener, emit);
    const o = output as {
      error?: string;
      target_months: number;
      target_amount: number;
      current_cover_months: number | null;
      gap: number;
      monthly_saving_needed: number;
      monthly_surplus_now: number;
    };
    if (o.error)
      return `${o.error} Add them on My finances (or load the demo profile) and ask again.`;
    if (!o.gap)
      return `You already have ${o.current_cover_months?.toFixed(1)} months of essential spending saved — at or above your ${o.target_months}-month target of ${formatINR(o.target_amount)}. Keep it in a liquid account separate from goal savings.`;
    return `A ${o.target_months}-month emergency fund for you is ${formatINR(o.target_amount)}. You have ${o.current_cover_months?.toFixed(1)} months covered, so the gap is ${formatINR(o.gap)}. Saving ${formatINR(o.monthly_saving_needed)} a month closes it in 12 months — that is ${Math.round((o.monthly_saving_needed / Math.max(1, o.monthly_surplus_now)) * 100)}% of your current monthly surplus.`;
  }

  // "Stress-test my finances": today's household, no purchase involved.
  if (/stress.?test (my|our) finances|how safe are my finances/.test(t)) {
    const { output } = await executeTool("stress_test_profile", {}, session, listener, emit);
    const o = output as {
      error?: string;
      monthly_surplus_now: number;
      months_savings_last_with_no_income: number | null;
      surplus_if_income_falls_20pct: number;
      surplus_if_expenses_rise_15pct: number;
    };
    if (o.error)
      return `${o.error} Add them on My finances (or load the demo profile) and ask again.`;
    return `Stress test of your finances today (hypothetical, not predictions):\n• If your income stopped, savings would cover ${o.months_savings_last_with_no_income?.toFixed(1) ?? "—"} months of essential spending.\n• If income fell 20%, you'd have ${formatINR(o.surplus_if_income_falls_20pct)} left each month (now ${formatINR(o.monthly_surplus_now)}).\n• If living expenses rose 15%, you'd have ${formatINR(o.surplus_if_expenses_rise_15pct)} left each month.\nTo stress-test a specific purchase, run "Can I afford this?" and open its What-if tab.`;
  }
  const amounts = findINRAmounts(message).filter(
    (a) => a.hasCurrency || a.hasUnit || a.value >= 10_000,
  );
  const type = detectPurchaseType(message);

  if (/compare|versus|\bvs\.?\b/.test(t) && amounts.length >= 2) {
    const { ok, output } = await executeTool(
      "compare_purchases",
      { purchase_type: type ?? "custom", prices: amounts.slice(0, 4).map((a) => a.value) },
      session,
      listener,
      emit,
    );
    const o = output as {
      error?: string;
      assumptions?: { rate_percent: number; tenure_months: number; down_payment_pct: number };
      options?: {
        price: number;
        emi: number;
        savings_after_purchase: number;
        monthly_surplus_after: number;
        assessment: string;
      }[];
    };
    if (!ok || o.error) return o.error ?? "The comparison failed.";
    const lines = o.options!.map(
      (x) =>
        `• ${inrWords(x.price)}: EMI ${formatINR(x.emi)}, ${formatINR(x.monthly_surplus_after)} left monthly, ${formatINR(x.savings_after_purchase)} savings after — ${x.assessment.toLowerCase()}.`,
    );
    return `Compared at ${o.assumptions!.down_payment_pct}% down, ${o.assumptions!.rate_percent}% p.a. (illustrative unless you gave a rate) over ${o.assumptions!.tenure_months / 12} years; upfront costs not included:\n${lines.join("\n")}`;
  }

  const scenario = scenarioFromText(message);
  if (scenario && /what if|if my|if i|suppose|what happens/.test(t)) {
    const { output } = await executeTool(
      "run_stress_scenario",
      { name: "Your what-if", ...scenario },
      session,
      listener,
      emit,
    );
    const o = output as {
      error?: string;
      based_on?: string;
      changed?: string[];
      baseline?: { monthly_surplus: number };
      scenario?: {
        monthly_surplus: number;
        savings_after_12_months: number;
        lowest_savings: number;
        savings_run_out_month: number | null;
        assessment: string;
        breaches: string[];
      };
    };
    if (o.error) return `${o.error} Try "Can I afford a ₹75 lakh house?"`;
    const s = o.scenario!;
    const flow = scenario.income_stop_months
      ? `with no income for ${scenario.income_stop_months} months your savings would fall to a low of ${formatINR(s.lowest_savings)}.`
      : `monthly surplus goes from ${formatINR(o.baseline!.monthly_surplus)} to ${formatINR(s.monthly_surplus)}.`;
    return `Hypothetical scenario on your ${o.based_on} analysis (${o.changed!.join("; ")}): ${flow} ${s.savings_run_out_month !== null ? `Your savings would run out in month ${s.savings_run_out_month}.` : `Savings after 12 months: ${formatINR(s.savings_after_12_months)}.`} Assessment: ${s.assessment.toLowerCase()}.${s.breaches.length ? ` Rules breached: ${s.breaches.join(", ").toLowerCase()}.` : ""} This is a what-if, not a prediction.`;
  }

  if (/afford|should i buy|can i buy|buy a|purchase/.test(t) && amounts.length >= 1) {
    const price = amounts[0]!.value;
    const { output } = await executeTool(
      "analyse_affordability",
      { purchase_type: type ?? "custom", price },
      session,
      listener,
      emit,
    );
    const o = output as ReturnType<typeof runDigest> & {
      status: string;
      missing?: { label: string; question: string }[];
      error?: string;
    };
    if (o.status === "needs_input")
      return `I need a few details first:\n${o.missing!.map((m) => `• ${m.question}`).join("\n")}\nAdd them on the Financial Profile page (or click "Try Demo"), then ask again.`;
    if (o.status !== "completed") return `The analysis could not finish: ${o.error}`;
    return `${o.assessment}. For the ${o.purchase}, the loan would be ${formatINR(o.loan_amount)} with an EMI of ${formatINR(o.emi)} at ${o.rate_percent}% (${o.rate_basis === "illustrative" || o.rate_basis === "demo" ? "illustrative rate" : o.rate_basis + " rate"}). You'd keep ${formatINR(o.savings_after_purchase)} in savings (${o.emergency_months_after?.toFixed(1)} months of cover) and ${formatINR(o.monthly_surplus_after)} a month. ${o.scenarios?.filter((s) => s.assessment === LABEL_TEXT.high_strain).length ?? 0} of ${o.scenarios?.length ?? 0} stress scenarios breach a safety rule. Open the full results for evidence, alternatives and the next-step checklist.`;
  }

  if (/save|saving/.test(t)) {
    const run = latestCompleted(session);
    const alt = run?.recommendation?.alternatives.find((a) => a.id === "save_first");
    if (alt) {
      await executeTool("get_latest_analysis", {}, session, listener, emit);
      return `${alt.title}. ${alt.description} (${alt.figures.map((f) => `${f.label}: ${f.unit === "INR" ? formatINR(f.value) : f.value}`).join("; ")}).`;
    }
    if (run)
      return `Your latest analysis (${run.request.label}) is already comfortable under its assumptions, so no extra saving is required by FinPulse's rules — keeping 6 months of expenses aside is still wise.`;
    return 'Run an analysis first (e.g. "Can I afford a ₹75 lakh house?") and I\'ll work out how much to save before buying.';
  }

  if (/why|risk|explain|concern/.test(t)) {
    const { output } = await executeTool("get_latest_analysis", {}, session, listener, emit);
    const o = output as ReturnType<typeof runDigest> & { error?: string };
    if (o.error)
      return 'There\'s no analysis to explain yet. Ask "Can I afford a ₹75 lakh house?" first.';
    const issues = [...o.failed_or_warning_checks, ...o.key_findings].slice(0, 5);
    return `${o.purchase}: ${o.assessment.toLowerCase()}. The main concerns:\n${issues.map((i) => `• ${i}`).join("\n")}`;
  }

  return 'I can run tools for: "Am I on track for my goals?", "Rent or buy: ₹75 lakh flat, rent ₹25,000", "Prepay or invest: ₹40 lakh loan at 8.5% with 15 years left, ₹5 lakh bonus", "Can I afford a ₹75 lakh house?", "What if my income drops by 20%?", "Compare a ₹15 lakh car with a ₹20 lakh car", "How much should I save before buying?" or "Explain why this option is risky".';
}

// ---------------------------------------------------------------- entry point

export async function copilotTurn(
  session: SessionState,
  message: string,
  emit: Emit,
  opts: { runId?: string } = {},
): Promise<void> {
  // Follow-up questions about a specific analysis keep it in focus for every tool.
  if (opts.runId && session.runs.some((r) => r.id === opts.runId)) session.focusRunId = opts.runId;
  const listener: WorkflowListener = (event) => emit({ type: "event", event });
  const status = aiStatus();
  audit(session, "copilot_message", "user", `Copilot: ${message.slice(0, 120)}`);
  let text: string;
  let mode: "ai" | "rule_based" = "rule_based";
  let notice: string | undefined;
  let unverified: string[] = [];
  if (status.enabled) {
    try {
      const result = await aiTurn(session, message, listener, emit);
      text = result.text;
      mode = "ai";
      unverified = verifyFigures(
        text,
        result.numbers,
        result.numbers.flatMap((n) => (Math.abs(n) <= 1.5 ? [n * 100, n] : [n])),
      );
    } catch (error) {
      notice = `${describeAiError(error)} — answered with the rule-based fallback instead.`;
      audit(session, "service_unavailable", "copilot", notice);
      text = await ruleTurn(session, message, listener, emit);
    }
  } else {
    notice =
      "AI is not configured (no ANTHROPIC_API_KEY). Answered by FinPulse's rule-based router using the same tools.";
    text = await ruleTurn(session, message, listener, emit);
  }
  session.copilot.push({ role: "user", text: message }, { role: "assistant", text });
  if (session.copilot.length > 40) session.copilot.splice(0, session.copilot.length - 40);
  emit({ type: "message", text, mode, unverifiedFigures: unverified, notice });
}
