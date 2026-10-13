/**
 * Server-side session store. Each browser gets an anonymous session id (httpOnly cookie); its
 * profile, workflow runs, action plans, documents and audit trail live here, in server memory.
 *
 * Hackathon scope: memory only (cleared on server restart; not shared between serverless
 * instances). Swap this module for a database-backed one to persist across restarts.
 */
import "server-only";

import type { WorkflowRun } from "./agents/types";
import { EMPTY_PROFILE, type FinancialProfile } from "./schemas";

export type ApprovalStatus =
  "draft" | "awaiting_review" | "approved" | "rejected" | "completed" | "failed";

export type ChecklistItem = {
  id: string;
  category: "savings" | "documents" | "research" | "protection" | "application";
  title: string;
  detail: string;
  done: boolean;
  /** Needs an external integration FinPulse does not have: it can be prepared, never executed. */
  requiresIntegration: boolean;
};

export type ActionPlan = {
  id: string;
  runId: string;
  title: string;
  createdAt: string;
  status: ApprovalStatus;
  statusHistory: { status: ApprovalStatus; at: string; by: "agent" | "user"; note?: string }[];
  items: ChecklistItem[];
  savingsPlan: {
    targetAmount: number;
    monthlySaving: number;
    months: number;
    rationale: string;
  } | null;
  draftAnswers: { question: string; answer: string; source: string }[];
  documentsNeeded: string[];
};

export type AuditEvent = {
  id: string;
  at: string;
  actor: string;
  type:
    | "goal_submitted"
    | "missing_information"
    | "plan_created"
    | "research_completed"
    | "calculation_completed"
    | "scenario_executed"
    | "verification_flag"
    | "recommendation_generated"
    | "action_prepared"
    | "approval_requested"
    | "approval_decision"
    | "action_completed"
    | "profile_updated"
    | "document_uploaded"
    | "document_confirmed"
    | "service_unavailable"
    | "copilot_message"
    | "demo_loaded"
    | "session_reset";
  summary: string;
  runId?: string;
};

export type ExtractedField = {
  key: string;
  label: string;
  value: number | string;
  confidence: "high" | "medium" | "low";
  evidence: string;
  profileField?: string;
};

export type DocumentRecord = {
  id: string;
  name: string;
  size: number;
  mime: string;
  uploadedAt: string;
  docType: "salary_slip" | "bank_statement" | "loan_quote" | "expense_summary" | "unknown";
  extraction: {
    status: "extracted" | "partial" | "not_extracted" | "failed";
    method: "rule_based_text" | "ai" | "none";
    note: string;
    fields: ExtractedField[];
  };
  flags: { severity: "info" | "warning"; message: string }[];
  review: "pending" | "confirmed" | "dismissed";
  appliedFields: string[];
};

export type SessionState = {
  id: string;
  createdAt: string;
  lastSeen: number;
  profile: FinancialProfile;
  runs: WorkflowRun[];
  actionPlans: ActionPlan[];
  documents: DocumentRecord[];
  audit: AuditEvent[];
  copilot: { role: "user" | "assistant"; text: string }[];
  /** The analysis the copilot's follow-up questions are about. */
  focusRunId?: string;
  rate: { windowStart: number; count: number };
};

const MAX_SESSIONS = 500;
const MAX_RUNS = 20;
const MAX_AUDIT = 500;

type Store = Map<string, SessionState>;
const g = globalThis as unknown as { __finpulsePersonalStore?: Store };
const store: Store = (g.__finpulsePersonalStore ??= new Map());

export function newId(prefix: string): string {
  return `${prefix}_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
}

function freshSession(id: string): SessionState {
  return {
    id,
    createdAt: new Date().toISOString(),
    lastSeen: Date.now(),
    profile: { values: { ...EMPTY_PROFILE }, sources: {}, isDemo: false, updatedAt: null },
    runs: [],
    actionPlans: [],
    documents: [],
    audit: [],
    copilot: [],
    rate: { windowStart: Date.now(), count: 0 },
  };
}

export function loadSession(id: string): SessionState {
  let s = store.get(id);
  if (!s) {
    if (store.size >= MAX_SESSIONS) {
      // Evict the least recently seen session.
      let oldest: SessionState | undefined;
      for (const v of store.values()) if (!oldest || v.lastSeen < oldest.lastSeen) oldest = v;
      if (oldest) store.delete(oldest.id);
    }
    s = freshSession(id);
    store.set(id, s);
  }
  s.lastSeen = Date.now();
  return s;
}

export function resetSession(id: string): SessionState {
  store.delete(id);
  return loadSession(id);
}

export function audit(
  session: SessionState,
  type: AuditEvent["type"],
  actor: string,
  summary: string,
  runId?: string,
): AuditEvent {
  const event: AuditEvent = {
    id: newId("aud"),
    at: new Date().toISOString(),
    actor,
    type,
    summary,
    runId,
  };
  session.audit.push(event);
  if (session.audit.length > MAX_AUDIT) session.audit.splice(0, session.audit.length - MAX_AUDIT);
  return event;
}

export function saveRun(session: SessionState, run: WorkflowRun): void {
  const i = session.runs.findIndex((r) => r.id === run.id);
  if (i >= 0) session.runs[i] = run;
  else session.runs.unshift(run);
  if (session.runs.length > MAX_RUNS) session.runs.length = MAX_RUNS;
}

/** Simple fixed-window limit on expensive operations (analysis, copilot, uploads). */
export function consumeRateLimit(session: SessionState, limit = 30, windowMs = 60_000): boolean {
  const now = Date.now();
  if (now - session.rate.windowStart > windowMs) session.rate = { windowStart: now, count: 0 };
  session.rate.count += 1;
  return session.rate.count <= limit;
}

// ---------------------------------------------------------------- approval state machine

const TRANSITIONS: Record<ApprovalStatus, ApprovalStatus[]> = {
  draft: ["awaiting_review"],
  awaiting_review: ["approved", "rejected"],
  approved: ["completed", "failed"],
  rejected: ["awaiting_review"],
  completed: [],
  failed: ["awaiting_review"],
};

export class TransitionError extends Error {}

/**
 * The only way an action plan's status changes. The backend enforces the order — nothing can be
 * completed without a recorded user approval, whatever the client or an LLM asks for.
 */
export function transitionActionPlan(
  plan: ActionPlan,
  to: ApprovalStatus,
  by: "agent" | "user",
  note?: string,
): void {
  if (!TRANSITIONS[plan.status].includes(to)) {
    throw new TransitionError(`Cannot move an action plan from "${plan.status}" to "${to}"`);
  }
  if ((to === "approved" || to === "rejected" || to === "completed") && by !== "user") {
    throw new TransitionError(`Only the user can mark an action plan "${to}"`);
  }
  plan.status = to;
  plan.statusHistory.push({ status: to, at: new Date().toISOString(), by, note });
}
