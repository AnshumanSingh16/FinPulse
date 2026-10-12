import { type NextRequest, NextResponse } from "next/server";

import { refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { getSession } from "@/lib/personal/session";
import { audit, resetSession } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

/** Clear this session's profile, analyses, plans, documents and audit trail. */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const session = resetSession((await getSession()).id);
  audit(session, "session_reset", "user", "Reset all data for this session");
  return NextResponse.json(stateView(session));
}
