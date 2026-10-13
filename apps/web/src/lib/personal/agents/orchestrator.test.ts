import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { currentMonth } from "../finance/plan";
import { demoGoals } from "../plan-model";
import { DEMO_PROFILE, DEMO_PURCHASE } from "../schemas";
import { loadSession, resetSession, transitionActionPlan, TransitionError } from "../store";
import { runAffordabilityWorkflow } from "./orchestrator";
import { verifyFigures } from "./synthesis";
import type { AgentEvent } from "./types";

describe("affordability workflow (no AI key)", () => {
  beforeEach(() => {
    delete process.env.ANTHROPIC_API_KEY;
    resetSession("test");
  });

  it("asks for missing information instead of guessing", async () => {
    const session = loadSession("test");
    const run = await runAffordabilityWorkflow(session, "Can I afford a house?", DEMO_PURCHASE);
    expect(run.status).toBe("needs_input");
    expect(run.missing.map((m) => m.field)).toEqual([
      "monthlyIncome",
      "monthlyExpenses",
      "liquidSavings",
      "existingEmis",
    ]);
    expect(run.analysis).toBeNull();
    expect(run.plan.filter((s) => s.status === "skipped").length).toBeGreaterThan(0);
  });

  it("checks the purchase against the saved goal plan", async () => {
    const session = loadSession("test");
    session.profile = { values: { ...DEMO_PROFILE }, sources: {}, isDemo: true, updatedAt: null };
    session.goals = demoGoals(currentMonth());
    const run = await runAffordabilityWorkflow(session, "House", DEMO_PURCHASE);
    expect(run.status).toBe("completed");
    const step = run.plan.find((s) => s.id === "plan");
    expect(step?.status).toBe("done");
    expect(run.toolCalls.some((c) => c.tool === "check_plan_impact" && c.status === "ok")).toBe(
      true,
    );
    expect(run.planImpact).not.toBeNull();
    // The ₹20 lakh+ of upfront cash comes out of the savings earmarked for the other goals.
    expect(run.planImpact!.affected.length).toBeGreaterThan(0);
    // One finding per moved goal, plus one because the odds fall sharply.
    expect(run.findings.filter((f) => f.category === "plan")).toHaveLength(
      run.planImpact!.affected.length + 1,
    );
    expect(run.findings.find((f) => f.id === "plan_odds")?.message).toMatch(
      /drops from \d+% to \d+%/,
    );
    // The same question across possible futures, and the Strategist's way to fit it in.
    expect(run.planOdds!.after.allOnTime).toBeLessThan(run.planOdds!.before.allOnTime);
    expect(run.plan.find((s) => s.id === "fit")?.status).toBe("done");
    expect(run.toolCalls.filter((c) => c.tool === "simulate_plan")).toHaveLength(2);
    expect(run.toolCalls.some((c) => c.tool === "search_better_plan" && c.status === "ok")).toBe(
      true,
    );
    expect(run.planOdds!.bestFit).not.toBeNull();
    expect(run.planOdds!.bestFit!.after.allOnTime).toBeGreaterThan(run.planOdds!.after.allOnTime);
    const plan = session.actionPlans.find((p) => p.runId === run.id)!;
    expect(plan.items[0]!.title).toBe("Re-plan the goals this purchase moves");
    expect(session.audit.some((a) => a.type === "plan_impact")).toBe(true);
  });

  it("skips the plan step when no goals are saved", async () => {
    const session = loadSession("test");
    session.profile = { values: { ...DEMO_PROFILE }, sources: {}, isDemo: true, updatedAt: null };
    const run = await runAffordabilityWorkflow(session, "House", DEMO_PURCHASE);
    expect(run.plan.some((s) => s.id === "plan" || s.id === "fit")).toBe(false);
    expect(run.planOdds).toBeNull();
    expect(run.planImpact).toBeNull();
  });

  it("runs every step on the demo profile and requests approval", async () => {
    const session = loadSession("test");
    session.profile = { values: { ...DEMO_PROFILE }, sources: {}, isDemo: true, updatedAt: null };
    const events: AgentEvent[] = [];
    const run = await runAffordabilityWorkflow(
      session,
      "Can I afford a ₹75 lakh house?",
      DEMO_PURCHASE,
      (e) => events.push(e),
    );

    expect(run.status).toBe("completed");
    expect(run.mode).toEqual({ ai: false, research: "illustrative" });
    expect(run.plan.every((s) => s.status === "done")).toBe(true);
    expect(run.analysis?.emi).toBe(52069.39);
    expect(run.analysis?.label).toBe("manageable_limited_buffer");
    expect(run.research?.live).toBe(false);
    expect(run.research?.sources[0]?.kind).toBe("illustrative");
    expect(run.scenarios?.length).toBeGreaterThanOrEqual(4);
    expect(run.recommendation?.narrative).toBeNull(); // no AI: no AI narrative, never canned text
    expect(run.recommendation?.alternatives.map((a) => a.id)).toEqual(
      expect.arrayContaining(["lower_price", "save_first", "higher_down_payment"]),
    );
    expect(run.plan[0]?.title).toBe("Understanding your goal");
    // upfront costs and ownership costs were not entered: disclosed, not silent
    expect(run.assumptions.find((a) => a.id === "in_upfront")?.basis).toBe("illustrative");
    expect(run.findings.some((f) => f.field === "monthlyOwnershipCost")).toBe(true);

    // every tool call is recorded and succeeded; events came from real operations
    expect(run.toolCalls.length).toBeGreaterThan(6);
    expect(run.toolCalls.every((c) => c.status === "ok")).toBe(true);
    expect(events.filter((e) => e.kind === "tool_result").length).toBe(run.toolCalls.length);

    const plan = session.actionPlans.find((p) => p.id === run.actionPlanId)!;
    expect(plan.status).toBe("awaiting_review");
    expect(plan.items.some((i) => i.requiresIntegration)).toBe(true);
    expect(session.audit.map((a) => a.type)).toEqual(
      expect.arrayContaining([
        "goal_submitted",
        "plan_created",
        "calculation_completed",
        "scenario_executed",
        "recommendation_generated",
        "approval_requested",
      ]),
    );
  });

  it("enforces the approval state machine", async () => {
    const session = loadSession("test");
    session.profile = { values: { ...DEMO_PROFILE }, sources: {}, isDemo: true, updatedAt: null };
    const run = await runAffordabilityWorkflow(session, "house", DEMO_PURCHASE);
    const plan = session.actionPlans.find((p) => p.id === run.actionPlanId)!;
    expect(() => transitionActionPlan(plan, "completed", "user")).toThrow(TransitionError);
    expect(() => transitionActionPlan(plan, "approved", "agent")).toThrow(TransitionError);
    transitionActionPlan(plan, "approved", "user");
    transitionActionPlan(plan, "completed", "user");
    expect(plan.statusHistory.map((h) => h.status)).toEqual([
      "draft",
      "awaiting_review",
      "approved",
      "completed",
    ]);
  });
});

describe("verifyFigures", () => {
  it("accepts figures that match tool outputs and rejects invented ones", () => {
    const allowed = [52069.39, 6_000_000, 550_000];
    expect(
      verifyFigures("An EMI of ₹52,069 on a ₹60 lakh loan leaves ₹5.5 lakh.", allowed, [33.5]),
    ).toEqual([]);
    expect(verifyFigures("Banks offer ₹70 lakh at 7.2%.", allowed, [33.5])).toEqual([
      "₹70 lakh",
      "7.2%",
    ]);
  });
});

describe("input provenance", () => {
  it("labels demo figures as demo data, not as the user's", async () => {
    resetSession("prov");
    const session = loadSession("prov");
    const at = new Date().toISOString();
    session.profile = {
      values: { ...DEMO_PROFILE },
      sources: { monthlyIncome: { kind: "demo", at }, liquidSavings: { kind: "document", at } },
      isDemo: true,
      updatedAt: at,
    };
    const run = await runAffordabilityWorkflow(session, "house", DEMO_PURCHASE);
    expect(run.assumptions.find((a) => a.id === "in_monthlyIncome")?.basis).toBe("demo");
    expect(run.assumptions.find((a) => a.id === "in_liquidSavings")?.basis).toBe("document");
  });
});
