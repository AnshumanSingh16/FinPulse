"use client";

import { ExternalLink, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { formatINR } from "@/lib/format";
import { AGENT_LABELS, type WorkflowRun } from "@/lib/personal/agents/types";
import type { ActionPlan } from "@/lib/personal/store";
import { cn } from "@/lib/utils";

import { ActionPlanCard } from "./action-plan";
import {
  AmortizationChart,
  IncomeAllocation,
  SavingsTrajectoryChart,
  ScenarioSurplusChart,
} from "./charts";
import { AssessmentBadge, ASSESSMENT, CheckBadge, Kpi, Notice, Section, SourceBadge } from "./ui";

const months = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : `${n.toFixed(1)} mo`;
const pct = (n: number | null | undefined) =>
  n === null || n === undefined ? "—" : `${(n * 100).toFixed(1)}%`;

export function RunResults({ run, plan }: { run: WorkflowRun; plan: ActionPlan | undefined }) {
  const a = run.analysis;
  const inputs = run.inputs;
  const rec = run.recommendation;
  if (!a || !inputs || !rec) return null;
  const meta = ASSESSMENT[rec.label];
  const risks = run.findings.filter(
    (f) =>
      f.severity !== "info" &&
      (f.category === "risk" || f.category === "inconsistent" || f.category === "document"),
  );

  return (
    <div className="flex flex-col gap-5">
      {/* 10. Assessment */}
      <section
        className={cn(
          "flex flex-col gap-3 rounded-xl border p-5",
          meta.className.replace(/text-\S+/, ""),
        )}
      >
        <div className="flex flex-wrap items-center gap-2">
          <AssessmentBadge label={rec.label} long />
          <span className="text-xs text-muted-foreground">
            Decision support, not a guarantee or financial advice.
          </span>
        </div>
        <h2 className="text-xl font-semibold tracking-tight text-balance">{rec.headline}</h2>
        <ul className="flex flex-col gap-1.5 text-sm text-pretty">
          {rec.summary.map((s) => (
            <li key={s} className="flex gap-2">
              <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground" />
              {s}
            </li>
          ))}
        </ul>
        {rec.narrative ? (
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-primary">
              <Sparkles className="size-3.5" /> AI explanation · every figure checked against tool
              outputs
            </div>
            {rec.narrative.text}
          </div>
        ) : null}
      </section>

      {/* 1–9. Key figures */}
      <Section
        title="The numbers"
        description={`${run.request.label} · ${inputs.purchase.annualInterestRate}% p.a. over ${inputs.purchase.tenureMonths / 12} years. All figures from FinPulse's tested calculation tools.`}
      >
        <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5">
          <Kpi label="Purchase price" value={formatINR(inputs.purchase.purchasePrice)} />
          <Kpi
            label="Down payment"
            value={formatINR(a.downPayment)}
            sub={`${inputs.purchase.downPaymentPct}% of price`}
          />
          <Kpi
            label="Additional upfront costs"
            value={formatINR(inputs.purchase.upfrontCashCosts + inputs.purchase.financedCosts)}
            sub={inputs.purchase.financedCosts ? "added to the loan" : "paid in cash"}
          />
          <Kpi label="Loan amount" value={formatINR(a.loanAmount)} />
          <Kpi label="Monthly EMI" value={formatINR(a.emi)} />
          <Kpi
            label="Total repayment"
            value={formatINR(a.totalRepayment)}
            sub="over the full tenure"
          />
          <Kpi label="Total interest" value={formatINR(a.totalInterest)} />
          <Kpi
            label="Savings after purchase"
            value={formatINR(a.postPurchaseSavings)}
            tone={a.postPurchaseSavings < 0 ? "bad" : undefined}
            sub={`was ${formatINR(inputs.household.liquidSavings)}`}
          />
          <Kpi
            label="Left each month"
            value={formatINR(a.after.cashFlow.monthlySurplus)}
            tone={a.after.cashFlow.monthlySurplus < 0 ? "bad" : undefined}
            sub={`was ${formatINR(a.before.cashFlow.monthlySurplus)}`}
          />
          <Kpi
            label="Emergency cover"
            value={months(a.after.emergencyMonths)}
            tone={
              (a.after.emergencyMonths ?? 99) < 3
                ? "bad"
                : (a.after.emergencyMonths ?? 99) < 6
                  ? "warn"
                  : "good"
            }
            sub={`was ${months(a.before.emergencyMonths)}`}
          />
        </div>
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">
              Where your take-home pay goes after the purchase
            </h3>
            <IncomeAllocation
              income={inputs.household.monthlyIncome}
              rows={[
                { label: "Living expenses", value: inputs.household.monthlyExpenses },
                { label: "Existing EMIs", value: inputs.household.existingEmis },
                { label: "New EMI", value: a.emi },
                ...(inputs.purchase.monthlyOwnershipCost
                  ? [{ label: "Ownership costs", value: inputs.purchase.monthlyOwnershipCost }]
                  : []),
                ...(inputs.household.otherMonthlyObligations
                  ? [
                      {
                        label: "Other obligations",
                        value: inputs.household.otherMonthlyObligations,
                      },
                    ]
                  : []),
                { label: "Left over", value: a.after.cashFlow.monthlySurplus },
              ]}
            />
          </div>
          {a.yearly.length ? (
            <div className="flex flex-col gap-2">
              <h3 className="text-sm font-medium">Principal vs interest, by loan year</h3>
              <AmortizationChart yearly={a.yearly} />
            </div>
          ) : null}
        </div>
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Affordability rules</h3>
          <div className="overflow-x-auto rounded-lg border">
            <table className="w-full text-xs">
              <thead className="bg-muted/60 text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Rule</th>
                  <th className="px-3 py-2 text-right font-medium">Value</th>
                  <th className="px-3 py-2 text-left font-medium">Threshold</th>
                  <th className="px-3 py-2 text-left font-medium">Result</th>
                </tr>
              </thead>
              <tbody>
                {a.checks.map((c) => (
                  <tr key={c.id} className="border-t align-top">
                    <td className="px-3 py-2">
                      <div className="font-medium">{c.label}</div>
                      <div className="mt-0.5 max-w-md text-pretty text-muted-foreground">
                        {c.explanation}
                      </div>
                    </td>
                    <td className="tabular px-3 py-2 text-right">
                      {c.value === null
                        ? "—"
                        : c.id === "debt_to_income" || c.id === "surplus_buffer"
                          ? pct(c.value)
                          : c.id === "emergency_cover"
                            ? months(c.value)
                            : formatINR(c.value)}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{c.displayThreshold}</td>
                    <td className="px-3 py-2">
                      <CheckBadge status={c.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-muted-foreground">
            These thresholds are configurable heuristics, not universal rules or a lender&apos;s
            criteria.
          </p>
        </div>
      </Section>

      {/* 11. Scenarios */}
      {run.scenarios ? <ScenarioSection run={run} /> : null}

      {/* 12. Risks */}
      <Section title="Key risks" description="Raised by the Risk and Verification agents.">
        {risks.length ? (
          <ul className="flex flex-col gap-2">
            {risks.map((f) => (
              <li key={f.id + f.message}>
                <Notice tone={f.severity === "critical" ? "error" : "warning"} title={f.message}>
                  {f.suggestion ? f.suggestion : null}
                  <span className="mt-1 block text-[11px]">{AGENT_LABELS[f.agent]} agent</span>
                </Notice>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No significant risks were flagged under the stated assumptions.
          </p>
        )}
      </Section>

      {/* 13. Alternatives */}
      <Section
        title="Alternatives"
        description="Computed with the same tools, so you can compare like for like."
      >
        <div className="grid gap-3 md:grid-cols-3">
          {rec.alternatives.map((alt) => (
            <div
              key={alt.id}
              className="flex flex-col gap-2 rounded-lg border bg-background/40 p-4"
            >
              <div className="font-medium text-pretty">{alt.title}</div>
              <p className="text-xs text-pretty text-muted-foreground">{alt.description}</p>
              <dl className="mt-auto grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5 text-xs">
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
            </div>
          ))}
          {rec.alternatives.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No alternatives needed: the plan is comfortable under the stated assumptions.
            </p>
          ) : null}
        </div>
        {run.research ? <FinancingTable run={run} /> : null}
      </Section>

      {/* 14. Next steps */}
      <Section
        title="Recommended next steps"
        description="Prepared by the Action Agent. Review and approve or reject — the decision is enforced on the server."
        actions={
          <Link href="/actions" className="text-xs text-primary hover:underline">
            Open Action Center
          </Link>
        }
      >
        {plan ? (
          <ActionPlanCard plan={plan} />
        ) : (
          <p className="text-sm text-muted-foreground">
            No action plan was prepared for this analysis.
          </p>
        )}
      </Section>

      {/* 15. Evidence */}
      <EvidencePanel run={run} />
    </div>
  );
}

function ScenarioSection({ run }: { run: WorkflowRun }) {
  const results = run.scenarios!;
  const baseline = results.find((r) => r.isBaseline)!;
  const others = results.filter((r) => !r.isBaseline);
  const [chosen, setChosen] = useState(
    others.find((r) => r.label === "high_strain")?.params.id ?? others[0]?.params.id,
  );
  const scenario = others.find((r) => r.params.id === chosen) ?? others[0];
  return (
    <Section
      title="Stress scenarios"
      description="Hypothetical what-ifs over the next 12 months, starting from the savings left after the purchase. Not predictions."
      actions={
        <Link href={`/scenarios?run=${run.id}`} className="text-xs text-primary hover:underline">
          Adjust & re-run
        </Link>
      }
    >
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[640px] text-xs">
          <thead className="bg-muted/60 text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Scenario</th>
              <th className="px-3 py-2 text-right font-medium">EMI</th>
              <th className="px-3 py-2 text-right font-medium">Monthly surplus</th>
              <th className="px-3 py-2 text-right font-medium">vs baseline</th>
              <th className="px-3 py-2 text-right font-medium">Lowest savings</th>
              <th className="px-3 py-2 text-right font-medium">Cover</th>
              <th className="px-3 py-2 text-left font-medium">Assessment</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.params.id} className={cn("border-t", r.isBaseline && "bg-muted/30")}>
                <td className="px-3 py-2">
                  <div className="font-medium">{r.params.name}</div>
                  {r.changedAssumptions.length ? (
                    <div className="text-muted-foreground">{r.changedAssumptions.join(" · ")}</div>
                  ) : null}
                  {r.monthExhausted !== null ? (
                    <div className="text-chart-negative">
                      Savings run out in month {r.monthExhausted}
                    </div>
                  ) : null}
                </td>
                <td className="tabular px-3 py-2 text-right">{formatINR(r.emi)}</td>
                <td
                  className={cn(
                    "tabular px-3 py-2 text-right",
                    r.monthlySurplus < 0 && "text-chart-negative",
                  )}
                >
                  {formatINR(r.monthlySurplus)}
                </td>
                <td className="tabular px-3 py-2 text-right text-muted-foreground">
                  {r.isBaseline ? "—" : formatINR(r.delta.monthlySurplus, { signed: true })}
                </td>
                <td
                  className={cn(
                    "tabular px-3 py-2 text-right",
                    r.lowestSavings < 0 && "text-chart-negative",
                  )}
                >
                  {formatINR(r.lowestSavings)}
                </td>
                <td className="tabular px-3 py-2 text-right">{months(r.emergencyMonths)}</td>
                <td className="px-3 py-2">
                  <AssessmentBadge label={r.label} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Monthly surplus by scenario</h3>
          <ScenarioSurplusChart results={results} />
        </div>
        {scenario ? (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-medium">Liquid savings over 12 months</h3>
              <select
                value={scenario.params.id}
                onChange={(e) => setChosen(e.target.value)}
                className="h-8 rounded-md border bg-background px-2 text-xs"
                aria-label="Scenario to compare"
              >
                {others.map((o) => (
                  <option key={o.params.id} value={o.params.id}>
                    {o.params.name}
                  </option>
                ))}
              </select>
            </div>
            <SavingsTrajectoryChart baseline={baseline} scenario={scenario} />
          </div>
        ) : null}
      </div>
    </Section>
  );
}

function FinancingTable({ run }: { run: WorkflowRun }) {
  const r = run.research!;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium">Financing options</h3>
        <SourceBadge kind={r.live ? "research" : "illustrative"} />
        <span className="text-xs text-muted-foreground">{r.provider}</span>
      </div>
      {!r.live ? (
        <Notice tone="warning" title="Illustrative ranges, not current lender offers">
          Live research is not configured. These rows show how rate and tenure change the cost; get
          written quotes before deciding.
        </Notice>
      ) : null}
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[560px] text-xs">
          <thead className="bg-muted/60 text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Option</th>
              <th className="px-3 py-2 text-right font-medium">Rate used</th>
              <th className="px-3 py-2 text-right font-medium">Tenure</th>
              <th className="px-3 py-2 text-right font-medium">EMI</th>
              <th className="px-3 py-2 text-right font-medium">Total interest</th>
            </tr>
          </thead>
          <tbody>
            {[...r.options]
              .sort((x, y) => (x.totalInterest ?? 0) - (y.totalInterest ?? 0))
              .map((o) => (
                <tr key={o.id} className="border-t">
                  <td className="px-3 py-2">
                    {o.name}
                    {o.feesNote ? <div className="text-muted-foreground">{o.feesNote}</div> : null}
                  </td>
                  <td className="tabular px-3 py-2 text-right">{o.rateUsed}%</td>
                  <td className="tabular px-3 py-2 text-right">{o.tenureMonths / 12} yrs</td>
                  <td className="tabular px-3 py-2 text-right">{formatINR(o.emi)}</td>
                  <td className="tabular px-3 py-2 text-right">{formatINR(o.totalInterest)}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      {r.notes.map((n) => (
        <p key={n} className="text-[11px] text-muted-foreground">
          {n}
        </p>
      ))}
    </div>
  );
}

export function EvidencePanel({ run }: { run: WorkflowRun }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Section
      title="Evidence & assumptions"
      description="Everything this recommendation rests on: inputs, assumptions, sources, verification findings, and every tool call the agents made."
    >
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium">Inputs and assumptions</h3>
          <ul className="flex flex-col divide-y rounded-lg border text-xs">
            {run.assumptions.map((as) => (
              <li key={as.id} className="flex flex-col gap-1 p-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{as.field}</span>
                  <span className="flex items-center gap-2">
                    <span className="tabular">{as.value}</span>
                    <SourceBadge kind={as.basis === "user" ? "user" : as.basis} />
                  </span>
                </div>
                <span className="text-pretty text-muted-foreground">{as.note}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">Sources</h3>
            <ul className="flex flex-col gap-2 text-xs">
              {(run.research?.sources ?? []).map((s) => (
                <li key={s.id} className="rounded-lg border p-2.5">
                  <div className="flex flex-wrap items-center gap-2">
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
                  </div>
                  <div className="mt-1 text-muted-foreground">{s.supports}</div>
                  <div className="mt-0.5 text-[10px] text-muted-foreground">
                    Retrieved {new Date(s.retrievedAt).toLocaleString("en-IN")}
                  </div>
                </li>
              ))}
              {!run.research ? (
                <li className="text-muted-foreground">No research step ran for this analysis.</li>
              ) : null}
              {run.research?.warnings.map((w) => (
                <li key={w} className="text-status-warning">
                  {w}
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-medium">All verification findings</h3>
            <ul className="flex flex-col gap-1 text-xs">
              {run.findings.map((f) => (
                <li key={f.id + f.message} className="flex gap-2">
                  <span
                    className={cn(
                      "shrink-0 font-medium uppercase",
                      f.severity === "critical"
                        ? "text-chart-negative"
                        : f.severity === "warning"
                          ? "text-status-warning"
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
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">Tool calls ({run.toolCalls.length})</h3>
        <ul className="flex flex-col divide-y rounded-lg border text-xs">
          {run.toolCalls.map((c) => (
            <li key={c.id} className="p-2.5">
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
                    "rounded px-1.5 text-[10px] uppercase",
                    c.status === "ok"
                      ? "bg-status-good/10 text-text-good"
                      : "bg-status-critical/10 text-chart-negative",
                  )}
                >
                  {c.status}
                </span>
                <span className="tabular text-muted-foreground">{c.durationMs} ms</span>
                <span className="w-full text-muted-foreground sm:w-auto sm:flex-1 sm:text-right">
                  {c.outputSummary ?? c.error}
                </span>
              </button>
              {open === c.id ? (
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <pre className="max-h-64 overflow-auto rounded bg-background p-2 text-[10.5px]">
                    {JSON.stringify(c.input, null, 2)}
                  </pre>
                  <pre className="max-h-64 overflow-auto rounded bg-background p-2 text-[10.5px]">
                    {JSON.stringify(c.output ?? c.error, null, 2)}
                  </pre>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
        <p className="text-[11px] text-muted-foreground">
          Run {run.id} · {run.mode.ai ? "AI enabled" : "AI not configured"} · research{" "}
          {run.mode.research} · {run.limits.llmCalls}/{run.limits.maxLlmCalls} model calls · started{" "}
          {new Date(run.createdAt).toLocaleString("en-IN")}
        </p>
      </div>
    </Section>
  );
}
