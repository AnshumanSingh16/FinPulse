import "server-only";

import { type NextRequest, NextResponse } from "next/server";

import { isSameOrigin } from "@/lib/api/proxy-policy";

import { aiStatus, liveResearchEnabled } from "./agents/llm";
import type { WorkflowRun } from "./agents/types";
import type { SessionState } from "./store";

export function jsonError(status: number, message: string, details?: unknown) {
  return NextResponse.json({ error: message, ...(details ? { details } : {}) }, { status, headers: { "cache-control": "no-store" } });
}

/** Mutating requests must come from this app's own pages (CSRF protection). */
export function refuseCrossOrigin(request: NextRequest): NextResponse | null {
  return isSameOrigin(request.method, request.headers, request.nextUrl.origin)
    ? null
    : jsonError(403, "Requests must come from this application.");
}

/** Read a JSON body with a size cap. Returns undefined when it is missing, too big or invalid. */
export async function readJson(request: Request, maxBytes = 64_000): Promise<unknown> {
  const length = Number(request.headers.get("content-length") ?? "0");
  if (length > maxBytes) return undefined;
  const text = await request.text();
  if (text.length > maxBytes) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

/** Newline-delimited JSON stream: one object per line, flushed as produced. */
export function ndjsonStream(work: (send: (item: unknown) => void) => Promise<void>): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (item: unknown) => {
        try {
          controller.enqueue(encoder.encode(`${JSON.stringify(item)}\n`));
        } catch {
          // client went away; the work still completes and is saved server-side
        }
      };
      try {
        await work(send);
      } catch {
        send({ type: "error", message: "The request failed unexpectedly." });
      } finally {
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      }
    },
  });
  return new Response(stream, {
    headers: { "content-type": "application/x-ndjson; charset=utf-8", "cache-control": "no-store", "x-accel-buffering": "no" },
  });
}

export function systemStatus() {
  const ai = aiStatus();
  return {
    ai: { enabled: ai.enabled, model: ai.model, reason: ai.reason },
    research: liveResearchEnabled()
      ? { mode: "live" as const, provider: "Anthropic web search" }
      : { mode: "illustrative" as const, provider: "Illustrative assumptions" },
    storage: "Server memory (per browser session; cleared on server restart)",
  };
}

export function runListItem(run: WorkflowRun) {
  return {
    id: run.id,
    goal: run.goal,
    label: run.request.label,
    type: run.request.type,
    status: run.status,
    createdAt: run.createdAt,
    assessment: run.analysis?.label ?? null,
    emi: run.analysis?.emi ?? null,
  };
}

export function stateView(session: SessionState) {
  return {
    status: systemStatus(),
    profile: session.profile,
    runs: session.runs.map(runListItem),
    latestRun: session.runs.find((r) => r.status === "completed") ?? session.runs[0] ?? null,
    actionPlans: session.actionPlans,
    documents: session.documents,
    audit: session.audit.slice(-200).reverse(),
    copilot: session.copilot,
  };
}
export type StateView = ReturnType<typeof stateView>;
