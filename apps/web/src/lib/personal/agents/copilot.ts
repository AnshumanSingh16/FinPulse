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
import { findINRAmounts, inrWords } from "../finance/parse-inr";
import { runScenarioSet, type ScenarioParams } from "../finance/scenarios";
import { detectPurchaseType } from "../goal";
import { PURCHASE_TYPES, type PurchaseRequest } from "../schemas";
import { audit, newId, type SessionState } from "../store";
import { aiStatus, describeAiError, effort, getClient, modelId, UNTRUSTED_DATA_RULE } from "./llm";
import { runAffordabilityWorkflow, type WorkflowListener } from "./orchestrator";
import { illustrativeRate, DEFAULT_TENURE } from "./research";
import { verifyFigures } from "./synthesis";
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

function latestCompleted(session: SessionState): WorkflowRun | undefined {
  return session.runs.find((r) => r.status === "completed" && r.inputs && r.analysis);
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

const SYSTEM = `You are the FinPulse Copilot, an agentic financial assistant for individuals in India. You help people decide "Can I afford this, and what should I do next?".

How you work:
- Always use the tools for facts and figures. Never calculate or invent financial numbers yourself, never invent interest rates, lender offers or approvals. Quote figures exactly as tools return them, in Indian formatting (₹52,069, ₹60 lakh).
- For "can I afford X" questions call analyse_affordability (it runs the full multi-agent workflow). For what-ifs on an existing analysis use run_stress_scenario; for comparisons use compare_purchases; to explain risks use get_latest_analysis.
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

  return 'I can run tools for: "Can I afford a ₹75 lakh house?", "What if my income drops by 20%?", "Compare a ₹15 lakh car with a ₹20 lakh car", "How much should I save before buying?" or "Explain why this option is risky".';
}

// ---------------------------------------------------------------- entry point

export async function copilotTurn(
  session: SessionState,
  message: string,
  emit: Emit,
): Promise<void> {
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
