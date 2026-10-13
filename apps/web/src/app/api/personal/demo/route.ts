import { type NextRequest, NextResponse } from "next/server";

import { refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { currentMonth } from "@/lib/personal/finance/plan";
import { demoCheckIns, demoGoals } from "@/lib/personal/plan-model";
import { DEMO_PROFILE, PROFILE_FIELDS } from "@/lib/personal/schemas";
import { getSession } from "@/lib/personal/session";
import { audit, newId } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

/**
 * Load the fictional demo household: profile, three goals and three months of check-ins.
 * Replaces the current profile, plan and check-ins.
 */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const session = await getSession();
  const at = new Date().toISOString();
  session.profile = {
    values: { ...DEMO_PROFILE },
    sources: Object.fromEntries(
      PROFILE_FIELDS.filter((f) => DEMO_PROFILE[f] !== null).map((f) => [
        f,
        { kind: "demo", at, note: "Fictional demo profile" },
      ]),
    ),
    isDemo: true,
    updatedAt: at,
  };
  const month = currentMonth();
  session.goals = demoGoals(month);
  // Fictional: the existing car loan has 30 EMIs left.
  session.planAssumptions = { existingEmiMonthsLeft: 30 };
  session.checkIns = demoCheckIns(month).map((c) => ({ ...c, id: newId("chk"), at }));
  audit(
    session,
    "demo_loaded",
    "user",
    `Loaded the fictional demo household (${session.goals.length} goals, ${session.checkIns.length} check-ins)`,
  );
  return NextResponse.json(stateView(session));
}
