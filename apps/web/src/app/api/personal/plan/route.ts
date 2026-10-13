import { type NextRequest, NextResponse } from "next/server";

import { jsonError, readJson, refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { PlanBodySchema } from "@/lib/personal/schemas";
import { getSession } from "@/lib/personal/session";
import { audit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

/** Replace the goal plan: the goals (in priority order) and the person's assumption overrides. */
export async function PUT(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = PlanBodySchema.safeParse(await readJson(request));
  if (!parsed.success)
    return jsonError(
      400,
      "Invalid plan",
      parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`),
    );
  const ids = new Set(parsed.data.goals.map((g) => g.id));
  if (ids.size !== parsed.data.goals.length) return jsonError(400, "Goal ids must be unique");
  const session = await getSession();
  const before = new Map(session.goals.map((g) => [g.id, g]));
  const added = parsed.data.goals.filter((g) => !before.has(g.id)).length;
  const removed = session.goals.filter((g) => !ids.has(g.id)).length;
  session.goals = parsed.data.goals;
  session.planAssumptions = parsed.data.assumptions;
  const parts = [
    added ? `${added} goal(s) added` : "",
    removed ? `${removed} removed` : "",
    `${session.goals.length} goal(s) in the plan`,
  ].filter(Boolean);
  audit(session, "plan_updated", "user", `Plan saved: ${parts.join(", ")}`);
  return NextResponse.json(stateView(session), { headers: { "cache-control": "no-store" } });
}
