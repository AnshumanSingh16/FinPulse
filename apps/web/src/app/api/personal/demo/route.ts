import { type NextRequest, NextResponse } from "next/server";

import { refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { DEMO_PROFILE, PROFILE_FIELDS } from "@/lib/personal/schemas";
import { getSession } from "@/lib/personal/session";
import { audit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

/** Load the fictional demo profile (replaces the current profile values). */
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
  audit(session, "demo_loaded", "user", "Loaded the fictional demo profile");
  return NextResponse.json(stateView(session));
}
