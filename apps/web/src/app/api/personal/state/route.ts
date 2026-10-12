import { NextResponse } from "next/server";

import { stateView } from "@/lib/personal/http";
import { getSession } from "@/lib/personal/session";

export const dynamic = "force-dynamic";

/** Everything the personal-finance pages render, for this browser's session. */
export async function GET() {
  const session = await getSession();
  return NextResponse.json(stateView(session), { headers: { "cache-control": "no-store" } });
}
