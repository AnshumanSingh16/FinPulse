import type { NextRequest } from "next/server";

import { runAffordabilityWorkflow } from "@/lib/personal/agents/orchestrator";
import { jsonError, ndjsonStream, readJson, refuseCrossOrigin } from "@/lib/personal/http";
import { applyProfileUpdate } from "@/lib/personal/profile";
import { AnalyzeBodySchema } from "@/lib/personal/schemas";
import { getSession } from "@/lib/personal/session";
import { audit, consumeRateLimit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";
export const maxDuration = 150;

/**
 * Run the affordability workflow. Streams NDJSON: {type:"event", event} for every real agent
 * event as it happens, then {type:"run", run} with the final state.
 */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = AnalyzeBodySchema.safeParse(await readJson(request));
  if (!parsed.success) return jsonError(400, "Invalid analysis request", parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`));
  const session = await getSession();
  if (!consumeRateLimit(session)) return jsonError(429, "Too many requests. Wait a minute and try again.");
  const { purchase, profile, goal } = parsed.data;
  if (profile) {
    const changed = applyProfileUpdate(session, profile, { kind: "user", at: new Date().toISOString(), note: "Entered on the analysis form" });
    if (changed.length) audit(session, "profile_updated", "user", `Updated ${changed.length} profile field(s) from the analysis form`);
  }
  return ndjsonStream(async (send) => {
    const run = await runAffordabilityWorkflow(session, goal || `Can I afford ${purchase.label}?`, purchase, (event) => send({ type: "event", event }));
    send({ type: "run", run });
  });
}
