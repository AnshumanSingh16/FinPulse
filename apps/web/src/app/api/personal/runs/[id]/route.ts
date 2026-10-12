import { NextResponse } from "next/server";

import { jsonError } from "@/lib/personal/http";
import { getSession } from "@/lib/personal/session";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = (await getSession()).runs.find((r) => r.id === id);
  return run
    ? NextResponse.json(run, { headers: { "cache-control": "no-store" } })
    : jsonError(404, "Analysis not found");
}
