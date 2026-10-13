"use client";

import { CalendarClock, Coins, Home, PiggyBank, TimerReset } from "lucide-react";
import Link from "next/link";

import { formatINR } from "@/lib/format";
import type { Alternative, WorkflowRun } from "@/lib/personal/agents/types";
import type { ActionPlan } from "@/lib/personal/store";

import { ActionPlanCard } from "../action-plan";

const ICON: Record<string, typeof Home> = {
  lower_price: Home,
  save_first: PiggyBank,
  higher_down_payment: Coins,
  longer_tenure: CalendarClock,
};

function AlternativeCard({ alt }: { alt: Alternative }) {
  const Icon = ICON[alt.id] ?? TimerReset;
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-xs">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-700">
          <Icon className="size-[18px]" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-col gap-1">
          <h4 className="text-[14.5px] leading-snug font-bold text-pretty">{alt.title}</h4>
          <p className="text-[13px] leading-snug text-pretty text-ink-500">{alt.description}</p>
        </div>
      </div>
      {alt.figures.length ? (
        <dl className="mt-auto grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 border-t border-line pt-3 text-[13px]">
          {alt.figures.map((f) => (
            <div key={f.label} className="contents">
              <dt className="text-ink-500">{f.label}</dt>
              <dd className="tabular text-right font-semibold">
                {f.unit === "INR"
                  ? formatINR(f.value)
                  : f.unit === "months"
                    ? `${f.value} months`
                    : `${f.value}%`}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

export function NextStepsPanel({ run, plan }: { run: WorkflowRun; plan: ActionPlan | undefined }) {
  const alts = run.recommendation?.alternatives ?? [];
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3" aria-labelledby="ways">
        <div className="flex flex-col gap-1">
          <h3 id="ways" className="text-[15px] font-bold">
            Ways to make this work
          </h3>
          <p className="text-[13px] text-ink-500">
            Each option was recalculated with the same tools, so you can compare like for like.
          </p>
        </div>
        {alts.length ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {alts.map((alt) => (
              <AlternativeCard key={alt.id} alt={alt} />
            ))}
          </div>
        ) : (
          <p className="text-[14px] text-ink-500">
            No changes needed — this plan passes every rule under the stated assumptions.
          </p>
        )}
        <Link
          href={`/scenarios?run=${run.id}`}
          className="w-fit text-[13px] font-semibold text-brand-700 hover:underline"
        >
          Explore more in What-if scenarios →
        </Link>
      </section>

      <section
        className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-6"
        aria-labelledby="plan"
      >
        <div className="flex flex-col gap-1">
          <h3 id="plan" className="text-[15px] font-bold">
            Your action checklist
          </h3>
          <p className="text-[13px] text-pretty text-ink-500">
            Prepared by the Action agent. Nothing happens until you approve, and FinPulse never
            submits applications or moves money.
          </p>
        </div>
        {plan ? (
          <ActionPlanCard plan={plan} />
        ) : (
          <p className="text-[14px] text-ink-500">No checklist was prepared for this analysis.</p>
        )}
      </section>
    </div>
  );
}
