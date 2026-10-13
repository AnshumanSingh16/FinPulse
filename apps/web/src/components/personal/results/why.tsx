"use client";

import { ExternalLink, Pencil } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { AGENT_LABELS, type Finding, type WorkflowRun } from "@/lib/personal/agents/types";
import { DEFAULT_RULES, type RuleCheck } from "@/lib/personal/finance/affordability";
import { cn } from "@/lib/utils";

import { EventFeed } from "../agent-activity";
import { Meter } from "../kit";
import { CheckBadge, Disclosure, Notice, SourceBadge, TONE_SOFT } from "../ui";

const R = DEFAULT_RULES;
const pct = (n: number) => `${Math.round(n * 100)}%`;

function valueText(c: RuleCheck): string {
  if (c.value === null) return "—";
  if (c.id === "debt_to_income" || c.id === "surplus_buffer")
    return `${(c.value * 100).toFixed(1)}%`;
  if (c.id === "emergency_cover") return `${c.value.toFixed(1)} months`;
  return formatINR(c.value);
}

function FactorMeter({ c }: { c: RuleCheck }) {
  if (c.value === null) return null;
  if (c.id === "debt_to_income")
    return (
      <Meter
        label={c.label}
        value={c.value}
        max={0.8}
        valueText={valueText(c)}
        zones={[
          { to: R.dtiComfortableMax, tone: "good" },
          { to: R.dtiStretchMax, tone: "warn" },
          { to: 0.8, tone: "bad" },
        ]}
        markers={[
          { at: R.dtiComfortableMax, label: pct(R.dtiComfortableMax) },
          { at: R.dtiStretchMax, label: pct(R.dtiStretchMax) },
        ]}
      />
    );
  if (c.id === "emergency_cover")
    return (
      <Meter
        label={c.label}
        value={c.value}
        max={12}
        valueText={valueText(c)}
        zones={[
          { to: R.emergencyMinimumMonths, tone: "bad" },
          { to: R.emergencyComfortableMonths, tone: "warn" },
          { to: 12, tone: "good" },
        ]}
        markers={[
          { at: R.emergencyMinimumMonths, label: `${R.emergencyMinimumMonths} mo` },
          { at: R.emergencyComfortableMonths, label: `${R.emergencyComfortableMonths} mo` },
        ]}
      />
    );
  if (c.id === "surplus_buffer")
    return (
      <Meter
        label={c.label}
        value={Math.max(0, c.value)}
        max={0.6}
        valueText={valueText(c)}
        zones={[
          { to: R.surplusComfortableShare, tone: "warn" },
          { to: 0.6, tone: "good" },
        ]}
        markers={[{ at: R.surplusComfortableShare, label: pct(R.surplusComfortableShare) }]}
      />
    );
  return null;
}

const CATEGORY: Record<Finding["category"], string> = {
  risk: "Risks",
  missing: "Missing information",
  inconsistent: "Inconsistencies",
  document: "Document mismatches",
  assumption: "Assumptions",
  plan: "Your other goals",
};

