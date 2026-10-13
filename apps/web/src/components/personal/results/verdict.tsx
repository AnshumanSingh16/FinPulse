"use client";

import { ArrowRight, CircleDashed } from "lucide-react";

import { formatINR } from "@/lib/format";
import type { WorkflowRun } from "@/lib/personal/agents/types";
import { DEFAULT_RULES } from "@/lib/personal/finance/affordability";
import { inrWords } from "@/lib/personal/finance/parse-inr";
import { cn } from "@/lib/utils";

import { Meter } from "../kit";
import { ASSESSMENT, AssessmentBadge } from "../ui";

/** The thresholds the analysis was actually evaluated with (the rules engine's defaults). */
const RULES = DEFAULT_RULES;

type Limiter = { id: string; text: string };

/** The binding constraint, in one sentence, from the rule checks' own values. */
export function limitingFactors(run: WorkflowRun): Limiter[] {
  const a = run.analysis!;
  const order = { fail: 0, warn: 1, pass: 2 } as const;
  const sorted = [...a.checks]
    .filter((c) => c.status !== "pass")
    .sort((x, y) => order[x.status] - order[y.status]);
  const out: Limiter[] = [];
  for (const c of sorted) {
    const v = c.value;
    if (v === null) continue;
    if (c.id === "upfront_cash")
      out.push({
        id: c.id,
        text: `Your savings fall ${formatINR(-v)} short of the cash needed upfront.`,
      });
    if (c.id === "monthly_surplus")
      out.push({
        id: c.id,
        text: `Your monthly costs would exceed your take-home pay by ${formatINR(-v)}.`,
      });
    if (c.id === "emergency_cover")
      out.push({
        id: c.id,
        text: `After the down payment and upfront costs you'd keep ${inrWords(a.postPurchaseSavings)} — about ${v.toFixed(1)} months of essential spending, below the ${RULES.emergencyComfortableMonths}-month guide.`,
      });
    if (c.id === "debt_to_income")
      out.push({
        id: c.id,
        text: `All EMIs together would take ${Math.round(v * 100)}% of your take-home pay.`,
      });
    if (c.id === "surplus_buffer")
      out.push({
        id: c.id,
        text: `Only ${Math.round(v * 100)}% of your pay would be left after every monthly cost.`,
      });
  }
  return out;
}

/**
 * Input completeness: how much of the analysis rests on figures the user (or their documents, or
 * the demo profile) supplied versus FinPulse's labelled estimates and defaults. Computed from the
 * run's own assumption records — not a confidence score.
 */
export function completeness(run: WorkflowRun) {
  const provided = run.assumptions.filter((a) =>
    ["user", "document", "demo", "research"].includes(a.basis),
  );
  const estimated = run.assumptions.filter(
    (a) => a.basis === "illustrative" || a.basis === "default",
  );
  return { provided: provided.length, total: run.assumptions.length, estimated };
}

export function VerdictPanel({ run, onEvidence }: { run: WorkflowRun; onEvidence: () => void }) {
  const a = run.analysis!;
  const rec = run.recommendation!;
  const tone = ASSESSMENT[rec.label].tone;
  const limits = limitingFactors(run);
  const comp = completeness(run);
  return (
    <section
      aria-labelledby="verdict-title"
      className="fp-rise relative overflow-hidden rounded-2xl border border-line bg-surface shadow-sm"
    >
      <span
        className={cn(
          "absolute inset-y-0 left-0 w-1",
          tone === "good"
            ? "bg-brand-600"
            : tone === "warn"
              ? "bg-caution-500"
              : tone === "bad"
                ? "bg-danger-500"
                : "bg-ink-400",
        )}
        aria-hidden
      />
      <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-8">
        <div className="flex flex-col gap-3">
          <AssessmentBadge label={rec.label} long />
          <h1
            id="verdict-title"
            className="text-[24px] leading-tight font-bold text-balance sm:text-[28px]"
          >
            {rec.headline}
          </h1>
          <p className="text-[15px] leading-relaxed text-pretty text-ink-700">
            {limits[0]?.text ??
              `You'd keep ${inrWords(a.postPurchaseSavings)} in savings and ${formatINR(a.after.cashFlow.monthlySurplus)} each month after every cost.`}
          </p>
          {limits.length > 1 ? (
            <p className="text-[13px] text-pretty text-ink-500">
              Also:{" "}
              {limits
                .slice(1)
                .map((l) => l.text.replace(/\.$/, "").toLowerCase())
                .join("; ")}
              .
            </p>
          ) : null}
          {rec.narrative ? (
            <p className="rounded-xl bg-agent-50 p-3 text-[13px] leading-relaxed text-pretty text-agent-700">
              <span className="font-semibold">FinPulse AI: </span>
              {rec.narrative.text}
              <span className="block pt-1 text-[11px] opacity-80">
                Every figure checked against the calculations.
              </span>
            </p>
          ) : null}
          <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-2 pt-1">
            <span className="inline-flex items-center gap-2 text-[13px] text-ink-500">
              <CircleDashed className="size-4 text-ink-400" aria-hidden />
              <span>
                <span className="font-semibold text-ink-900">
                  {comp.provided} of {comp.total}
                </span>{" "}
                inputs are your figures
                {comp.estimated.length
                  ? ` · ${comp.estimated.length} estimate${comp.estimated.length === 1 ? "" : "s"}`
                  : ""}
              </span>
            </span>
            <button
              type="button"
              onClick={onEvidence}
              className="inline-flex items-center gap-1 text-[13px] font-semibold text-brand-700 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            >
              Assumptions & evidence <ArrowRight className="size-3.5" aria-hidden />
            </button>
          </div>
        </div>
        <SavingsRunway run={run} />
      </div>
    </section>
  );
}

