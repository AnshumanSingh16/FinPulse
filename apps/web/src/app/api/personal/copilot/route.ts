import type { NextRequest } from "next/server";
import { z } from "zod";

import { copilotTurn } from "@/lib/personal/agents/copilot";
import { jsonError, ndjsonStream, readJson, refuseCrossOrigin } from "@/lib/personal/http";
import { getSession } from "@/lib/personal/session";
import { consumeRateLimit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";
export const maxDuration = 180;

const Body = z.object({
  message: z.string().trim().min(1).max(1000),
  /** Ask about this analysis: keeps it in focus for follow-up questions. */
  runId: z.string().max(40).optional(),
});

/** One copilot turn. Streams tool calls and workflow events, then the reply. */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = Body.safeParse(await readJson(request, 8_000));
  if (!parsed.success) return jsonError(400, "Message must be 1–1000 characters");
  const session = await getSession();
  if (!consumeRateLimit(session))
    return jsonError(429, "Too many requests. Wait a minute and try again.");
  return ndjsonStream((send) =>
    copilotTurn(session, parsed.data.message, send, { runId: parsed.data.runId }),
  );
}