export function WhyPanel({ run, onEdit }: { run: WorkflowRun; onEdit?: () => void }) {
  const a = run.analysis!;
  const issues = run.findings.filter((f) => f.severity !== "info" && f.category !== "assumption");
  const groups = (["risk", "missing", "inconsistent", "document"] as const)
    .map((k) => ({ k, items: issues.filter((f) => f.category === k) }))
    .filter((g) => g.items.length);
  const notes = run.findings.filter((f) => f.severity === "info");
  const r = run.research;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section
        className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-5 shadow-xs lg:col-span-2"
        aria-labelledby="factors"
      >
        <header className="flex flex-col gap-1">
          <h3 id="factors" className="text-[15px] font-bold">
            What decided this
          </h3>
          <p className="text-[13px] text-pretty text-ink-500">
            Five explicit rules applied to your numbers. The verdict is the worst result among them.
            Thresholds are FinPulse&apos;s guides, not a lender&apos;s criteria.
          </p>
        </header>
        <ul className="grid gap-x-8 gap-y-5 md:grid-cols-2">
          {a.checks.map((c) => (
            <li key={c.id} className="flex flex-col gap-2">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 flex-col">
                  <span className="text-[14px] font-semibold">{c.label}</span>
                  <span className="text-[12px] text-ink-500">Guide: {c.displayThreshold}</span>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="tabular font-display text-[15px] font-bold">{valueText(c)}</span>
                  <CheckBadge status={c.status} />
                </div>
              </div>
              <FactorMeter c={c} />
            </li>
          ))}
        </ul>
        <Disclosure title="How each rule works" hint="And its limitations">
          <ul className="flex flex-col gap-3 text-[13px] leading-relaxed text-ink-700">
            {a.checks.map((c) => (
              <li key={c.id}>
                <span className="font-semibold text-ink-900">{c.label}.</span> {c.explanation}
              </li>
            ))}
          </ul>
        </Disclosure>
      </section>

      <section
        className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-5 shadow-xs"
        aria-labelledby="risks"
      >
        <h3 id="risks" className="text-[15px] font-bold">
          Risks and missing information
        </h3>
        {groups.length ? (
          groups.map((g) => (
            <div key={g.k} className="flex flex-col gap-2">
              <span className="text-[12px] font-semibold tracking-wide text-ink-500 uppercase">
                {CATEGORY[g.k]}
              </span>
              {g.items.map((f) => (
                <Notice
                  key={f.id + f.message}
                  tone={f.severity === "critical" ? "error" : "warning"}
                  title={f.message}
                >
                  {f.suggestion ? <span className="block">{f.suggestion}</span> : null}
                  <span className="mt-1 block text-[11px]">
                    Raised by the {AGENT_LABELS[f.agent]} agent
                  </span>
                </Notice>
              ))}
            </div>
          ))
        ) : (
          <p className="text-[14px] text-ink-500">
            No significant risks were raised under these assumptions.
          </p>
        )}
        {notes.length ? (
          <Disclosure title={`${notes.length} other note${notes.length === 1 ? "" : "s"}`}>
            <ul className="flex flex-col gap-2 text-[13px] text-ink-700">
              {notes.map((f) => (
                <li key={f.id + f.message}>{f.message}</li>
              ))}
            </ul>
          </Disclosure>
        ) : null}
      </section>

      <section
        className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-5 shadow-xs"
        aria-labelledby="assumptions"
      >
        <div className="flex items-center justify-between gap-2">
          <h3 id="assumptions" className="text-[15px] font-bold">
            Assumptions used
          </h3>
          {onEdit ? (
            <Button variant="ghost" size="sm" onClick={onEdit}>
              <Pencil /> Change
            </Button>
          ) : null}
        </div>
        <ul className="flex flex-col divide-y divide-line">
          {run.assumptions.map((as) => (
            <li key={as.id} className="flex flex-col gap-1 py-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2 text-[14px]">
                <span className="font-medium">{as.field}</span>
                <span className="flex items-center gap-2">
                  <span className="tabular">{as.value}</span>
                  <SourceBadge kind={as.basis === "user" ? "user" : as.basis} />
                </span>
              </div>
              <span className="text-[12.5px] text-pretty text-ink-500">{as.note}</span>
            </li>
          ))}
        </ul>
      </section>

      <section
        className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-5 shadow-xs lg:col-span-2"
        aria-labelledby="sources"
      >
        <h3 id="sources" className="text-[15px] font-bold">
          Where the data came from
        </h3>
        {!r ? (
          <p className="text-[14px] text-ink-500">
            No research step ran for this analysis; it used the rate you entered.
          </p>
        ) : (
          <>
            {!r.live ? (
              <Notice tone="warning" title="No external data was retrieved">
                Live research isn&apos;t configured, so financing rates are clearly labelled
                illustrative ranges — not current lender offers. Get written quotes before deciding.
              </Notice>
            ) : null}
            <ul className="flex flex-col gap-2.5">
              {r.sources.map((s) => (
                <li key={s.id} className="flex flex-col gap-0.5 text-[13.5px]">
                  <span className="flex flex-wrap items-center gap-2">
                    <SourceBadge kind={s.kind === "web" ? "research" : "illustrative"} />
                    {s.url ? (
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline"
                      >
                        {s.title} <ExternalLink className="size-3" aria-hidden />
                      </a>
                    ) : (
                      <span className="font-semibold">{s.title}</span>
                    )}
                  </span>
                  <span className="text-[12.5px] text-ink-500">
                    {s.supports} · retrieved {new Date(s.retrievedAt).toLocaleString("en-IN")}
                  </span>
                </li>
              ))}
            </ul>
            {r.warnings.map((w) => (
              <p key={w} className="text-[12.5px] text-caution-text">
                {w}
              </p>
            ))}
            <Disclosure
              title="Compare loan rates and tenures"
              hint={`${r.options.length} options, EMI and total interest for each`}
            >
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-[13.5px]">
                  <thead className="text-left text-[12px] text-ink-500">
                    <tr className="border-b border-line">
                      <th className="py-2 font-medium" scope="col">
                        Option
                      </th>
                      <th className="py-2 text-right font-medium" scope="col">
                        Rate
                      </th>
                      <th className="py-2 text-right font-medium" scope="col">
                        Tenure
                      </th>
                      <th className="py-2 text-right font-medium" scope="col">
                        EMI
                      </th>
                      <th className="py-2 text-right font-medium" scope="col">
                        Total interest
                      </th>
                    </tr>
                  </thead>
                  <tbody className="tabular">
                    {[...r.options]
                      .sort((x, y) => (x.totalInterest ?? 0) - (y.totalInterest ?? 0))
                      .map((o) => (
                        <tr key={o.id} className="border-b border-line last:border-0">
                          <th scope="row" className="py-2.5 pr-3 text-left font-normal">
                            {o.name}
                          </th>
                          <td className="py-2.5 text-right">{o.rateUsed}%</td>
                          <td className="py-2.5 text-right">{o.tenureMonths / 12} yrs</td>
                          <td className="py-2.5 text-right">{formatINR(o.emi)}</td>
                          <td className="py-2.5 text-right">{formatINR(o.totalInterest)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </Disclosure>
          </>
        )}
      </section>

      <div className="lg:col-span-2">
        <TechnicalDetail run={run} />
      </div>
    </div>
  );
}

function TechnicalDetail({ run }: { run: WorkflowRun }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Disclosure
      title="Technical detail"
      hint={`${run.toolCalls.length} tool calls with inputs and outputs, plus the raw event log`}
    >
      <div className="flex flex-col gap-4">
        <ul className="flex flex-col divide-y divide-line rounded-xl border border-line text-[12px]">
          {run.toolCalls.map((c) => (
            <li key={c.id} className="p-3">
              <button
                type="button"
                onClick={() => setOpen(open === c.id ? null : c.id)}
                className="flex w-full flex-wrap items-center gap-2 text-left"
                aria-expanded={open === c.id}
              >
                <code className="font-mono font-semibold text-agent-700">{c.tool}</code>
                <span className="text-ink-500">{AGENT_LABELS[c.agent]}</span>
                <span
                  className={cn(
                    "rounded-full px-1.5 text-[10px] font-medium",
                    c.status === "ok" ? TONE_SOFT.good : TONE_SOFT.bad,
                  )}
                >
                  {c.status}
                </span>
                <span className="tabular text-ink-400">{c.durationMs} ms</span>
                <span className="w-full text-ink-500 sm:w-auto sm:flex-1 sm:text-right">
                  {c.outputSummary ?? c.error}
                </span>
              </button>
              {open === c.id ? (
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  <pre className="max-h-64 overflow-auto rounded-lg bg-surface-sunken p-2 text-[10.5px]">
                    {JSON.stringify(c.input, null, 2)}
                  </pre>
                  <pre className="max-h-64 overflow-auto rounded-lg bg-surface-sunken p-2 text-[10.5px]">
                    {JSON.stringify(c.output ?? c.error, null, 2)}
                  </pre>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
        <EventFeed events={run.events} max={300} />
        <p className="text-[12px] text-ink-500">
          Run {run.id} · {run.mode.ai ? "AI on" : "AI off"} · research {run.mode.research} ·{" "}
          {run.limits.llmCalls}/{run.limits.maxLlmCalls} AI calls ·{" "}
          {new Date(run.createdAt).toLocaleString("en-IN")}
        </p>
      </div>
    </Disclosure>
  );
}
