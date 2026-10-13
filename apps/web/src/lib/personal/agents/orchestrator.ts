/**
 * The orchestrator: runs the affordability workflow end to end.
 *
 *   goal → check inputs (ask if missing) → plan → research → calculate → stress-test → verify
 *        → synthesise → prepare next steps → request approval → audit
 *
 * It is a structured orchestrator: the plan is built from the request and the profile, and each
 * step invokes its agent's tools through RunContext, which validates and records every call. The
 * LLM, when configured, is used where judgement helps (live research, explanation, the copilot) and
 * never produces a financial figure. Every step's outcome — success, failure, skipped — is recorded
 * and streamed, so the UI shows exactly what ran.
 */
import "server-only";

import { formatINR } from "@/lib/format";

import { currentMonth } from "../finance/plan";
import { effectiveAssumptions, goalFromPurchase, summarizeOdds } from "../plan-model";

import type { ProfileValues, PurchaseRequest } from "../schemas";
import {
  audit,
  newId,
  saveRun,
  transitionActionPlan,
  type ActionPlan,
  type SessionState,
} from "../store";
import { aiStatus, liveResearchEnabled } from "./llm";
import { planImpactTool, searchPlanTool, simulatePlanTool } from "./plan-tools";
import { buildPlan } from "./planner";
import { LimitExceededError, RunContext } from "./runtime";
import { aiNarrative, buildAlternatives, buildRecommendation, buildSummary } from "./synthesis";
import {
  actionPlanTool,
  analysePurchaseTool,
  interpretGoalTool,
  compareFinancingTool,
  illustrativeResearchTool,
  optionsForComparison,
  researchTool,
  resolveInputsTool,
  scenariosTool,
  verifyTool,
} from "./tools";
import type { AgentEvent, Finding, PlanStep, ResearchResult, WorkflowRun } from "./types";
import { riskFindings, type DocumentFact } from "./verification";

export type WorkflowListener = (event: AgentEvent) => void;

function newRun(
  goal: string,
  request: PurchaseRequest,
  profile: ProfileValues,
  research: boolean,
  goals: number,
): WorkflowRun {
  const ai = aiStatus().enabled;
  const live = liveResearchEnabled();
  return {
    id: newId("run"),
    goal,
    createdAt: new Date().toISOString(),
    finishedAt: null,
    status: "running",
    mode: { ai, research: live ? "live" : "illustrative" },
    request,
    profileSnapshot: { ...profile },
    plan: buildPlan({ research, liveResearch: live, goals }),
    events: [],
    toolCalls: [],
    missing: [],
    assumptions: [],
    inputs: null,
    research: null,
    analysis: null,
    scenarios: null,
    planImpact: null,
    planOdds: null,
    findings: [],
    checks: [],
    recommendation: null,
    actionPlanId: null,
    error: null,
    limits: { maxToolCalls: 40, maxDurationMs: 120_000, maxLlmCalls: 3, llmCalls: 0 },
  };
}

function documentFacts(session: SessionState): DocumentFact[] {
  return session.documents
    .filter((d) => d.review !== "dismissed")
    .flatMap((d) =>
      d.extraction.fields
        .filter((f) => f.profileField && typeof f.value === "number")
        .map((f) => ({
          documentName: d.name,
          profileField: f.profileField!,
          label: f.label,
          value: f.value as number,
        })),
    );
}

