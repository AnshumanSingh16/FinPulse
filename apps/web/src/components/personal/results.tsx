"use client";

import { ExternalLink, Pencil, Plus, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { AGENT_LABELS, type AgentEvent, type WorkflowRun } from "@/lib/personal/agents/types";
import type { ActionPlan } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

import { ActionPlanCard } from "./action-plan";
import { EventFeed, PlanTracker } from "./agent-activity";
import {
  AmortizationChart,
  IncomeAllocation,
  SavingsTrajectoryChart,
  ScenarioSurplusChart,
} from "./charts";
import {
  ASSESSMENT,
  AssessmentBadge,
  CheckBadge,
  Disclosure,
  Notice,
  Section,
  SourceBadge,
  Stat,
  StatRows,
  TONE_SOFT,
} from "./ui";

const months = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : `${n.toFixed(1)} months`;
const pct = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : `${(n * 100).toFixed(1)}%`;

/** The answer in one plain sentence, built only from the rule checks' own values. */
function answerSentence(run: WorkflowRun): string {
  const a = run.analysis!;
  const c = (id: string) => a.checks.find((x) => x.id === id)!;
  const reasons: string[] = [];
  const add = (id: string, text: (v: number) => string) => {
    const k = c(id);
    if (k && k.status !== "pass" && k.value !== null) reasons.push(text(k.value));
  };
  add("upfront_cash", (v) => `your savings fall ${formatINR(-v)} short of the cash needed upfront`);
  add("monthly_surplus", (v) => `your monthly costs would exceed your pay by ${formatINR(-v)}`);
  add(
    "emergency_cover",
    (v) => `you'd have only ${v.toFixed(1)} months of savings left after buying (6 is safer)`,
  );
  add("debt_to_income", (v) => `EMIs would take ${Math.round(v * 100)}% of your take-home pay`);
  add("surplus_buffer", (v) => `only ${Math.round(v * 100)}% of your pay would be left each month`);
  const list = reasons.slice(0, 2).join(", and ");
  if (a.label === "comfortable")
    return `Yes — under these assumptions you can afford it, with ${formatINR(a.after.cashFlow.monthlySurplus)} spare each month and ${a.after.emergencyMonths?.toFixed(1) ?? "—"} months of savings in reserve.`;
  if (a.label === "high_strain") return `Not as planned: ${list}.`;
  return `Probably, but it would be tight: ${list}.`;
}

const SECTIONS = [
  ["answer", "Answer"],
  ["numbers", "Numbers"],
  ["future", "What if"],
  ["why", "Why"],
  ["options", "Options"],
  ["next", "Next step"],
] as const;

export function RunResults({
  run,
  plan,
  events,
  onEdit,
  onNew,
}: {
  run: WorkflowRun;
  plan: ActionPlan | undefined;
  events: AgentEvent[];
  onEdit?: () => void;
  onNew?: () => void;
}) {
  const a = run.analysis;
  const inputs = run.inputs;
  const rec = run.recommendation;
  if (!a || !inputs || !rec) return null;
  const tone = ASSESSMENT[rec.label].tone;
  const estimates = run.assumptions.filter(
    (x) => x.basis === "illustrative" || x.basis === "default" || x.basis === "demo",
  );
  const risks = run.findings.filter((f) => f.severity !== "info" && f.category !== "assumption");
  const surplus = a.after.cashFlow.monthlySurplus;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-col">
          <span className="text-xs text-muted-foreground">Your question</span>
          <span className="truncate font-medium">{run.goal}</span>
        </div>
        <div className="flex gap-2">
          {onEdit ? (
            <Button variant="outline" size="sm" onClick={onEdit}>
              <Pencil /> Change details
            </Button>
          ) : null}
          {onNew ? (
            <Button variant="ghost" size="sm" onClick={onNew}>
              <Plus /> New question
            </Button>
          ) : null}
        </div>
      </div>

      <nav
        aria-label="Result sections"
        className="sticky top-14 z-20 -mx-4 flex gap-1 overflow-x-auto border-b bg-background/95 px-4 py-2 backdrop-blur lg:top-0"
      >
        {SECTIONS.map(([id, label]) => (
          <a
            key={id}
            href={`#${id}`}
            className="min-h-9 shrink-0 rounded-full px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {label}
          </a>
        ))}
      </nav>

      {/* 1. The answer */}
      <section
        id="answer"
        className={cn(
          "flex scroll-mt-28 flex-col gap-5 rounded-3xl p-5 sm:p-7",
          TONE_SOFT[tone].split(" ")[0],
        )}
      >
        <div className="flex flex-col gap-2">
          <AssessmentBadge label={rec.label} long className="bg-background/80" />
          <h1 className="text-2xl font-semibold tracking-tight text-balance text-foreground sm:text-3xl">
            {rec.headline}
          </h1>
          <p className="max-w-2xl text-base text-pretty text-foreground/85">
            {answerSentence(run)}
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 rounded-2xl bg-background p-5 sm:grid-cols-3 sm:divide-x [&>*]:sm:pl-5 [&>*:first-child]:sm:pl-0">
          <Stat
            label="Monthly EMI"
            value={formatINR(a.emi)}
            size="lg"
            sub={`${inputs.purchase.annualInterestRate}% for ${inputs.purchase.tenureMonths / 12} years`}
          />
          <Stat
            label="Left each month after everything"
            value={formatINR(surplus)}
            size="lg"
            tone={surplus < 0 ? "bad" : undefined}
            sub={`now ${formatINR(a.before.cashFlow.monthlySurplus)}`}
          />
          <Stat
            label="Savings left after buying"
            value={formatINR(a.postPurchaseSavings)}
            size="lg"
            tone={
              a.postPurchaseSavings < 0
                ? "bad"
                : (a.after.emergencyMonths ?? 99) < 3
                  ? "bad"
                  : (a.after.emergencyMonths ?? 99) < 6
                    ? "warn"
                    : undefined
            }
            sub={`${months(a.after.emergencyMonths)} of spending`}
          />
        </div>
        {rec.narrative ? (
          <p className="flex gap-2 text-sm text-pretty text-foreground/80">
            <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
            <span>
              {rec.narrative.text}{" "}
              <span className="text-xs text-muted-foreground">
                (AI summary; every figure checked against the calculations)
              </span>
            </span>
          </p>
        ) : null}
        {estimates.length ? (
          <p className="text-xs text-muted-foreground">
            Includes estimates:{" "}
            {estimates.map((e) => `${e.field.toLowerCase()} (${e.value})`).join(", ")}.{" "}
            <a href="#why" className="font-medium text-primary hover:underline">
              See assumptions
            </a>
          </p>
        ) : null}
      </section>

      {/* 2. The numbers */}
      <Section
        id="numbers"
        title="The numbers"
        description="Calculated by FinPulse's tested formulas — no AI involved."
      >
        <div className="grid gap-8 md:grid-cols-2">
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold">Paying for it</h3>
            <StatRows
              rows={[
                { label: "Price", value: formatINR(inputs.purchase.purchasePrice) },
                {
                  label: `Down payment (${inputs.purchase.downPaymentPct}%)`,
                  value: formatINR(a.downPayment),
                },
                {
                  label: (
                    <span className="inline-flex items-center gap-2">
                      One-time costs
                      {run.assumptions.find((x) => x.id === "in_upfront")?.basis ===
                      "illustrative" ? (
                        <SourceBadge kind="illustrative" />
                      ) : null}
                    </span>
                  ),
                  value: formatINR(
                    inputs.purchase.upfrontCashCosts + inputs.purchase.financedCosts,
                  ),
                  hint: inputs.purchase.financedCosts ? "added to the loan" : "paid upfront",
                },
                { label: "Cash you pay upfront", value: formatINR(a.upfrontCash), strong: true },
                { label: "Loan amount", value: formatINR(a.loanAmount) },
                { label: "Total interest over the loan", value: formatINR(a.totalInterest) },
                { label: "Total you repay", value: formatINR(a.totalRepayment) },
              ]}
            />
          </div>
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold">Every month, after buying</h3>
            <StatRows
              rows={[
                { label: "Take-home pay", value: formatINR(inputs.household.monthlyIncome) },
                {
                  label: "Living expenses",
                  value: `− ${formatINR(inputs.household.monthlyExpenses)}`,
                },
                { label: "Current EMIs", value: `− ${formatINR(inputs.household.existingEmis)}` },
                { label: "New EMI", value: `− ${formatINR(a.emi)}` },
                ...(inputs.purchase.monthlyOwnershipCost
                  ? [
                      {
                        label: "Running costs",
                        value: `− ${formatINR(inputs.purchase.monthlyOwnershipCost)}`,
                      },
                    ]
                  : []),
                ...(inputs.household.otherMonthlyObligations
                  ? [
                      {
                        label: "Other fixed costs",
                        value: `− ${formatINR(inputs.household.otherMonthlyObligations)}`,
                      },
                    ]
                  : []),
                {
                  label: "Left over",
                  value: formatINR(surplus),
                  strong: true,
                  tone: surplus < 0 ? ("bad" as const) : ("good" as const),
                },
                {
                  label: "EMIs as share of pay",
                  value: pct(a.after.dti),
                  hint: "debt-to-income, on take-home pay",
                },
              ]}
            />
          </div>
        </div>
        {a.yearly.length ? (
          <Disclosure
            title="How your EMI splits over the years"
            hint="Principal vs interest, by loan year"
          >
            <AmortizationChart yearly={a.yearly} />
          </Disclosure>
        ) : null}
      </Section>

      {/* 3. The future */}
      {run.scenarios ? <FutureSection run={run} /> : null}

      {/* 4. The explanation */}
      <Section
        id="why"
        title="Why we said this"
        description="The assessment comes from explicit rules applied to your numbers, then checked by the Risk and Verification agents."
      >
        <ul className="flex flex-col divide-y rounded-2xl border">
          {a.checks.map((c) => (
            <li key={c.id} className="flex items-start justify-between gap-3 px-4 py-3">
              <div className="flex min-w-0 flex-col">
                <span className="text-sm font-medium">{c.label}</span>
                <span className="text-xs text-muted-foreground">
                  Yours:{" "}
                  {c.value === null
                    ? "—"
                    : c.id === "debt_to_income" || c.id === "surplus_buffer"
                      ? pct(c.value)
                      : c.id === "emergency_cover"
                        ? months(c.value)
                        : formatINR(c.value)}{" "}
                  · Guide: {c.displayThreshold}
                </span>
              </div>
              <CheckBadge status={c.status} />
            </li>
          ))}
        </ul>
        {risks.length ? (
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Things to watch</h3>
            {risks.map((f) => (
              <Notice
                key={f.id + f.message}
                tone={f.severity === "critical" ? "error" : "warning"}
                title={f.message}
              >
                {f.suggestion}
              </Notice>
            ))}
          </div>
        ) : null}
        <Disclosure
          title="Assumptions and estimates"
          hint={`${estimates.length} estimate${estimates.length === 1 ? "" : "s"} — replace them with your real figures for a better answer`}
        >
          <ul className="flex flex-col divide-y">
            {run.assumptions.map((as) => (
              <li key={as.id} className="flex flex-col gap-1 py-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="font-medium">{as.field}</span>
                  <span className="flex items-center gap-2">
                    <span className="tabular">{as.value}</span>
                    <SourceBadge kind={as.basis === "user" ? "user" : as.basis} />
                  </span>
                </div>
                <span className="text-xs text-pretty text-muted-foreground">{as.note}</span>
              </li>
            ))}
          </ul>
        </Disclosure>
        <Disclosure
          title="How the rules work"
          hint="Thresholds are guides, not a lender's criteria"
        >
          <ul className="flex flex-col gap-3 text-sm text-muted-foreground">
            {a.checks.map((c) => (
              <li key={c.id}>
                <span className="font-medium text-foreground">{c.label}.</span> {c.explanation}
              </li>
            ))}
          </ul>
        </Disclosure>
      </Section>

      {/* 5. Alternatives */}
      <Section
        id="options"
        title="Your options"
        description="Each option is recalculated with the same tools, so you can compare like for like."
      >
        {rec.alternatives.length ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {rec.alternatives.map((alt) => (
              <div key={alt.id} className="flex flex-col gap-2 rounded-2xl border p-4">
                <div className="font-medium text-pretty">{alt.title}</div>
                <p className="text-sm text-pretty text-muted-foreground">{alt.description}</p>
                {alt.figures.length ? (
                  <dl className="mt-auto grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 border-t pt-3 text-sm">
                    {alt.figures.map((f) => (
                      <div key={f.label} className="contents">
                        <dt className="text-muted-foreground">{f.label}</dt>
                        <dd className="tabular text-right font-medium">
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
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No changes needed — this plan passes every rule under the stated assumptions.
          </p>
        )}
        {run.research ? (
          <Disclosure
            title="Compare loan rates and tenures"
            hint={
              run.research.live
                ? `From ${run.research.sources.length} live sources`
                : "Illustrative ranges, not current lender offers"
            }
          >
            <FinancingTable run={run} />
          </Disclosure>
        ) : null}
        <Link
          href={`/scenarios?run=${run.id}`}
          className="w-fit text-sm font-medium text-primary hover:underline"
        >
          Try your own what-ifs →
        </Link>
      </Section>

      {/* 6. Next step */}
      <Section
        id="next"
        title="Your next steps"
        description="Prepared by FinPulse for you to review. Nothing happens until you approve, and FinPulse never submits applications or moves money."
      >
        {plan ? (
          <ActionPlanCard plan={plan} />
        ) : (
          <p className="text-sm text-muted-foreground">
            No checklist was prepared for this analysis.
          </p>
        )}
      </Section>

      {/* How we reached this result */}
      <Disclosure
        title="How we reached this result"
        hint="Agent steps, sources, every calculation and the technical log"
      >
        <HowWeGotHere run={run} events={events.length ? events : run.events} />
      </Disclosure>
    </div>
  );
}

function FutureSection({ run }: { run: WorkflowRun }) {
  const results = run.scenarios!;
  const baseline = results.find((r) => r.isBaseline)!;
  const others = results.filter((r) => !r.isBaseline);
  const [chosen, setChosen] = useState(
    others.find((r) => r.label === "high_strain")?.params.id ?? others[0]?.params.id,
  );
  const scenario = others.find((r) => r.params.id === chosen) ?? others[0];
  const breaches = others.filter((r) => r.label === "high_strain");
  return (
    <Section
      id="future"
      title="What if things don't go to plan?"
      description="Hypothetical situations over the next 12 months, starting from the savings you'd have left. These are what-ifs, not predictions."
    >
      <p className="text-sm">
        {breaches.length ? (
          <>
            <span className="font-medium text-text-critical">
              {breaches.length} of {others.length} situations
            </span>{" "}
            would put you under serious strain — most notably{" "}
            {breaches[0]!.params.name.toLowerCase()}
            {breaches[0]!.monthExhausted !== null
              ? `, where savings run out in month ${breaches[0]!.monthExhausted}`
              : ""}
            .
          </>
        ) : (
          <>
            <span className="font-medium text-text-good">All {others.length} situations</span> stay
            within the safety rules.
          </>
        )}
      </p>
      {scenario ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Situation to compare">
            {others.map((o) => (
              <button
                key={o.params.id}
                type="button"
                role="radio"
                aria-checked={o.params.id === scenario.params.id}
                onClick={() => setChosen(o.params.id)}
                className={cn(
                  "min-h-9 rounded-full border px-3 text-xs transition",
                  o.params.id === scenario.params.id
                    ? "border-primary bg-accent font-medium text-accent-foreground"
                    : "text-muted-foreground hover:border-foreground/30",
                )}
              >
                {o.params.name}
                {o.label === "high_strain" ? " ⚠" : ""}
              </button>
            ))}
          </div>
          <h3 className="text-sm font-semibold">
            Your savings, month by month: as planned vs {scenario.params.name.toLowerCase()}
          </h3>
          <SavingsTrajectoryChart baseline={baseline} scenario={scenario} />
          <p className="text-sm text-muted-foreground">
            {scenario.monthExhausted !== null
              ? `In this situation your savings would run out in month ${scenario.monthExhausted}.`
              : `Lowest point: ${formatINR(scenario.lowestSavings)} (${months(scenario.emergencyMonths)} of spending).`}{" "}
            <AssessmentBadge label={scenario.label} />
          </p>
        </div>
      ) : null}
      <Disclosure
        title="Compare all situations"
        hint="Monthly cash left over in each, plus the full table"
      >
        <div className="flex flex-col gap-5">
          <ScenarioSurplusChart results={results} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="py-2 font-medium">Situation</th>
                  <th className="py-2 text-right font-medium">EMI</th>
                  <th className="py-2 text-right font-medium">Left each month</th>
                  <th className="py-2 text-right font-medium">Lowest savings</th>
                  <th className="py-2 pl-3 font-medium">Result</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.params.id} className="border-b last:border-0">
                    <td className="py-2.5 pr-3">
                      <div className="font-medium">{r.params.name}</div>
                      {r.changedAssumptions.length ? (
                        <div className="text-xs text-muted-foreground">
                          {r.changedAssumptions.join(" · ")}
                        </div>
                      ) : null}
                    </td>
                    <td className="tabular py-2.5 text-right">{formatINR(r.emi)}</td>
                    <td
                      className={cn(
                        "tabular py-2.5 text-right",
                        r.monthlySurplus < 0 && "text-text-critical",
                      )}
                    >
                      {formatINR(r.monthlySurplus)}
                    </td>
                    <td
                      className={cn(
                        "tabular py-2.5 text-right",
                        r.lowestSavings < 0 && "text-text-critical",
                      )}
                    >
                      {formatINR(r.lowestSavings)}
                    </td>
                    <td className="py-2.5 pl-3">
                      <AssessmentBadge label={r.label} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Disclosure>
    </Section>
  );
}

function FinancingTable({ run }: { run: WorkflowRun }) {
  const r = run.research!;
  return (
    <div className="flex flex-col gap-3">
      {!r.live ? (
        <Notice tone="warning" title="Illustrative ranges, not current lender offers">
          Live research isn&apos;t configured. These rows show how the rate and tenure change your
          cost; get written quotes before deciding.
        </Notice>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr className="border-b">
              <th className="py-2 font-medium">Option</th>
              <th className="py-2 text-right font-medium">Rate</th>
              <th className="py-2 text-right font-medium">Tenure</th>
              <th className="py-2 text-right font-medium">EMI</th>
              <th className="py-2 text-right font-medium">Total interest</th>
            </tr>
          </thead>
          <tbody>
            {[...r.options]
              .sort((x, y) => (x.totalInterest ?? 0) - (y.totalInterest ?? 0))
              .map((o) => (
                <tr key={o.id} className="border-b last:border-0">
                  <td className="py-2.5 pr-3">{o.name}</td>
                  <td className="tabular py-2.5 text-right">{o.rateUsed}%</td>
                  <td className="tabular py-2.5 text-right">{o.tenureMonths / 12} yrs</td>
                  <td className="tabular py-2.5 text-right">{formatINR(o.emi)}</td>
                  <td className="tabular py-2.5 text-right">{formatINR(o.totalInterest)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {r.notes.map((n) => (
        <p key={n} className="text-xs text-muted-foreground">
          {n}
        </p>
      ))}
    </div>
  );
}

function HowWeGotHere({ run, events }: { run: WorkflowRun; events: AgentEvent[] }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">What each agent did</h3>
        <PlanTracker events={events} running={false} showAgents />
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">Sources</h3>
        <ul className="flex flex-col gap-2 text-sm">
          {(run.research?.sources ?? []).map((s) => (
            <li key={s.id} className="flex flex-col gap-0.5">
              <span className="flex flex-wrap items-center gap-2">
                <SourceBadge kind={s.kind === "web" ? "research" : "illustrative"} />
                {s.url ? (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
                  >
                    {s.title} <ExternalLink className="size-3" />
                  </a>
                ) : (
                  <span className="font-medium">{s.title}</span>
                )}
              </span>
              <span className="text-xs text-muted-foreground">
                {s.supports} · retrieved {new Date(s.retrievedAt).toLocaleString("en-IN")}
              </span>
            </li>
          ))}
          {!run.research ? (
            <li className="text-muted-foreground">No research step ran for this analysis.</li>
          ) : null}
          {run.research?.warnings.map((w) => (
            <li key={w} className="text-xs text-text-warning">
              {w}
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">All verification findings ({run.findings.length})</h3>
        <ul className="flex flex-col gap-1.5 text-sm">
          {run.findings.map((f) => (
            <li key={f.id + f.message} className="flex gap-2">
              <span
                className={cn(
                  "w-16 shrink-0 text-xs font-medium capitalize",
                  f.severity === "critical"
                    ? "text-text-critical"
                    : f.severity === "warning"
                      ? "text-text-warning"
                      : "text-muted-foreground",
                )}
              >
                {f.severity}
              </span>
              <span className="text-pretty">{f.message}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold">
          Calculations and tool calls ({run.toolCalls.length})
        </h3>
        <ul className="flex flex-col divide-y rounded-xl border text-xs">
          {run.toolCalls.map((c) => (
            <li key={c.id} className="p-3">
              <button
                type="button"
                onClick={() => setOpen(open === c.id ? null : c.id)}
                className="flex w-full flex-wrap items-center gap-2 text-left"
                aria-expanded={open === c.id}
              >
                <code className="font-mono font-medium text-primary">{c.tool}</code>
                <span className="text-muted-foreground">{AGENT_LABELS[c.agent]}</span>
                <span
                  className={cn(
                    "rounded-full px-1.5 text-[10px]",
                    c.status === "ok" ? TONE_SOFT.good : TONE_SOFT.bad,
                  )}
                >
                  {c.status}
                </span>
                <span className="w-full text-muted-foreground sm:w-auto sm:flex-1 sm:text-right">
                  {c.outputSummary ?? c.error}
                </span>
              </button>
              {open === c.id ? (
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <pre className="max-h-64 overflow-auto rounded-lg bg-muted p-2 text-[10.5px]">
                    {JSON.stringify(c.input, null, 2)}
                  </pre>
                  <pre className="max-h-64 overflow-auto rounded-lg bg-muted p-2 text-[10.5px]">
                    {JSON.stringify(c.output ?? c.error, null, 2)}
                  </pre>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      </div>

      {run.analysis ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold">Where take-home pay goes after buying</h3>
          <IncomeAllocation
            income={run.inputs!.household.monthlyIncome}
            rows={[
              { label: "Living expenses", value: run.inputs!.household.monthlyExpenses },
              { label: "Current EMIs", value: run.inputs!.household.existingEmis },
              { label: "New EMI", value: run.analysis.emi },
              { label: "Left over", value: run.analysis.after.cashFlow.monthlySurplus },
            ]}
          />
        </div>
      ) : null}

      <Disclosure title="Technical event log" hint={`${events.length} events`}>
        <EventFeed events={events} max={200} />
      </Disclosure>
      <p className="text-xs text-muted-foreground">
        Run {run.id} · {run.mode.ai ? "AI on" : "AI off"} · research {run.mode.research} ·{" "}
        {run.limits.llmCalls}/{run.limits.maxLlmCalls} AI calls ·{" "}
        {new Date(run.createdAt).toLocaleString("en-IN")}
      </p>
    </div>
  );
}
