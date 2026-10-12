"use client";

import { useState } from "react";

import type { AuditEvent } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

import { usePersonal } from "./provider";
import { Loading, Section } from "./ui";

const GROUPS: Record<string, { label: string; types: AuditEvent["type"][] }> = {
  all: { label: "All", types: [] },
  agents: { label: "Agent work", types: ["plan_created", "research_completed", "calculation_completed", "scenario_executed", "verification_flag", "recommendation_generated", "action_prepared", "missing_information"] },
  approvals: { label: "Approvals", types: ["approval_requested", "approval_decision", "action_completed"] },
  data: { label: "Your data", types: ["profile_updated", "document_uploaded", "document_confirmed", "demo_loaded", "session_reset", "goal_submitted", "copilot_message"] },
  problems: { label: "Issues", types: ["verification_flag", "service_unavailable", "missing_information"] },
};

const TONE: Partial<Record<AuditEvent["type"], string>> = {
  verification_flag: "bg-status-warning",
  service_unavailable: "bg-status-critical",
  missing_information: "bg-status-warning",
  approval_decision: "bg-primary",
  approval_requested: "bg-primary",
  action_completed: "bg-status-good",
  recommendation_generated: "bg-chart-1",
};

export function AuditTrail() {
  const { state } = usePersonal();
  const [group, setGroup] = useState("all");
  if (!state) return <Loading />;
  const events = state.audit.filter((e) => group === "all" || GROUPS[group]!.types.includes(e.type));
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <div className="text-xs font-medium tracking-wide text-primary uppercase">Trust & accountability</div>
        <h1 className="text-2xl font-semibold tracking-tight">Audit Trail</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">Every goal, agent step, verification flag, approval and data change, recorded by the server as it happened. Newest first.</p>
      </header>
      <Section title={`${events.length} event(s)`} actions={
        <div className="flex flex-wrap gap-1" role="group" aria-label="Filter events">
          {Object.entries(GROUPS).map(([k, g]) => (
            <button key={k} type="button" onClick={() => setGroup(k)} aria-pressed={group === k} className={cn("rounded-md border px-2.5 py-1 text-xs", group === k ? "border-primary/50 bg-primary/10 text-primary" : "text-muted-foreground")}>
              {g.label}
            </button>
          ))}
        </div>
      }>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No events.</p>
        ) : (
          <ol className="relative flex flex-col gap-3 border-l pl-5">
            {events.map((e) => (
              <li key={e.id} className="relative">
                <span className={cn("absolute top-1.5 -left-[25px] size-2.5 rounded-full ring-4 ring-card", TONE[e.type] ?? "bg-muted-foreground")} />
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
                  <span className="text-sm font-medium">{e.type.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())}</span>
                  <span className="text-xs text-primary">{e.actor}</span>
                  <span className="text-xs text-muted-foreground tabular">{new Date(e.at).toLocaleString("en-IN", { hour12: false })}</span>
                  {e.runId ? <span className="font-mono text-[10px] text-muted-foreground">{e.runId}</span> : null}
                </div>
                <p className="text-sm text-pretty text-muted-foreground">{e.summary}</p>
              </li>
            ))}
          </ol>
        )}
      </Section>
    </div>
  );
}
