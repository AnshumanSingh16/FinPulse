import { NextResponse } from "next/server";

import { currentMonth } from "@/lib/personal/finance/plan";
import { cachedInsights } from "@/lib/personal/odds-cache";
import { getSession } from "@/lib/personal/session";

export const dynamic = "force-dynamic";

/** What hurts the saved plan most, and how much monthly spending room it has. */
export async function GET() {
  const session = await getSession();
  const insights = cachedInsights({
    profile: session.profile.values,
    goals: session.goals,
    assumptions: session.planAssumptions,
    startMonth: currentMonth(),
  });
  return NextResponse.json(insights, { headers: { "cache-control": "no-store" } });
}
