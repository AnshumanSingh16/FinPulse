"use client";

import Link from "next/link";

import { ActionPlanCard } from "./action-plan";
import { usePersonal } from "./provider";
import { Loading, Notice, Section } from "./ui";

export function ActionCenter() {
  const { state } = usePersonal();
  if (!state) return <Loading />;
  const plans = state.actionPlans;
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <div className="text-xs font-medium text-primary">Prepared by the Action Agent</div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">Next steps</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Next-step plans prepared by the Action Agent. Each one waits for your review; approval,
          rejection and completion are enforced by the server. FinPulse never submits applications,
          contacts lenders or moves money.
        </p>
      </header>
      {plans.length === 0 ? (
        <Notice tone="info" title="No action plans yet">
          Plans are prepared at the end of an affordability analysis.{" "}
          <Link href="/afford" className="text-primary hover:underline">
            Run one
          </Link>
          .
        </Notice>
      ) : (
        plans.map((p) => (
          <Section
            key={p.id}
            title={p.title}
            actions={
              <Link
                href={`/afford?run=${p.runId}`}
                className="text-xs text-primary hover:underline"
              >
                View analysis
              </Link>
            }
          >
            <ActionPlanCard plan={p} />
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer select-none">Approval history</summary>
              <ol className="mt-2 flex flex-col gap-1">
                {p.statusHistory.map((h, i) => (
                  <li key={i}>
                    {new Date(h.at).toLocaleString("en-IN")} — {h.status.replace("_", " ")} by{" "}
                    {h.by}
                    {h.note ? `: ${h.note}` : ""}
                  </li>
                ))}
              </ol>
            </details>
          </Section>
        ))
      )}
    </div>
  );
}
