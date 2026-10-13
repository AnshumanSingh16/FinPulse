import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { decideStrategy, StrategyDecisionError } from "@/lib/personal/agents/strategist";
import { jsonError, readJson, refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { getSession } from "@/lib/personal/session";

export const dynamic = "force-dynamic";

const Body = z.object({ action: z.enum(["apply", "dismiss"]) });

/** The person's decision on a Strategist proposal (see decideStrategy). */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = Body.safeParse(await readJson(request));
  if (!parsed.success) return jsonError(400, "Invalid decision");
  const { id } = await params;
  const session = await getSession();
  try {
    decideStrategy(session, id, parsed.data.action);
  } catch (error) {
    if (error instanceof StrategyDecisionError) return jsonError(error.status, error.message);
    throw error;
  }
  return NextResponse.json(stateView(session), { headers: { "cache-control": "no-store" } });
}
