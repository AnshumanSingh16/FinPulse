import type { NextRequest } from "next/server";

import { runStrategist } from "@/lib/personal/agents/strategist";
import { jsonError, ndjsonStream, refuseCrossOrigin } from "@/lib/personal/http";
import { getSession } from "@/lib/personal/session";
import { consumeRateLimit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";
export const maxDuration = 90;

/** Run the Strategist on the saved plan. Streams its events, then {type:"strategy", run}. */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const session = await getSession();
  if (!consumeRateLimit(session, 10))
    return jsonError(429, "Too many requests. Wait a minute and try again.");
  if (session.strategies[0]?.status === "running")
    return jsonError(409, "A search is already running");
  return ndjsonStream(async (send) => {
    const run = await runStrategist(session, (event) => send({ type: "event", event }));
    send({ type: "strategy", run });
  });
}
