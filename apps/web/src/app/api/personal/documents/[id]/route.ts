import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { jsonError, readJson, refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { applyProfileUpdate } from "@/lib/personal/profile";
import { PROFILE_FIELDS, type ProfileValues } from "@/lib/personal/schemas";
import { getSession } from "@/lib/personal/session";
import { audit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

const Body = z.discriminatedUnion("action", [
  /** Apply the chosen extracted fields to the profile (user-confirmed). */
  z.object({ action: z.literal("confirm"), applyKeys: z.array(z.string().max(40)).max(20) }),
  z.object({ action: z.literal("dismiss") }),
  z.object({ action: z.literal("delete") }),
]);

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = Body.safeParse(await readJson(request));
  if (!parsed.success) return jsonError(400, "Invalid request");
  const session = await getSession();
  const { id } = await params;
  const doc = session.documents.find((d) => d.id === id);
  if (!doc) return jsonError(404, "Document not found");
  const body = parsed.data;
  if (body.action === "delete") {
    session.documents = session.documents.filter((d) => d.id !== id);
    return NextResponse.json(stateView(session));
  }
  if (body.action === "dismiss") {
    doc.review = "dismissed";
    audit(session, "document_confirmed", "user", `Dismissed the extraction from "${doc.name}"`);
    return NextResponse.json(stateView(session));
  }
  const update: Partial<ProfileValues> = {};
  for (const key of body.applyKeys) {
    const field = doc.extraction.fields.find((f) => f.key === key);
    const target = field?.profileField as (typeof PROFILE_FIELDS)[number] | undefined;
    if (!field || !target || typeof field.value !== "number" || !PROFILE_FIELDS.includes(target))
      continue;
    (update as Record<string, number>)[target] = field.value;
  }
  const changed = applyProfileUpdate(session, update, {
    kind: "document",
    at: new Date().toISOString(),
    documentId: doc.id,
    note: `From "${doc.name}" (confirmed by you)`,
  });
  doc.review = "confirmed";
  doc.appliedFields = [...new Set([...doc.appliedFields, ...changed])];
  audit(
    session,
    "document_confirmed",
    "user",
    `Reviewed "${doc.name}"${changed.length ? `; applied ${changed.join(", ")} to the profile` : "; nothing applied"}`,
  );
  return NextResponse.json(stateView(session));
}
