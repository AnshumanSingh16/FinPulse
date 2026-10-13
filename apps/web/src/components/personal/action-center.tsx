"use client";

import { ArrowUpRight, ListChecks } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import type { ApprovalStatus } from "@/lib/personal/store";

import { ActionPlanCard } from "./action-plan";
import { Chip } from "./kit";
import { usePersonal } from "./provider";
import { Disclosure, EmptyState, Loading, PageTitle } from "./ui";

const FILTERS: { key: "all" | ApprovalStatus; label: string }[] = [
  { key: "all", label: "All" },
  { key: "awaiting_review", label: "Waiting for you" },
  { key: "approved", label: "In progress" },
  { key: "completed", label: "Done" },
  { key: "rejected", label: "Set aside" },
];

export function ActionCenter() {
  const { state } = usePersonal();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  if (!state) return <Loading />;
  const plans = state.actionPlans;
  const shown = plans.filter((p) => filter === "all" || p.status === filter);

  return (
    <div className="flex flex-col gap-6">
      <PageTitle
        eyebrow="Prepared by the Action Agent"
        title="Next steps"
        description="Each plan waits for your review. Approval, rejection and completion are enforced by the server — FinPulse never submits applications, contacts lenders or moves money."
      />

      {plans.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="No next steps yet"
          action={
            <Link
              href="/afford"
              className="text-[14px] font-semibold text-brand-700 hover:underline"
            >
              Run an affordability analysis →
            </Link>
          }
        >
          The Action Agent prepares a checklist at the end of every affordability analysis.
        </EmptyState>
      ) : (
        <>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Filter plans">
            {FILTERS.map((f) => {
              const n = plans.filter((p) => f.key === "all" || p.status === f.key).length;
              if (f.key !== "all" && n === 0) return null;
              return (
                <Chip key={f.key} selected={filter === f.key} onClick={() => setFilter(f.key)}>
                  {f.label}
                  <span className="tabular text-[12px] text-ink-400">{n}</span>
                </Chip>
              );
            })}
          </div>
          {shown.map((p) => (
            <article
              key={p.id}
              className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-6"
              aria-labelledby={`plan-${p.id}`}
            >
              <header className="flex items-start justify-between gap-3">
                <h2 id={`plan-${p.id}`} className="text-[18px] leading-snug font-bold text-balance">
                  {p.title}
                </h2>
                <Link
                  href={`/afford?run=${p.runId}`}
                  className="inline-flex shrink-0 items-center gap-1 text-[13px] font-semibold text-brand-700 hover:underline"
                >
                  View analysis <ArrowUpRight className="size-3.5" aria-hidden />
                </Link>
              </header>
              <ActionPlanCard plan={p} />
              <Disclosure
                title="Approval history"
                hint={`${p.statusHistory.length} change(s), recorded by the server`}
              >
                <ol className="flex flex-col gap-2 text-[13px]">
                  {p.statusHistory.map((h, i) => (
                    <li key={i} className="flex flex-wrap gap-x-2 text-ink-700">
                      <time className="tabular text-ink-400" dateTime={h.at}>
                        {new Date(h.at).toLocaleString("en-IN", { hour12: false })}
                      </time>
                      <span className="font-medium">{h.status.replace(/_/g, " ")}</span>
                      <span className="text-ink-500">
                        by {h.by === "user" ? "you" : "the Action Agent"}
                      </span>
                      {h.note ? <span className="text-ink-500">— {h.note}</span> : null}
                    </li>
                  ))}
                </ol>
              </Disclosure>
            </article>
          ))}
        </>
      )}
    </div>
  );
}
