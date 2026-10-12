import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { scenariosTool, ScenarioParamsSchema } from "@/lib/personal/agents/tools";
import { jsonError, readJson, refuseCrossOrigin } from "@/lib/personal/http";
import { getSession } from "@/lib/personal/session";
import { audit, consumeRateLimit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

const Body = z.object({
  runId: z.string().max(40),
  scenarios: z.array(ScenarioParamsSchema).min(1).max(8),
  /** Optional overrides to the analysis inputs ("adjust assumptions and rerun"). */
  overrides: z
    .object({
      annualInterestRate: z.number().min(0).max(50).optional(),
      tenureMonths: z.number().int().min(1).max(600).optional(),
      downPaymentPct: z.number().min(0).max(100).optional(),
      monthlyOwnershipCost: z.number().min(0).max(1e9).optional(),
    })
    .optional(),
});

/** Run custom stress scenarios against a completed analysis (the Risk Agent's tool). */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = Body.safeParse(await readJson(request));
  if (!parsed.success)
    return jsonError(
      400,
      "Invalid scenario request",
      parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`),
    );
  const session = await getSession();
  if (!consumeRateLimit(session))
    return jsonError(429, "Too many requests. Wait a minute and try again.");
  const run = session.runs.find((r) => r.id === parsed.data.runId);
  if (!run?.inputs) return jsonError(404, "No completed analysis with that id");
  const inputs = {
    purchase: { ...run.inputs.purchase, ...parsed.data.overrides },
    household: run.inputs.household,
  };
  const input = { inputs, scenarios: parsed.data.scenarios };
  const ok = scenariosTool.input.safeParse(input);
  if (!ok.success) return jsonError(400, "Invalid scenario parameters");
  try {
    const results = await scenariosTool.run(ok.data, new AbortController().signal);
    audit(
      session,
      "scenario_executed",
      "agent:risk",
      `Custom stress test on "${run.request.label}": ${scenariosTool.summarize(results)}`,
      run.id,
    );
    return NextResponse.json({ results, inputs });
  } catch (error) {
    return jsonError(400, error instanceof Error ? error.message : "Scenario failed");
  }
}
