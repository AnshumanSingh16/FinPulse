/**
 * Workflow state shared by the orchestrator, the agents and the UI. Everything an agent produces
 * is structured data; free text is limited to short summaries.
 */
import type { AffordabilityLabel, PurchaseAnalysis, RuleCheck } from "../finance/affordability";
import type { ScenarioResult } from "../finance/scenarios";
import type { PlanOdds, RiskDriver } from "../finance/montecarlo";
import type { ChangeView, SearchRound } from "../finance/optimize";
import type { PlanImpact } from "../finance/plan";
import type { PlanGoalValues, ProfileValues, PurchaseRequest } from "../schemas";

export type AgentName =
  | "orchestrator"
  | "planner"
  | "research"
  | "analysis"
  | "risk"
  | "verification"
  | "action"
  | "copilot"
  | "strategist";

export const AGENT_LABELS: Record<AgentName, string> = {
  orchestrator: "Orchestrator",
  planner: "Financial Planner",
  research: "Financial Research",
  analysis: "Financial Analysis",
  risk: "Risk (stress testing)",
  verification: "Verification",
  action: "Financial Action",
  copilot: "Copilot",
  strategist: "Strategist",
};

export type StepStatus = "pending" | "running" | "done" | "failed" | "skipped" | "needs_input";

export type PlanStep = {
  id: string;
  agent: AgentName;
  title: string;
  why: string;
  status: StepStatus;
  summary?: string;
  toolCallIds: string[];
};

export type ToolCallRecord = {
  id: string;
  tool: string;
  agent: AgentName;
  stepId?: string;
  input: unknown;
  output?: unknown;
  outputSummary?: string;
  status: "ok" | "error" | "rejected";
  error?: string;
  startedAt: string;
  durationMs: number;
};

export type AgentEventKind =
  | "run_started"
  | "plan_created"
  | "step_started"
  | "step_completed"
  | "step_failed"
  | "step_skipped"
  | "tool_call"
  | "tool_result"
  | "tool_error"
  | "finding"
  | "needs_input"
  | "llm"
  | "run_completed"
  | "run_failed";

export type AgentEvent = {
  id: string;
  at: string;
  agent: AgentName;
  kind: AgentEventKind;
  message: string;
  stepId?: string;
  toolCallId?: string;
  level?: "info" | "warning" | "error";
  /** On plan_created: the plan's steps, so the UI can show the plan before it runs. */
  plan?: { id: string; agent: AgentName; title: string; why: string }[];
};

export type Source = {
  id: string;
  title: string;
  url: string | null;
  retrievedAt: string;
  kind: "web" | "illustrative" | "user" | "document" | "regulatory_guideline";
  supports: string;
};

export type FinancingOption = {
  id: string;
  name: string;
  annualRateMin: number;
  annualRateMax: number;
  rateUsed: number;
  tenureMonths: number;
  feesNote: string | null;
  basis: "illustrative" | "sourced";
  sourceIds: string[];
  emi?: number;
  totalInterest?: number;
};

export type ResearchResult = {
  provider: string;
  live: boolean;
  retrievedAt: string;
  options: FinancingOption[];
  sources: Source[];
  notes: string[];
  warnings: string[];
};

export type Assumption = {
  id: string;
  field: string;
  value: string;
  basis: "user" | "demo" | "document" | "illustrative" | "research" | "default";
  note: string;
};

export type Finding = {
  id: string;
  agent: "verification" | "risk" | "analysis";
  severity: "info" | "warning" | "critical";
  category: "missing" | "inconsistent" | "assumption" | "risk" | "document" | "plan";
  message: string;
  field?: string;
  suggestion?: string;
};

export type Alternative = {
  id: string;
  title: string;
  description: string;
  figures: { label: string; value: number; unit: "INR" | "months" | "percent" }[];
};

export type Recommendation = {
  label: AffordabilityLabel;
  headline: string;
  summary: string[];
  narrative: { text: string; mode: "ai" | "template"; unverifiedFigures: string[] } | null;
  alternatives: Alternative[];
};

export type MissingInput = { field: string; label: string; question: string };

export type ResolvedInputs = {
  purchase: {
    purchasePrice: number;
    downPaymentPct: number;
    upfrontCashCosts: number;
    financedCosts: number;
    annualInterestRate: number;
    tenureMonths: number;
    monthlyOwnershipCost: number;
  };
  household: {
    monthlyIncome: number;
    monthlyExpenses: number;
    existingEmis: number;
    otherMonthlyObligations: number;
    liquidSavings: number;
  };
};

export type RunStatus = "running" | "completed" | "needs_input" | "failed";

export type WorkflowRun = {
  id: string;
  goal: string;
  createdAt: string;
  finishedAt: string | null;
  status: RunStatus;
  mode: { ai: boolean; research: "live" | "illustrative" };
  request: PurchaseRequest;
  profileSnapshot: ProfileValues;
  plan: PlanStep[];
  events: AgentEvent[];
  toolCalls: ToolCallRecord[];
  missing: MissingInput[];
  assumptions: Assumption[];
  inputs: ResolvedInputs | null;
  research: ResearchResult | null;
  analysis: PurchaseAnalysis | null;
  scenarios: ScenarioResult[] | null;
  /** What this purchase does to the person's other saved goals (null when none are saved). */
  planImpact: PlanImpact | null;
  /** The same comparison across possible futures, and the Strategist's best way to fit it in. */
  planOdds: {
    before: OddsSummary;
    after: OddsSummary;
    bestFit: { changes: ChangeView[]; after: OddsSummary; evaluations: number } | null;
  } | null;
  findings: Finding[];
  checks: RuleCheck[];
  recommendation: Recommendation | null;
  actionPlanId: string | null;
  error: string | null;
  limits: { maxToolCalls: number; maxDurationMs: number; maxLlmCalls: number; llmCalls: number };
};

/** A summary of Monte Carlo odds small enough to keep on runs and send to the browser. */
export type OddsSummary = Pick<PlanOdds, "paths" | "allOnTime" | "neverShort" | "score"> & {
  goals: Pick<PlanOdds["goals"][number], "id" | "name" | "onTime" | "withinYear" | "medianDelay">[];
};

/**
 * One run of the Strategist agent: measure the plan's odds, find what hurts most, search for
 * changes that improve it, check the proposal on fresh futures, and hand it over for approval.
 */
export type StrategyRun = {
  id: string;
  createdAt: string;
  finishedAt: string | null;
  status: "running" | "completed" | "failed";
  /** Fingerprint of the plan it was run on: a proposal can't be applied to a plan that changed. */
  planKey: string;
  plan: PlanStep[];
  events: AgentEvent[];
  toolCalls: ToolCallRecord[];
  limits: WorkflowRun["limits"];
  drivers: RiskDriver[];
  rounds: SearchRound[];
  proposal: {
    changes: ChangeView[];
    goals: PlanGoalValues[];
    spendingCut: number;
    before: OddsSummary;
    after: OddsSummary;
    evaluations: number;
  } | null;
  decision: "pending" | "applied" | "dismissed" | "none";
  error: string | null;
};
