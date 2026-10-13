"use client";

import { AlertTriangle, CircleUser, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import type { AgentName } from "@/lib/personal/agents/types";
import type { AuditEvent } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

import { AGENT_META, AgentGlyph, Chip } from "./kit";
import { usePersonal } from "./provider";
import { EmptyState, Loading, PageTitle } from "./ui";

const GROUPS: Record<string, { label: string; types: AuditEvent["type"][] }> = {
  all: { label: "All", types: [] },
  agents: {
    label: "Agent work",
    types: [
      "plan_created",
      "research_completed",
      "calculation_completed",
      "scenario_executed",
      "verification_flag",
      "recommendation_generated",
      "action_prepared",
      "missing_information",
    ],
  },
  approvals: {
    label: "Approvals",
    types: ["approval_requested", "approval_decision", "action_completed"],
  },
  data: {
    label: "Your data",
    types: [
      "profile_updated",
      "document_uploaded",
      "document_confirmed",
      "demo_loaded",
      "session_reset",
      "goal_submitted",
      "copilot_message",
    ],
  },
  problems: {
    label: "Issues",
    types: ["verification_flag", "service_unavailable", "missing_information"],
  },
};

const CAUTION: AuditEvent["type"][] = ["verification_flag", "missing_information"];
const APPROVAL: AuditEvent["type"][] = [
  "approval_requested",
  "approval_decision",
  "action_completed",
];

function title(type: AuditEvent["type"]) {
  return type.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** The actor recorded by the server ("user", "agent:risk", "system" …), shown with its icon. */
function Actor({ actor }: { actor: string }) {
  const agent = actor.startsWith("agent:") ? (actor.slice(6) as AgentName) : null;
  if (agent && agent in AGENT_META) return <AgentGlyph agent={agent} size="sm" />;
  return (
    <span
      className="inline-flex size-6 shrink-0 items-center justify-center rounded-lg bg-surface-sunken text-ink-500"
      aria-hidden
    >
      <CircleUser className="size-3.5" />
    </span>
  );
}

function actorLabel(actor: string) {
  if (actor.startsWith("agent:")) {
    const a = actor.slice(6) as AgentName;
    return a in AGENT_META ? `${AGENT_META[a].label} agent` : actor;
  }
  return actor === "user" ? "You" : actor.replace(/^\w/, (c) => c.toUpperCase());
}

function dayLabel(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  const y = new Date();
  y.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === y.toDateString()) return "Yesterday";
  return d.toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });
}

export function AuditTrail() {
  const { state } = usePersonal();
  const [group, setGroup] = useState("all");
  if (!state) return <Loading />;
  const match = (k: string, e: AuditEvent) => k === "all" || GROUPS[k]!.types.includes(e.type);
  const events = state.audit.filter((e) => match(group, e));

  // Group consecutive events (already newest first) by calendar day.
  const days: { label: string; items: AuditEvent[] }[] = [];
  for (const e of events) {
    const label = dayLabel(e.at);
    const last = days[days.length - 1];
    if (last?.label === label) last.items.push(e);
    else days.push({ label, items: [e] });
  }

  return (
    <div className="flex flex-col gap-6">
      <PageTitle
        eyebrow="Everything that happened"
        title="Activity log"
        description="Every goal, agent step, verification flag, approval and data change — recorded by the server as it happened, not reconstructed afterwards. Newest first."
      />

      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter events">
        {Object.entries(GROUPS).map(([k, g]) => {
          const n = state.audit.filter((e) => match(k, e)).length;
          return (
            <Chip key={k} selected={group === k} onClick={() => setGroup(k)}>
              {g.label}
              <span className="tabular text-[12px] text-ink-400">{n}</span>
            </Chip>
          );
        })}
      </div>

      {events.length === 0 ? (
        <EmptyState
          title={state.audit.length ? "Nothing in this filter" : "No activity yet"}
          action={
            state.audit.length ? undefined : (
              <Link
                href="/afford"
                className="text-[14px] font-semibold text-brand-700 hover:underline"
              >
                Start an analysis →
              </Link>
            )
          }
        >
          {state.audit.length
            ? "Try another filter to see the rest of the log."
            : "Load the demo or run an analysis and every step will be recorded here."}
        </EmptyState>
      ) : (
        days.map((d) => (
          <section key={d.label} className="flex flex-col gap-2" aria-label={d.label}>
            <h2 className="text-[12px] font-semibold tracking-wide text-ink-400 uppercase">
              {d.label}
            </h2>
            <ol className="overflow-hidden rounded-2xl border border-line bg-surface shadow-xs">
              {d.items.map((e) => {
                const caution = CAUTION.includes(e.type);
                const failed = e.type === "service_unavailable";
                return (
                  <li
                    key={e.id}
                    className={cn(
                      "flex gap-3 border-b border-line px-4 py-3 last:border-0 sm:px-5",
                      caution && "bg-caution-50/50",
                      failed && "bg-danger-50/50",
                    )}
                  >
                    <Actor actor={e.actor} />
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                        <span className="text-[14px] font-semibold text-ink-900">
                          {title(e.type)}
                        </span>
                        {caution ? (
                          <AlertTriangle
                            className="size-3.5 text-caution-text"
                            aria-label="Needs attention"
                          />
                        ) : null}
                        {failed ? (
                          <AlertTriangle
                            className="size-3.5 text-danger-text"
                            aria-label="Service unavailable"
                          />
                        ) : null}
                        {APPROVAL.includes(e.type) ? (
                          <ShieldCheck className="size-3.5 text-brand-600" aria-label="Approval" />
                        ) : null}
                      </div>
                      <p className="text-[13.5px] text-pretty text-ink-700">{e.summary}</p>
                      <p className="flex flex-wrap items-center gap-x-2 text-[12px] text-ink-400">
                        <span>{actorLabel(e.actor)}</span>
                        <span aria-hidden>·</span>
                        <time className="tabular" dateTime={e.at}>
                          {new Date(e.at).toLocaleTimeString("en-IN", { hour12: false })}
                        </time>
                        {e.runId ? (
                          <>
                            <span aria-hidden>·</span>
                            <Link
                              href={`/afford?run=${e.runId}`}
                              className="font-mono text-[11px] text-ink-500 hover:text-brand-700 hover:underline"
                            >
                              {e.runId}
                            </Link>
                          </>
                        ) : null}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        ))
      )}
    </div>
  );
}