export async function runAffordabilityWorkflow(
  session: SessionState,
  goal: string,
  request: PurchaseRequest,
  listener: WorkflowListener = () => {},
): Promise<WorkflowRun> {
  const needsResearch = request.researchFinancing || request.interestRate === null;
  const run = newRun(goal, request, session.profile.values, needsResearch, session.goals.length);
  saveRun(session, run);
  const ctx = new RunContext(run, listener);
  const step = (id: string) => run.plan.find((s) => s.id === id)!;
  const start = (s: PlanStep) => {
    s.status = "running";
    ctx.emit(s.agent, "step_started", s.title, { stepId: s.id });
  };
  const finish = (s: PlanStep, summary: string) => {
    s.status = "done";
    s.summary = summary;
    ctx.emit(s.agent, "step_completed", summary, { stepId: s.id });
  };

  audit(session, "goal_submitted", "user", `Goal: ${goal}`, run.id);
  ctx.emit("orchestrator", "run_started", `Goal received: "${goal}"`);
  ctx.emit(
    "orchestrator",
    "plan_created",
    `Task plan ready: ${run.plan.length} steps across ${new Set(run.plan.map((s) => s.agent)).size} agents. AI ${run.mode.ai ? "enabled" : "not configured (deterministic mode)"}; research ${run.mode.research === "live" ? "live" : "illustrative"}.`,
    { plan: run.plan.map(({ id, agent, title, why }) => ({ id, agent, title, why })) },
  );
  audit(session, "plan_created", "agent:planner", `Created a ${run.plan.length}-step plan`, run.id);

  let current: PlanStep | null = null;
  try {
    // 0. Understand the goal -----------------------------------------------------------------
    current = step("understand");
    start(current);
    const goalInfo = await ctx.callTool(interpretGoalTool, { goal }, current.id);
    if (
      goalInfo.price !== null &&
      Math.abs(goalInfo.price - request.price) > request.price * 0.01
    ) {
      ctx.emit(
        "planner",
        "finding",
        `Your goal mentions ${formatINR(goalInfo.price)}, but the price entered is ${formatINR(request.price)}. Using the entered price.`,
        { stepId: current.id, level: "warning" },
      );
    }
    finish(current, `Goal: ${request.label} (${request.type}).`);

    // 1. Collect & check inputs ------------------------------------------------------------
    current = step("collect");
    start(current);
    const resolved = await ctx.callTool(
      resolveInputsTool,
      {
        profile: session.profile.values,
        sources: session.profile.sources,
        isDemo: session.profile.isDemo,
        request,
      },
      current.id,
    );
    run.assumptions = resolved.assumptions;
    if (!resolved.inputs) {
      run.missing = resolved.missing;
      current.status = "needs_input";
      current.summary = `Missing: ${resolved.missing.map((m) => m.label).join(", ")}`;
      ctx.emit(
        "planner",
        "needs_input",
        `I need ${resolved.missing.length} more detail(s) before a reliable assessment: ${resolved.missing.map((m) => m.label).join(", ")}.`,
        { stepId: current.id, level: "warning" },
      );
      for (const s of run.plan) if (s.status === "pending") s.status = "skipped";
      run.status = "needs_input";
      run.finishedAt = new Date().toISOString();
      audit(
        session,
        "missing_information",
        "agent:planner",
        `Asked for: ${resolved.missing.map((m) => m.label).join(", ")}`,
        run.id,
      );
      return run;
    }
    const inputs = resolved.inputs;
    finish(
      current,
      `All required inputs present. ${resolved.assumptions.filter((a) => a.basis === "illustrative" || a.basis === "default").length} gap(s) filled with disclosed assumptions.`,
    );

    // 2. Research ------------------------------------------------------------------------------
    if (needsResearch) {
      current = step("research");
      start(current);
      const query = {
        purchaseType: request.type,
        loanAmount: Math.round(
          inputs.purchase.purchasePrice * (1 - inputs.purchase.downPaymentPct / 100) +
            inputs.purchase.financedCosts,
        ),
        tenureMonths: inputs.purchase.tenureMonths,
      };
      let research: ResearchResult;
      let note = "";
      if (run.mode.research === "live" && ctx.useLlmCall()) {
        try {
          research = await ctx.callTool(researchTool, query, current.id);
        } catch (error) {
          if (error instanceof LimitExceededError) throw error;
          note = " Live research failed, so illustrative ranges were used.";
          audit(
            session,
            "service_unavailable",
            "agent:research",
            "Live research failed; fell back to illustrative assumptions",
            run.id,
          );
          research = await ctx.callTool(illustrativeResearchTool, query, current.id);
        }
      } else {
        research = await ctx.callTool(illustrativeResearchTool, query, current.id);
      }
      const compared = await ctx.callTool(
        compareFinancingTool,
        { loanAmount: query.loanAmount, options: optionsForComparison(research) },
        current.id,
      );
      for (const o of research.options) {
        const c = compared.find((x) => x.id === o.id);
        if (c) Object.assign(o, { emi: c.emi, totalInterest: c.totalInterest });
      }
      run.research = research;
      if (resolved.needsRate) {
        const rates = research.options
          .filter((o) => o.tenureMonths === inputs.purchase.tenureMonths)
          .map((o) => o.rateUsed);
        const pool = rates.length ? rates : research.options.map((o) => o.rateUsed);
        const sorted = [...pool].sort((a, b) => a - b);
        const rate = research.live
          ? sorted[Math.floor(sorted.length / 2)]!
          : (research.options[0]!.annualRateMin + research.options[0]!.annualRateMax) / 2;
        inputs.purchase.annualInterestRate = Math.round(rate * 100) / 100;
        run.assumptions.push({
          id: "in_rate",
          field: "Interest rate",
          value: `${inputs.purchase.annualInterestRate}% p.a.`,
          basis: research.live ? "research" : "illustrative",
          note: research.live
            ? "Median of the lowest published rates found by live research. Your offered rate may be higher."
            : "Midpoint of an illustrative range, not a current lender quote.",
        });
      }
      for (const w of research.warnings)
        ctx.emit("research", "finding", w, { stepId: current.id, level: "warning" });
      audit(
        session,
        "research_completed",
        "agent:research",
        `${research.live ? "Live" : "Illustrative"} financing research: ${research.options.length} option(s), ${research.sources.length} source(s)`,
        run.id,
      );
      finish(
        current,
        `${research.options.length} financing option(s) ${research.live ? `from ${research.sources.length} retrieved source(s)` : "from labelled illustrative ranges"}.${note}`,
      );
    }
    run.inputs = inputs;

    // 3. Analysis ------------------------------------------------------------------------------
    current = step("analyse");
    start(current);
    const analysis = await ctx.callTool(analysePurchaseTool, inputs, current.id);
    run.analysis = analysis;
    run.checks = analysis.checks;
    audit(
      session,
      "calculation_completed",
      "agent:analysis",
      `EMI ${formatINR(analysis.emi)} on ${formatINR(analysis.loanAmount)}; post-purchase savings ${formatINR(analysis.postPurchaseSavings)}`,
      run.id,
    );
    finish(
      current,
      `EMI ${formatINR(analysis.emi)}/month; ${formatINR(analysis.after.cashFlow.monthlySurplus)} left monthly; ${analysis.after.emergencyMonths?.toFixed(1) ?? "—"} months of emergency cover.`,
    );

    // 4. Stress test ---------------------------------------------------------------------------
    current = step("stress");
    start(current);
    const scenarios = await ctx.callTool(scenariosTool, { inputs }, current.id);
    run.scenarios = scenarios;
    const risks = riskFindings(scenarios);
    for (const f of risks)
      ctx.emit("risk", "finding", f.message, {
        stepId: current.id,
        level: f.severity === "warning" ? "warning" : "info",
      });
    audit(
      session,
      "scenario_executed",
      "agent:risk",
      `${scenarios.length - 1} stress scenarios; ${risks.filter((r) => r.severity === "warning").length} breach a rule`,
      run.id,
    );
    finish(
      current,
      `${scenarios.length - 1} scenarios run; ${scenarios.filter((s) => !s.isBaseline && s.label === "high_strain").length} breach a safety rule.`,
    );

    // 5. Plan impact: what does this purchase do to everything else the person is saving for? --
    const planFindings: Finding[] = [];
    if (session.goals.length) {
      current = step("plan");
      start(current);
      const month = currentMonth();
      const planInput = {
        household: { ...inputs.household, investments: session.profile.values.investments ?? 0 },
        goals: session.goals,
        assumptions: effectiveAssumptions(session.profile.values, session.planAssumptions),
        startMonth: month,
      };
      const newGoal = goalFromPurchase(request, inputs.purchase, month);
      const { impact } = await ctx.callTool(planImpactTool, { ...planInput, newGoal }, current.id);
      run.planImpact = impact;
      for (const a of impact.affected) {
        const message =
          a.extraDelayMonths === null
            ? `Buying this now puts "${a.name}" out of reach within the plan's horizon.`
            : a.extraDelayMonths > 0
              ? `Buying this now pushes "${a.name}" back by ${a.extraDelayMonths} month(s), to ${a.after.achievedMonth}.`
              : `"${a.name}" moves to ${a.after.achievedMonth}.`;
        planFindings.push({
          id: `plan_${a.id}`,
          agent: "analysis",
          severity: a.extraDelayMonths === null ? "critical" : "warning",
          category: "plan",
          message,
          suggestion: "Open your plan to change priorities or dates.",
        });
        ctx.emit("analysis", "finding", message, { stepId: current.id, level: "warning" });
      }
      audit(
        session,
        "plan_impact",
        "agent:analysis",
        impact.affected.length
          ? `Impact on your plan: ${impact.affected.length} goal(s) move`
          : `Fits alongside all ${session.goals.length} saved goal(s)`,
        run.id,
      );
      // The same question across possible futures, not just the expected one.
      const variability = session.profile.values.incomeVariability;
      const withPurchase = { ...planInput, goals: [...planInput.goals, newGoal] };
      const before = await ctx.callTool(
        simulatePlanTool,
        { ...planInput, paths: 400, incomeVariability: variability },
        current.id,
      );
      const after = await ctx.callTool(
        simulatePlanTool,
        { ...withPurchase, paths: 400, incomeVariability: variability },
        current.id,
      );
      run.planOdds = { before: summarizeOdds(before), after: summarizeOdds(after), bestFit: null };
      const pctOf = (x: number) => `${Math.round(x * 100)}%`;
      if (before.allOnTime - after.allOnTime >= 0.1) {
        const message = `The chance every goal lands on time drops from ${pctOf(before.allOnTime)} to ${pctOf(after.allOnTime)} if you buy this now.`;
        planFindings.push({
          id: "plan_odds",
          agent: "analysis",
          severity: after.allOnTime < 0.5 ? "critical" : "warning",
          category: "plan",
          message,
          suggestion: "See the best way to fit it in, below the verdict.",
        });
        ctx.emit("analysis", "finding", message, { stepId: current.id, level: "warning" });
      }
      finish(
        current,
        `${impact.affected.length ? `${impact.affected.length} of your ${session.goals.length} goal(s) move in the expected future. ` : ""}Every goal on time: ${pctOf(before.allOnTime)} today, ${pctOf(after.allOnTime)} with this purchase.`,
      );

      // 5b. Strategist: the smallest changes that make room for it -------------------------
      current = step("fit");
      start(current);
      if (before.allOnTime - after.allOnTime < 0.05) {
        finish(current, "No search needed: buying this barely changes your odds.");
      } else {
        const fitStep = current;
        const proposal = await ctx.callTool(
          searchPlanTool((r) => {
            ctx.emit(
              "strategist",
              "finding",
              r.accepted
                ? `Round ${r.round}: tried ${r.tried} changes. Best: ${r.accepted.text}.`
                : `Round ${r.round}: tried ${r.tried} changes; none beat its disruption.`,
              { stepId: fitStep.id },
            );
          }, "quick"),
          { ...withPurchase, incomeVariability: variability },
          current.id,
        );
        const fresh = summarizeOdds(proposal.after);
        if (proposal.changes.length && proposal.after.score > proposal.before.score) {
          run.planOdds.bestFit = {
            changes: proposal.changes,
            after: fresh,
            evaluations: proposal.evaluations,
          };
          finish(
            current,
            `${proposal.changes.map((c) => c.text).join("; ")} → every goal on time in ${pctOf(fresh.allOnTime)} of fresh futures.`,
          );
        } else {
          finish(current, "No small change makes enough room; the trade-off is real.");
        }
      }
    }

    // 6. Verification --------------------------------------------------------------------------
    current = step("verify");
    start(current);
    const findings = await ctx.callTool(
      verifyTool,
      {
        profile: session.profile.values,
        request,
        inputs,
        analysis,
        assumptions: run.assumptions,
        documentFacts: documentFacts(session),
        researchLive: run.research?.live ?? false,
      },
      current.id,
    );
    run.findings = [...findings, ...risks, ...planFindings];
    for (const f of findings.filter((x) => x.severity !== "info")) {
      ctx.emit("verification", "finding", f.message, {
        stepId: current.id,
        level: f.severity === "critical" ? "error" : "warning",
      });
      audit(session, "verification_flag", "agent:verification", f.message, run.id);
    }
    finish(
      current,
      `${findings.length} finding(s): ${findings.filter((f) => f.severity === "critical").length} critical, ${findings.filter((f) => f.severity === "warning").length} warnings.`,
    );

    // 7. Synthesis -----------------------------------------------------------------------------
    current = step("synthesise");
    start(current);
    const alternatives = await buildAlternatives(
      ctx,
      inputs,
      analysis,
      session.profile.values.emergencyBufferMonths ?? 6,
      current.id,
    );
    const summary = buildSummary(analysis, scenarios, run.findings);
    const narrative = await aiNarrative(
      ctx,
      {
        assessment: analysis.label,
        purchase_price: inputs.purchase.purchasePrice,
        down_payment: analysis.downPayment,
        upfront_cash: analysis.upfrontCash,
        loan_amount: analysis.loanAmount,
        annual_rate_percent: inputs.purchase.annualInterestRate,
        tenure_months: inputs.purchase.tenureMonths,
        emi: analysis.emi,
        total_interest: analysis.totalInterest,
        savings_after_purchase: analysis.postPurchaseSavings,
        monthly_surplus_after: analysis.after.cashFlow.monthlySurplus,
        debt_to_income_after: analysis.after.dti,
        emergency_months_after: analysis.after.emergencyMonths,
        scenarios: scenarios.map((s) => ({
          name: s.params.name,
          label: s.label,
          month_savings_run_out: s.monthExhausted,
          monthly_surplus: s.monthlySurplus,
        })),
        alternatives: alternatives.map((a) => ({ title: a.title, figures: a.figures })),
      },
      current.id,
    );
    run.recommendation = buildRecommendation(analysis, summary, alternatives, narrative);
    audit(
      session,
      "recommendation_generated",
      "agent:planner",
      run.recommendation.headline,
      run.id,
    );
    finish(
      current,
      `${run.recommendation.headline}. ${alternatives.length} alternative(s) computed.`,
    );

    // 8. Action plan ---------------------------------------------------------------------------
    current = step("act");
    start(current);
    const draft = await ctx.callTool(
      actionPlanTool,
      {
        runId: run.id,
        request,
        profile: session.profile.values,
        analysis,
        alternatives,
        findings: run.findings,
        researchLive: run.research?.live ?? false,
      },
      current.id,
    );
    if (run.planImpact?.affected.length) {
      draft.items.unshift({
        id: `item_${draft.items.length + 1}`,
        category: "savings",
        title: "Re-plan the goals this purchase moves",
        detail: `${run.planImpact.affected.map((a) => a.name).join(", ")} would move. Decide which comes first in your plan before committing.`,
        done: false,
        requiresIntegration: false,
      });
    }
    const now = new Date().toISOString();
    const plan: ActionPlan = {
      ...draft,
      id: newId("plan"),
      createdAt: now,
      status: "draft",
      statusHistory: [{ status: "draft", at: now, by: "agent" }],
    };
    transitionActionPlan(plan, "awaiting_review", "agent", "Prepared by the Action Agent");
    session.actionPlans.unshift(plan);
    run.actionPlanId = plan.id;
    audit(
      session,
      "action_prepared",
      "agent:action",
      `Prepared "${plan.title}" (${plan.items.length} items)`,
      run.id,
    );
    audit(
      session,
      "approval_requested",
      "agent:action",
      `Awaiting your review: "${plan.title}"`,
      run.id,
    );
    finish(
      current,
      `Checklist of ${plan.items.length} items prepared and awaiting your approval. Nothing has been submitted.`,
    );

    run.status = "completed";
    run.finishedAt = new Date().toISOString();
    ctx.emit(
      "orchestrator",
      "run_completed",
      `Recommendation ready: ${run.recommendation.headline}`,
    );
    return run;
  } catch (error) {
    const message =
      error instanceof LimitExceededError
        ? error.message
        : error instanceof Error
          ? `A step failed: ${error.message}`
          : "A step failed";
    if (current && current.status === "running") {
      current.status = "failed";
      current.summary = message;
      ctx.emit(current.agent, "step_failed", message, { stepId: current.id, level: "error" });
    }
    for (const s of run.plan) if (s.status === "pending") s.status = "skipped";
    run.status = "failed";
    run.error = message;
    run.finishedAt = new Date().toISOString();
    ctx.emit("orchestrator", "run_failed", message, { level: "error" });
    audit(session, "service_unavailable", "orchestrator", `Workflow failed: ${message}`, run.id);
    return run;
  } finally {
    saveRun(session, run);
  }
}
