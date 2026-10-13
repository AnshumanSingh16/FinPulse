"use client";

import { ArrowRight, Check, Loader2, Plus, Route } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import type { WorkflowRun } from "@/lib/personal/agents/types";
import { api } from "@/lib/personal/client";
import { cn } from "@/lib/utils";

import { fmtMonth } from "../plan-workspace";
import { usePersonal } from "../provider";
import { Notice } from "../ui";

const VERDICT = {
  fits: { title: "Fits alongside your other goals", cls: "text-brand-700" },
  new_goal_late: {
    title: "Your other goals hold, but this can't be fully funded now",
    cls: "text-caution-text",
  },
  delays_others: { title: "Buying this now pushes other goals back", cls: "text-caution-text" },
  breaks_plan: { title: "Buying this now puts another goal out of reach", cls: "text-danger-text" },
} as const;

/**
 * What this purchase does to the person's saved goal plan (computed by the check_plan_impact tool
 * during the analysis), and a way to make it part of the plan.
 */
export function PlanImpactCard({ run }: { run: WorkflowRun }) {
  const { state, setState } = usePersonal();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inPlan = state?.plan.goals.some((g) => g.fromRunId === run.id) ?? false;
  const impact = run.planImpact;

  async function add() {
    setBusy(true);
    setError(null);
    try {
      setState(await api.addGoalFromRun(run.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't add it to your plan");
    } finally {
      setBusy(false);
    }
  }

  const addButton = inPlan ? (
    <Link
      href="/plan"
      className="inline-flex items-center gap-1.5 text-[13.5px] font-semibold text-brand-700 hover:underline"
    >
      <Check className="size-4" aria-hidden /> In your plan — open it
    </Link>
  ) : (
    <Button variant="outline" onClick={add} disabled={busy}>
      {busy ? <Loader2 className="animate-spin" /> : <Plus />} Add to my plan
    </Button>
  );

  if (!impact)
    return (
      <section className="flex flex-col gap-3 rounded-2xl border border-dashed border-line-strong bg-surface p-4 sm:flex-row sm:items-center sm:p-5">
        <Route className="size-5 shrink-0 text-ink-400" aria-hidden />
        <p className="flex-1 text-[13.5px] text-pretty text-ink-700">
          <span className="font-semibold text-ink-900">Checked on its own.</span> Save your other
          goals — a car, education, travel — and FinPulse shows what this purchase would push back.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          {addButton}
          <Link href="/plan" className="text-[13px] font-semibold text-brand-700 hover:underline">
            Set up my plan
          </Link>
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
      </section>
    );

  const v = VERDICT[impact.verdict];
  const freeDelta = impact.freeMonthlyAfter - impact.freeMonthlyBefore;
  return (
    <section
      className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-5"
      aria-labelledby="impact-h"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="flex items-center gap-1.5 text-[12px] font-semibold tracking-wide text-ink-400 uppercase">
            <Route className="size-3.5" aria-hidden /> Your other goals
          </span>
          <h2 id="impact-h" className={cn("text-[17px] font-bold", v.cls)}>
            {v.title}
          </h2>
        </div>
        {addButton}
      </div>
      {impact.affected.length ? (
        <ul className="flex flex-col gap-2">
          {impact.affected.map((a) => (
            <li
              key={a.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl bg-surface-sunken/70 px-3 py-2.5 text-[13.5px]"
            >
              <span className="font-semibold text-ink-900">{a.name}</span>
              <span className="tabular flex items-center gap-1.5 text-ink-500">
                {fmtMonth(a.before.achievedMonth)}
                <ArrowRight className="size-3.5" aria-hidden />
                <span
                  className={a.extraDelayMonths === null ? "text-danger-text" : "text-caution-text"}
                >
                  {a.after.achievedMonth ? fmtMonth(a.after.achievedMonth) : "out of reach"}
                </span>
              </span>
              {a.extraDelayMonths ? (
                <span className="tabular ml-auto text-[12.5px] font-medium text-caution-text">
                  +{a.extraDelayMonths} month{a.extraDelayMonths === 1 ? "" : "s"}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[13.5px] text-ink-700">
          Every saved goal still lands when you wanted it.
        </p>
      )}
      <p className="text-[12.5px] text-ink-500">
        Spare money after funding goals this month: {formatINR(impact.freeMonthlyBefore)} →{" "}
        <span className={cn("font-semibold", freeDelta < 0 ? "text-caution-text" : "text-ink-900")}>
          {formatINR(impact.freeMonthlyAfter)}
        </span>
        . Projected month by month with your plan&apos;s assumptions.{" "}
        <Link href="/plan" className="font-semibold text-brand-700 hover:underline">
          Change priorities or dates
        </Link>
      </p>
      {error ? <Notice tone="error">{error}</Notice> : null}
    </section>
  );
}
