/**
 * Server-side session store. Each browser gets an anonymous session id (httpOnly cookie); its
 * profile, goal plan, check-ins, workflow runs, action plans, documents and audit trail live here.
 *
 * Storage (FINPULSE_STORAGE):
 *   file   (default) — kept in memory and written to one JSON file per session under
 *                      FINPULSE_DATA_DIR (default ./.finpulse-data), so a plan survives restarts.
 *                      Writes are debounced and atomic (write to a temp file, then rename).
 *   memory           — memory only; used by the tests and for throwaway demos.
 * A single Node process owns the files: run one instance, or swap this module for a database.
 */
import "server-only";

import fs from "node:fs";
import path from "node:path";

import type { StrategyRun, WorkflowRun } from "./agents/types";
import type { PlanAssumptions } from "./finance/plan";
import type { CheckIn } from "./plan-model";
import { EMPTY_PROFILE, type FinancialProfile, type PlanGoalValues } from "./schemas";

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
    | "session_reset"
    | "plan_updated"
    | "plan_impact"
    | "check_in"
    | "decision_compared"
    | "strategy_proposed"
    | "strategy_decision";
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
  /** The goal plan: every goal the household is working towards, in priority order. */
  goals: PlanGoalValues[];
  /** The person's own changes to the plan's growth, inflation and return assumptions. */
  planAssumptions: Partial<PlanAssumptions>;
  /** Monthly check-ins: what actually came in and went out. */
  checkIns: CheckIn[];
  /** Strategist runs, newest first. */
  strategies: StrategyRun[];
  /** The analysis the copilot's follow-up questions are about. */
  focusRunId?: string;
  rate: { windowStart: number; count: number };
};

const MAX_SESSIONS = 500;
const MAX_RUNS = 20;
const MAX_AUDIT = 500;
const MAX_CHECKINS = 60;

type Store = Map<string, SessionState>;
const g = globalThis as unknown as {
  __finpulsePersonalStore?: Store;
  __finpulseTimers?: Map<string, ReturnType<typeof setTimeout>>;
};
const store: Store = (g.__finpulsePersonalStore ??= new Map());
const timers = (g.__finpulseTimers ??= new Map());

export function storageMode(): "file" | "memory" {
  if (process.env.FINPULSE_STORAGE === "memory" || process.env.VITEST) return "memory";
  return "file";
}

export function storageLabel(): string {
  return storageMode() === "file"
    ? "Saved on this server (one private file per browser session)"
    : "Server memory only (cleared on restart)";
}

const dataDir = () => path.resolve(process.env.FINPULSE_DATA_DIR || ".finpulse-data");
const SAFE_ID = /^[a-zA-Z0-9_-]{8,64}$/;
const fileFor = (id: string) => path.join(dataDir(), `${id}.json`);

function readFromDisk(id: string): SessionState | null {
  if (storageMode() !== "file" || !SAFE_ID.test(id)) return null;
  try {
    const raw = JSON.parse(fs.readFileSync(fileFor(id), "utf8")) as Partial<SessionState>;
    if (raw.id !== id) return null;
    // Fill fields added in later versions so older files keep working.
    return { ...freshSession(id), ...raw, rate: { windowStart: Date.now(), count: 0 } };
  } catch {
    return null;
  }
}

function writeToDisk(session: SessionState): void {
  if (!SAFE_ID.test(session.id)) return;
  // A visit that changed nothing leaves no file behind (every change records an audit event).
  if (!session.audit.length && !session.profile.updatedAt && !fs.existsSync(fileFor(session.id)))
    return;
  try {
    fs.mkdirSync(dataDir(), { recursive: true, mode: 0o700 });
    const target = fileFor(session.id);
    const tmp = `${target}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(session), { mode: 0o600 });
    fs.renameSync(tmp, target);
  } catch (error) {
    console.error("[finpulse] could not save session", error instanceof Error ? error.message : "");
  }
}

/** Schedule a save of this session (debounced). Called by every mutation helper. */
export function persist(session: SessionState): void {
  if (storageMode() !== "file") return;
  const pending = timers.get(session.id);
  if (pending) clearTimeout(pending);
  timers.set(
    session.id,
    setTimeout(() => {
      timers.delete(session.id);
      writeToDisk(session);
    }, 150),
  );
}

function deleteFromDisk(id: string): void {
  if (storageMode() !== "file" || !SAFE_ID.test(id)) return;
  const pending = timers.get(id);
  if (pending) clearTimeout(pending);
  timers.delete(id);
  try {
    fs.rmSync(fileFor(id), { force: true });
  } catch {
    /* already gone */
  }
}

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
    goals: [],
    planAssumptions: {},
    checkIns: [],
    strategies: [],
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
    s = readFromDisk(id) ?? freshSession(id);
    store.set(id, s);
  }
  s.lastSeen = Date.now();
  // Most route handlers change the session synchronously right after loading it; the debounced
  // save runs after they finish. Long-running work also saves through audit() and saveRun().
  persist(s);
  return s;
}

export function resetSession(id: string): SessionState {
  store.delete(id);
  deleteFromDisk(id);
  return loadSession(id);
}

export function addCheckIn(session: SessionState, checkIn: CheckIn): void {
  session.checkIns = session.checkIns.filter((c) => c.month !== checkIn.month);
  session.checkIns.push(checkIn);
  session.checkIns.sort((a, b) => (a.month < b.month ? 1 : -1));
  if (session.checkIns.length > MAX_CHECKINS) session.checkIns.length = MAX_CHECKINS;
  persist(session);
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
  persist(session);
  return event;
}

export function saveRun(session: SessionState, run: WorkflowRun): void {
  const i = session.runs.findIndex((r) => r.id === run.id);
  if (i >= 0) session.runs[i] = run;
  else session.runs.unshift(run);
  if (session.runs.length > MAX_RUNS) session.runs.length = MAX_RUNS;
  persist(session);
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
  // The caller saves via audit(); action plans live inside the session.
}
