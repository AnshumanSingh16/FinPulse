import { type NextRequest, NextResponse } from "next/server";

import { currentMonth } from "@/lib/personal/finance/plan";
import { jsonError, readJson, refuseCrossOrigin } from "@/lib/personal/http";
import { cachedOdds } from "@/lib/personal/odds-cache";
import { summarizeOdds } from "@/lib/personal/plan-model";
import { PlanBodySchema } from "@/lib/personal/schemas";
import { getSession } from "@/lib/personal/session";
import { consumeRateLimit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

/** Odds for a draft plan (not saved): lets the plan page update the odds while editing. */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = PlanBodySchema.safeParse(await readJson(request));
  if (!parsed.success) return jsonError(400, "Invalid plan");
  const session = await getSession();
  if (!consumeRateLimit(session, 120))
    return jsonError(429, "Too many requests. Wait a minute and try again.");
  const odds = cachedOdds(
    {
      profile: session.profile.values,
      goals: parsed.data.goals,
      assumptions: parsed.data.assumptions,
      startMonth: currentMonth(),
    },
    500,
  );
  return NextResponse.json(odds ? { ...summarizeOdds(odds), fan: odds.fan } : null, {
    headers: { "cache-control": "no-store" },
  });
}
