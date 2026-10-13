"use client";

import { formatINR } from "@/lib/format";
import type { WorkflowRun } from "@/lib/personal/agents/types";
import { inrWords } from "@/lib/personal/finance/parse-inr";
import { cn } from "@/lib/utils";

import { AmortizationChart } from "../charts";
import { Disclosure, SourceBadge } from "../ui";

type Segment = { label: string; value: number; cls: string };

/** One quantity split into labelled parts. Direct labels + legend: colour is never the only cue. */
function SplitBar({ segments, label }: { segments: Segment[]; label: string }) {
  const total = segments.reduce((s, x) => s + Math.max(0, x.value), 0) || 1;
  return (
    <div className="flex flex-col gap-2.5">
      <div
        className="flex h-3 gap-[2px] overflow-hidden rounded-full bg-surface-sunken"
        role="img"
        aria-label={`${label}: ${segments.map((s) => `${s.label} ${formatINR(s.value)}`).join(", ")}`}
      >
        {segments.map((s) =>
          s.value > 0 ? (
            <span
              key={s.label}
              className={cn("fp-grow h-full first:rounded-l-full last:rounded-r-full", s.cls)}
              style={{ width: `${(s.value / total) * 100}%` }}
            />
          ) : null,
        )}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {segments.map((s) => (
          <li key={s.label} className="flex items-center gap-1.5 text-[12px] text-ink-500">
            <span className={cn("size-2 rounded-sm", s.cls)} aria-hidden />
            {s.label}
            <span className="tabular font-medium text-ink-700">
              {Math.round((Math.max(0, s.value) / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Row({
  label,
  value,
  strong,
  badge,
  tone,
}: {
  label: string;
  value: string;
  strong?: boolean;
  badge?: React.ReactNode;
  tone?: "good" | "bad";
}) {
  return (
    <div
      className={cn(
        "flex items-baseline justify-between gap-3 py-2",
        strong && "border-t border-line pt-2.5",
      )}
    >
      <dt
        className={cn(
          "flex items-center gap-2 text-[14px]",
          strong ? "font-semibold text-ink-900" : "text-ink-500",
        )}
      >
        {label}
        {badge}
      </dt>
      <dd
        className={cn(
          "tabular text-right text-[14px]",
          strong ? "font-display text-[16px] font-bold" : "font-medium text-ink-900",
          tone === "good" && "text-brand-700",
          tone === "bad" && "text-danger-text",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function Group({
  title,
  lead,
  children,
}: {
  title: string;
  lead: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-5 shadow-xs">
      <header className="flex flex-col gap-1">
        <h3 className="text-[15px] font-bold">{title}</h3>
        <p className="text-[13px] leading-snug text-pretty text-ink-500">{lead}</p>
      </header>
      {children}
    </section>
  );
}

export function NumbersPanel({ run }: { run: WorkflowRun }) {
  const a = run.analysis!;
  const { purchase: p, household: h } = run.inputs!;
  const upfrontCosts = p.upfrontCashCosts + p.financedCosts;
  const upfrontEstimated =
    run.assumptions.find((x) => x.id === "in_upfront")?.basis === "illustrative";
  const before = a.before.cashFlow;
  const after = a.after.cashFlow;
  const interestShare = a.totalRepayment > 0 ? a.totalInterest / a.totalRepayment : 0;
  const crossover = a.yearly.find((y) => y.principalPaid > y.interestPaid);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Group
        title="Buying it"
        lead={`Where the ${inrWords(p.purchasePrice + upfrontCosts)} comes from, including one-time costs.`}
      >
        <SplitBar
          label="Purchase funding"
          segments={[
            { label: "Down payment", value: a.downPayment, cls: "bg-ink-700" },
            { label: "One-time costs", value: upfrontCosts, cls: "bg-ink-400" },
            { label: "Loan", value: a.loanAmount, cls: "bg-chart-1" },
          ]}
        />
        <dl className="flex flex-col">
          <Row label="Price" value={formatINR(p.purchasePrice)} />
          <Row label={`Down payment (${p.downPaymentPct}%)`} value={formatINR(a.downPayment)} />
          <Row
            label="One-time costs"
            value={formatINR(upfrontCosts)}
            badge={upfrontEstimated ? <SourceBadge kind="illustrative" /> : null}
          />
          <Row label="Loan amount" value={formatINR(a.loanAmount)} />
          <Row label="Cash you pay upfront" value={formatINR(a.upfrontCash)} strong />
        </dl>
      </Group>

      <Group
        title="Every month"
        lead="Your take-home pay today and after buying, from your profile and the new EMI."
      >
        <SplitBar
          label="Take-home pay after buying"
          segments={[
            {
              label: "Living costs",
              value: h.monthlyExpenses + p.monthlyOwnershipCost + h.otherMonthlyObligations,
              cls: "bg-ink-400",
            },
            { label: "Current EMIs", value: h.existingEmis, cls: "bg-ink-700" },
            { label: "New EMI", value: a.emi, cls: "bg-chart-1" },
            { label: "Left over", value: Math.max(0, after.monthlySurplus), cls: "bg-brand-500" },
          ]}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-[14px]">
            <caption className="sr-only">Monthly cash flow today and after buying</caption>
            <thead>
              <tr className="text-left text-[12px] text-ink-500">
                <th className="py-1.5 font-medium" scope="col">
                  <span className="sr-only">Item</span>
                </th>
                <th className="py-1.5 text-right font-medium" scope="col">
                  Today
                </th>
                <th className="py-1.5 text-right font-medium" scope="col">
                  After buying
                </th>
              </tr>
            </thead>
            <tbody className="tabular">
              {[
                ["Take-home pay", before.monthlyIncome, after.monthlyIncome],
                [
                  "Living costs",
                  -(before.monthlyExpenses + before.monthlyOtherObligations),
                  -(after.monthlyExpenses + after.monthlyOtherObligations),
                ],
                ["All EMIs", -before.monthlyDebtPayments, -after.monthlyDebtPayments],
              ].map(([l, b, x]) => (
                <tr key={l as string} className="border-t border-line">
                  <th scope="row" className="py-2 text-left font-normal text-ink-500">
                    {l}
                  </th>
                  <td className="py-2 text-right">{formatINR(b as number)}</td>
                  <td className="py-2 text-right">{formatINR(x as number)}</td>
                </tr>
              ))}
              <tr className="border-t border-line-strong">
                <th scope="row" className="py-2.5 text-left font-semibold">
                  Left over
                </th>
                <td className="py-2.5 text-right font-semibold">
                  {formatINR(before.monthlySurplus)}
                </td>
                <td
                  className={cn(
                    "py-2.5 text-right font-display text-[16px] font-bold",
                    after.monthlySurplus < 0 ? "text-danger-text" : "text-brand-700",
                  )}
                >
                  {formatINR(after.monthlySurplus)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Group>

      <Group
        title="Over the loan"
        lead={
          a.loanAmount > 0
            ? `You'd repay ${inrWords(a.totalRepayment)} for a ${inrWords(a.loanAmount)} loan — interest is ${Math.round(interestShare * 100)}% of everything you pay.`
            : "No loan is needed: the purchase is paid in cash."
        }
      >
        {a.loanAmount > 0 ? (
          <>
            <SplitBar
              label="Total repayment"
              segments={[
                { label: "Principal", value: a.loanAmount, cls: "bg-chart-1" },
                { label: "Interest", value: a.totalInterest, cls: "bg-chart-2" },
              ]}
            />
            <dl className="flex flex-col">
              <Row label="Total interest" value={formatINR(a.totalInterest)} />
              <Row label="Total repayment" value={formatINR(a.totalRepayment)} strong />
            </dl>
            {crossover ? (
              <p className="text-[13px] text-pretty text-ink-500">
                Your EMI pays more interest than principal until year {crossover.year}. Prepaying
                early in the loan saves the most interest.
              </p>
            ) : null}
          </>
        ) : null}
      </Group>

      {a.yearly.length ? (
        <section className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-5 shadow-xs">
          <header className="flex flex-col gap-1">
            <h3 className="text-[15px] font-bold">Principal vs interest, year by year</h3>
            <p className="text-[13px] text-ink-500">
              From the month-by-month amortization schedule.
            </p>
          </header>
          <AmortizationChart yearly={a.yearly} />
        </section>
      ) : null}

      <div className="lg:col-span-2">
        <Disclosure title="How these are calculated" hint="The formulas behind every number above">
          <ul className="flex flex-col gap-2 text-[13px] leading-relaxed text-ink-700">
            <li>
              <span className="font-semibold">EMI</span> = P × r × (1 + r)ⁿ ÷ ((1 + r)ⁿ − 1), with P
              = {formatINR(a.loanAmount)}, r = {p.annualInterestRate}% ÷ 12 and n = {p.tenureMonths}{" "}
              months → <span className="tabular font-semibold">{formatINR(a.emi)}</span>.
            </li>
            <li>
              <span className="font-semibold">Savings after buying</span> ={" "}
              {formatINR(h.liquidSavings)} − {formatINR(a.upfrontCash)} ={" "}
              <span className="tabular font-semibold">{formatINR(a.postPurchaseSavings)}</span>.
            </li>
            <li>
              <span className="font-semibold">Months of cover</span> = savings after buying ÷
              essential spending ({formatINR(after.totalMonthlyOutflow)}) ={" "}
              <span className="tabular font-semibold">
                {a.after.emergencyMonths?.toFixed(1) ?? "—"}
              </span>
              .
            </li>
            <li>
              <span className="font-semibold">Debt-to-income</span> = all EMIs (
              {formatINR(a.newMonthlyDebt)}) ÷ take-home pay ({formatINR(h.monthlyIncome)}) ={" "}
              <span className="tabular font-semibold">
                {a.after.dti === null ? "—" : `${(a.after.dti * 100).toFixed(1)}%`}
              </span>
              .
            </li>
          </ul>
        </Disclosure>
      </div>
    </div>
  );
}