/**
 * Where the savings go and how long what's left would last. Segments and months come straight
 * from the analysis; the guide lines are the rule thresholds the verdict used.
 */
export function SavingsRunway({ run }: { run: WorkflowRun }) {
  const a = run.analysis!;
  const savings = run.inputs!.household.liquidSavings;
  const down = a.downPayment;
  const upfront = Math.max(0, a.upfrontCash - a.downPayment);
  const left = a.postPurchaseSavings;
  const shortfall = left < 0 ? -left : 0;
  const scale = Math.max(savings, down + upfront);
  const w = (n: number) => `${Math.max(0, (n / scale) * 100)}%`;
  const months = a.after.emergencyMonths ?? 0;
  const outflow = a.after.cashFlow.totalMonthlyOutflow;
  const target = run.profileSnapshot.emergencyBufferMonths;
  const max = Math.max(12, Math.ceil(months + 1), (target ?? 0) + 2);
  const leftTone =
    months >= RULES.emergencyComfortableMonths
      ? "good"
      : months >= RULES.emergencyMinimumMonths
        ? "warn"
        : "bad";

  const segments = [
    { key: "down", label: "Down payment", value: down, cls: "bg-ink-700" },
    { key: "upfront", label: "One-time", value: upfront, cls: "bg-ink-400" },
    {
      key: "left",
      label: "Left over",
      value: Math.max(0, left),
      cls:
        leftTone === "good"
          ? "bg-brand-500"
          : leftTone === "warn"
            ? "bg-caution-500"
            : "bg-danger-500",
    },
  ];

  return (
    <div className="flex flex-col gap-5 rounded-xl bg-surface-sunken p-4 sm:p-5">
      <div className="flex flex-col gap-2.5">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-[13px] font-semibold text-ink-900">Your savings runway</h2>
          <span className="tabular text-[12px] text-ink-500">of {formatINR(savings)} saved</span>
        </div>
        <div
          className="flex h-3.5 gap-[2px] overflow-hidden rounded-full bg-surface"
          role="img"
          aria-label={`Of ${formatINR(savings)}: ${formatINR(down)} down payment, ${formatINR(upfront)} one-time costs, ${formatINR(left)} left.`}
        >
          {segments.map((s) =>
            s.value > 0 ? (
              <span
                key={s.key}
                className={cn("fp-grow h-full first:rounded-l-full last:rounded-r-full", s.cls)}
                style={{ width: w(s.value) }}
              />
            ) : null,
          )}
          {shortfall ? (
            <span className="h-full bg-danger-500/40" style={{ width: w(shortfall) }} />
          ) : null}
        </div>
        <dl className="grid grid-cols-3 gap-2">
          {segments.map((s) => (
            <div key={s.key} className="flex flex-col gap-0.5">
              <dt className="flex items-center gap-1.5 text-[11.5px] whitespace-nowrap text-ink-500">
                <span className={cn("size-2 rounded-sm", s.cls)} aria-hidden />
                {s.label}
              </dt>
              <dd
                className={cn(
                  "tabular font-display text-[14px] font-bold whitespace-nowrap sm:text-[15px]",
                  s.key === "left" && left < 0 && "text-danger-text",
                )}
              >
                {formatINR(s.key === "left" ? left : s.value)}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="text-[13px] font-semibold text-ink-900">How long it would last</h3>
          <span
            className={cn(
              "tabular font-display text-[17px] font-bold",
              leftTone === "good"
                ? "text-brand-700"
                : leftTone === "warn"
                  ? "text-caution-text"
                  : "text-danger-text",
            )}
          >
            {months.toFixed(1)} months
          </span>
        </div>
        <Meter
          label="Months of essential spending covered by savings left after buying"
          value={months}
          max={max}
          valueText={`${months.toFixed(1)} months`}
          zones={[
            { to: RULES.emergencyMinimumMonths, tone: "bad" },
            { to: RULES.emergencyComfortableMonths, tone: "warn" },
            { to: max, tone: "good" },
          ]}
          markers={[
            { at: RULES.emergencyMinimumMonths, label: `${RULES.emergencyMinimumMonths} mo min` },
            {
              at: RULES.emergencyComfortableMonths,
              label: `${RULES.emergencyComfortableMonths} mo guide`,
            },
            ...(target &&
            target !== RULES.emergencyComfortableMonths &&
            target !== RULES.emergencyMinimumMonths
              ? [{ at: target, label: `your ${target} mo` }]
              : []),
          ]}
        />
        <p className="text-[12px] leading-snug text-pretty text-ink-500">
          Essential spending after buying is {formatINR(outflow)}/month (living costs, all EMIs
          {run.inputs!.purchase.monthlyOwnershipCost ? ", running costs" : ""}). Guide lines are
          FinPulse&apos;s rule thresholds, not a lender&apos;s criteria.
        </p>
      </div>
    </div>
  );
}
