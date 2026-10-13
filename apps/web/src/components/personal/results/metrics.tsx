"use client";

import type { ReactNode } from "react";

import { formatINR } from "@/lib/format";
import type { WorkflowRun } from "@/lib/personal/agents/types";
import { inrWords } from "@/lib/personal/finance/parse-inr";
import { cn } from "@/lib/utils";

import { Delta } from "../kit";

function MetricCard({
  label,
  value,
  tone,
  children,
}: {
  label: string;
  value: string;
  tone?: "warn" | "bad";
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-[78%] snap-start flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:min-w-0 sm:p-5">
      <span className="text-[13px] font-medium text-ink-500">{label}</span>
      <span
        className={cn(
          "tabular font-display text-[26px] leading-none font-bold tracking-tight sm:text-[28px]",
          tone === "warn" && "text-caution-text",
          tone === "bad" && "text-danger-text",
        )}
      >
        {value}
      </span>
      <div className="mt-auto flex flex-col gap-2">{children}</div>
    </div>
  );
}

/** Before/after mini-bars on one scale, labelled. */
function BeforeAfter({ before, after, max }: { before: number; after: number; max: number }) {
  const w = (n: number) => `${Math.max(2, Math.min(100, (Math.max(0, n) / max) * 100))}%`;
  return (
    <div className="flex flex-col gap-1 text-[11.5px] text-ink-500" aria-hidden>
      <div className="flex items-center gap-2">
        <span className="w-10 shrink-0">Now</span>
        <span className="h-1.5 rounded-full bg-ink-400/60" style={{ width: w(before) }} />
      </div>
      <div className="flex items-center gap-2">
        <span className="w-10 shrink-0">After</span>
        <span
          className={cn("fp-grow h-1.5 rounded-full", after < 0 ? "bg-danger-500" : "bg-ink-900")}
          style={{ width: w(after) }}
        />
      </div>
    </div>
  );
}

/** The three figures that decide the purchase, each with the context that makes it meaningful. */
export function MetricTrio({ run }: { run: WorkflowRun }) {
  const a = run.analysis!;
  const inputs = run.inputs!;
  const income = inputs.household.monthlyIncome;
  const share = income > 0 ? a.emi / income : null;
  const before = a.before.cashFlow.monthlySurplus;
  const after = a.after.cashFlow.monthlySurplus;
  const savingsBefore = inputs.household.liquidSavings;
  const months = a.after.emergencyMonths;
  const coverTone =
    months === null ? undefined : months < 3 ? "bad" : months < 6 ? "warn" : undefined;

  return (
    <div className="-mx-4 flex snap-x snap-mandatory [scrollbar-width:none] gap-3 overflow-x-auto px-4 pb-1 sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0 sm:pb-0">
      <MetricCard label="Monthly EMI" value={formatINR(a.emi)}>
        <p className="text-[13px] text-ink-700">
          {share !== null ? (
            <>
              <span className="font-semibold">{Math.round(share * 100)}%</span> of your take-home
              pay
            </>
          ) : null}
        </p>
        <p className="text-[12px] text-ink-500">
          {inputs.purchase.annualInterestRate}% for {inputs.purchase.tenureMonths / 12} years on a{" "}
          {inrWords(a.loanAmount)} loan
        </p>
      </MetricCard>

      <MetricCard
        label="Left each month"
        value={formatINR(after)}
        tone={after < 0 ? "bad" : undefined}
      >
        <Delta
          value={after - before}
          format={(n) => formatINR(n)}
          goodWhen="up"
          suffix="vs today"
        />
        <BeforeAfter before={before} after={after} max={Math.max(before, after, 1)} />
      </MetricCard>

      <MetricCard
        label="Savings after buying"
        value={formatINR(a.postPurchaseSavings)}
        tone={a.postPurchaseSavings < 0 ? "bad" : coverTone}
      >
        <p className="text-[13px] text-ink-700">
          <span className="font-semibold">{months === null ? "—" : months.toFixed(1)} months</span>{" "}
          of essential spending
        </p>
        <BeforeAfter
          before={savingsBefore}
          after={a.postPurchaseSavings}
          max={Math.max(savingsBefore, 1)}
        />
      </MetricCard>
    </div>
  );
}
