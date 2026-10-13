"use client";

import { Briefcase, Car, GraduationCap, Home, Pencil, Plus, ShoppingBag } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type { AgentEvent, WorkflowRun } from "@/lib/personal/agents/types";
import type { PurchaseType } from "@/lib/personal/schemas";
import type { ActionPlan } from "@/lib/personal/store";

import { Tabs } from "./kit";
import { MetricTrio } from "./results/metrics";
import { NextStepsPanel } from "./results/next";
import { NumbersPanel } from "./results/numbers";
import { AgentRail } from "./results/rail";
import { VerdictPanel } from "./results/verdict";
import { WhatIfPanel } from "./results/whatif";
import { WhyPanel } from "./results/why";

const TYPE_ICON: Record<PurchaseType, typeof Home> = {
  house: Home,
  car: Car,
  education: GraduationCap,
  business: Briefcase,
  custom: ShoppingBag,
};

type TabId = "numbers" | "whatif" | "why" | "next";

function GoalHeader({
  run,
  onEdit,
  onNew,
}: {
  run: WorkflowRun;
  onEdit?: () => void;
  onNew?: () => void;
}) {
  const Icon = TYPE_ICON[run.request.type];
  const when = new Date(run.finishedAt ?? run.createdAt).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-line bg-surface text-ink-700 shadow-xs">
          <Icon className="size-5" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="line-clamp-2 text-[15px] font-semibold">
            {run.goal.replace(/^Copilot: /, "")}
          </span>
          <span className="text-[12px] text-ink-500">
            Analysed {when} · {run.request.label}
          </span>
        </div>
      </div>
      <div className="flex gap-2">
        {onEdit ? (
          <Button variant="outline" size="sm" onClick={onEdit}>
            <Pencil /> <span className="hidden sm:inline">Edit details</span>
            <span className="sm:hidden">Edit</span>
          </Button>
        ) : null}
        {onNew ? (
          <Button variant="ghost" size="sm" onClick={onNew}>
            <Plus /> <span className="hidden sm:inline">New analysis</span>
            <span className="sm:hidden">New</span>
          </Button>
        ) : null}
      </div>
    </div>
  );
}

/**
 * The affordability result. Decision first (verdict, runway, three figures), detail in tabs, and
 * the agents' work alongside — every figure comes from the analysis the server computed.
 */
export function RunResults({
  run,
  plan,
  onEdit,
  onNew,
}: {
  run: WorkflowRun;
  plan: ActionPlan | undefined;
  events?: AgentEvent[];
  onEdit?: () => void;
  onNew?: () => void;
}) {
  const [tab, setTab] = useState<TabId>("numbers");
  const tabsRef = useRef<HTMLDivElement>(null);
  if (!run.analysis || !run.inputs || !run.recommendation) return null;

  const go = (t: TabId) => {
    setTab(t);
    requestAnimationFrame(() =>
      tabsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };
  const issues = run.findings.filter(
    (f) => f.severity !== "info" && f.category !== "assumption",
  ).length;
  const strained =
    run.scenarios?.filter((s) => !s.isBaseline && s.label === "high_strain").length ?? 0;
  const pill = (n: number, tone: "warn" | "bad" = "warn") =>
    n ? (
      <span
        className={
          tone === "bad"
            ? "tabular rounded-full bg-danger-50 px-1.5 text-[11px] font-semibold text-danger-text"
            : "tabular rounded-full bg-caution-50 px-1.5 text-[11px] font-semibold text-caution-text"
        }
      >
        {n}
      </span>
    ) : undefined;

  return (
    <div className="flex flex-col gap-5">
      <GoalHeader run={run} onEdit={onEdit} onNew={onNew} />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-4">
          <VerdictPanel run={run} onEvidence={() => go("why")} />
          <MetricTrio run={run} />

          <div
            ref={tabsRef}
            className="sticky top-14 z-20 -mx-4 scroll-mt-16 bg-canvas/95 px-4 py-2 backdrop-blur-md sm:mx-0 sm:px-0 lg:top-0 lg:scroll-mt-4"
          >
            <Tabs
              label="Result details"
              value={tab}
              onChange={(id) => setTab(id as TabId)}
              items={[
                { id: "numbers", label: "The numbers" },
                { id: "whatif", label: "What if?", badge: pill(strained, "bad") },
                { id: "why", label: "Why this result?", badge: pill(issues) },
                {
                  id: "next",
                  label: "Next steps",
                  badge: plan?.status === "awaiting_review" ? pill(1) : undefined,
                },
              ]}
            />
          </div>

          <div
            role="tabpanel"
            id={`panel-${tab}`}
            aria-labelledby={`tab-${tab}`}
            key={tab}
            className="fp-rise"
          >
            {tab === "numbers" ? <NumbersPanel run={run} /> : null}
            {tab === "whatif" ? <WhatIfPanel run={run} /> : null}
            {tab === "why" ? <WhyPanel run={run} onEdit={onEdit} /> : null}
            {tab === "next" ? <NextStepsPanel run={run} plan={plan} /> : null}
          </div>
        </div>

        <div>
          <AgentRail run={run} plan={plan} onReview={() => go("next")} />
        </div>
      </div>
    </div>
  );
}
