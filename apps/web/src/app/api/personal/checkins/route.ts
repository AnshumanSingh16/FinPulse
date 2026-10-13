import { type NextRequest, NextResponse } from "next/server";

import { formatINR } from "@/lib/format";
import { currentMonth, monthsBetween } from "@/lib/personal/finance/plan";
import { jsonError, readJson, refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { CheckInSchema } from "@/lib/personal/schemas";
import { getSession } from "@/lib/personal/session";
import { addCheckIn, audit, newId, persist } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

/** Record (or replace) one month's actual income and spending. */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = CheckInSchema.safeParse(await readJson(request));
  if (!parsed.success)
    return jsonError(
      400,
      "Invalid check-in",
      parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`),
    );
  if (monthsBetween(currentMonth(), parsed.data.month) > 0)
    return jsonError(400, "You can't check in for a month that hasn't started");
  const session = await getSession();
  addCheckIn(session, { ...parsed.data, id: newId("chk"), at: new Date().toISOString() });
  audit(
    session,
    "check_in",
    "user",
    `Checked in for ${parsed.data.month}: ${formatINR(parsed.data.income)} in, ${formatINR(parsed.data.spending)} out`,
  );
  return NextResponse.json(stateView(session), { headers: { "cache-control": "no-store" } });
}

export async function DELETE(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const month = request.nextUrl.searchParams.get("month") ?? "";
  const session = await getSession();
  const before = session.checkIns.length;
  session.checkIns = session.checkIns.filter((c) => c.month !== month);
  if (session.checkIns.length === before) return jsonError(404, "No check-in for that month");
  persist(session);
  audit(session, "check_in", "user", `Removed the check-in for ${month}`);
  return NextResponse.json(stateView(session), { headers: { "cache-control": "no-store" } });
}
