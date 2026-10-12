import { type NextRequest, NextResponse } from "next/server";

import { jsonError, readJson, refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { applyProfileUpdate } from "@/lib/personal/profile";
import { ProfileValuesSchema } from "@/lib/personal/schemas";
import { getSession } from "@/lib/personal/session";
import { audit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

/** Update profile fields the user typed. Each changed field is marked as user-supplied. */
export async function PUT(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const body = await readJson(request);
  const parsed = ProfileValuesSchema.partial().safeParse((body as { values?: unknown })?.values);
  if (!parsed.success) return jsonError(400, "Invalid profile values", parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`));
  const session = await getSession();
  const changed = applyProfileUpdate(session, parsed.data, { kind: "user", at: new Date().toISOString() });
  if (changed.length) audit(session, "profile_updated", "user", `Updated ${changed.length} profile field(s): ${changed.join(", ")}`);
  return NextResponse.json(stateView(session));
}
