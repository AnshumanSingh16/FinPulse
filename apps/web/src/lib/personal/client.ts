/**
 * Browser-side API helpers for the personal-finance pages. Same-origin fetches only; the session
 * cookie identifies the user's data on the server.
 */
import type { CopilotStreamItem } from "./agents/copilot";
import type { AgentEvent, WorkflowRun } from "./agents/types";
import type { ScenarioParams, ScenarioResult } from "./finance/scenarios";
import type { StateView } from "./http";
import type { ProfileValues, PurchaseRequest } from "./schemas";
import type { DocumentRecord } from "./store";

export type { StateView };

export class ClientError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly details?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, credentials: "same-origin", cache: "no-store" });
  if (!res.ok) {
    let body: { error?: string; details?: unknown } = {};
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    throw new ClientError(
      body.error ?? `Request failed (HTTP ${res.status})`,
      res.status,
      body.details,
    );
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  state: () => request<StateView>("/api/personal/state"),
  saveProfile: (values: Partial<ProfileValues>) =>
    request<StateView>("/api/personal/profile", json("PUT", { values })),
  loadDemo: () => request<StateView>("/api/personal/demo", json("POST")),
  reset: () => request<StateView>("/api/personal/reset", json("POST")),
  run: (id: string) => request<WorkflowRun>(`/api/personal/runs/${encodeURIComponent(id)}`),
  scenarios: (runId: string, scenarios: ScenarioParams[], overrides?: Record<string, number>) =>
    request<{ results: ScenarioResult[] }>(
      "/api/personal/scenarios",
      json("POST", { runId, scenarios, overrides }),
    ),
  action: (planId: string, body: Record<string, unknown>) =>
    request<StateView>(`/api/personal/actions/${encodeURIComponent(planId)}`, json("POST", body)),
  documentAction: (docId: string, body: Record<string, unknown>) =>
    request<StateView>(`/api/personal/documents/${encodeURIComponent(docId)}`, json("POST", body)),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ document: DocumentRecord; state: StateView }>("/api/personal/documents", {
      method: "POST",
      body: form,
    });
  },
};

/** POST and read an NDJSON stream, calling onItem for each line as it arrives. */
async function stream<T>(path: string, body: unknown, onItem: (item: T) => void): Promise<void> {
  const res = await fetch(path, { ...json("POST", body), credentials: "same-origin" });
  if (!res.ok || !res.body) {
    let message = `Request failed (HTTP ${res.status})`;
    try {
      message = ((await res.json()) as { error?: string }).error ?? message;
    } catch {
      /* not JSON */
    }
    throw new ClientError(message, res.status);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) onItem(JSON.parse(line) as T);
    }
  }
  if (buffer.trim()) onItem(JSON.parse(buffer) as T);
}

export type AnalyzeItem =
  | { type: "event"; event: AgentEvent }
  | { type: "run"; run: WorkflowRun }
  | { type: "error"; message: string };

export function analyze(
  body: { goal?: string; purchase: PurchaseRequest; profile?: Partial<ProfileValues> },
  onItem: (item: AnalyzeItem) => void,
) {
  return stream<AnalyzeItem>("/api/personal/analyze", body, onItem);
}

export function copilot(
  message: string,
  onItem: (item: CopilotStreamItem | { type: "error"; message: string }) => void,
) {
  return stream("/api/personal/copilot", { message }, onItem);
}
