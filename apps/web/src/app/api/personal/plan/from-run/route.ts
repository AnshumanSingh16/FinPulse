import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { currentMonth } from "@/lib/personal/finance/plan";
import { jsonError, readJson, refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { goalFromPurchase } from "@/lib/personal/plan-model";
import { getSession } from "@/lib/personal/session";
import { audit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

const Body = z.object({ runId: z.string().max(40) });

/** Add the purchase from a completed analysis to the goal plan, on the analysed terms. */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = Body.safeParse(await readJson(request));
  if (!parsed.success) return jsonError(400, "Invalid request");
  const session = await getSession();
  const run = session.runs.find((r) => r.id === parsed.data.runId);
  if (!run || run.status !== "completed" || !run.inputs)
    return jsonError(404, "That analysis isn't complete");
  if (session.goals.some((g) => g.fromRunId === run.id))
    return jsonError(409, "This purchase is already in your plan");
  if (session.goals.length >= 12) return jsonError(409, "A plan can hold up to 12 goals");
  const goal = goalFromPurchase(run.request, run.inputs.purchase, currentMonth(), run.id);
  // Same order the analysis checked: bought now, so funded first; the others keep their order.
  session.goals = [
    goal,
    ...[...session.goals]
      .sort((a, b) => a.priority - b.priority)
      .map((g, i) => ({ ...g, priority: Math.min(20, i + 2) })),
  ];
  audit(
    session,
    "plan_updated",
    "user",
    `Added "${goal.name}" to the plan from an analysis`,
    run.id,
  );
  return NextResponse.json(stateView(session), { headers: { "cache-control": "no-store" } });
}
