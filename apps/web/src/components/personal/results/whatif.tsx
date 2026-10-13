"use client";

import { FlaskConical, Loader2, Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import type { WorkflowRun } from "@/lib/personal/agents/types";
import { api } from "@/lib/personal/client";
import type { ScenarioParams, ScenarioResult } from "@/lib/personal/finance/scenarios";
import { cn } from "@/lib/utils";

import { SavingsTrajectoryChart, ScenarioSurplusChart } from "../charts";
import { MoneyInput } from "../fields";
import { Delta } from "../kit";
import { AssessmentBadge, Disclosure, Notice } from "../ui";

function outcomeLine(s: ScenarioResult): string {
  if (s.isBaseline) return "Your plan as analysed, with no shocks.";
  const what = s.changedAssumptions.join(", ").toLowerCase();
  if (s.monthExhausted !== null)
    return `With ${what}, your savings would run out in month ${s.monthExhausted}.`;
  return `With ${what}, you'd have ${formatINR(s.monthlySurplus)} left each month and your savings would bottom out at ${formatINR(s.lowestSavings)}.`;
}

function headline(s: ScenarioResult): string {
  if (s.monthExhausted !== null) return `Savings run out in month ${s.monthExhausted}`;
  return `${formatINR(s.monthlySurplus)}/month left`;
}

function Compare({
  label,
  base,
  value,
  goodWhen,
  fmt,
}: {
  label: string;
  base: number;
  value: number;
  goodWhen: "up" | "down";
  fmt: (n: number) => string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[12px] text-ink-500">{label}</span>
      <span
        className={cn(
          "tabular font-display text-[17px] font-bold whitespace-nowrap",
          value < 0 && "text-danger-text",
        )}
      >
        {fmt(value)}
      </span>
      <Delta value={value - base} format={fmt} goodWhen={goodWhen} suffix="vs plan" />
    </div>
  );
}

const SLIDERS = [
  { key: "incomeChangePct", label: "Income change", min: -60, max: 30, step: 5, unit: "%" },
  {
    key: "incomeStopMonths",
    label: "Months with no income",
    min: 0,
    max: 12,
    step: 1,
    unit: " mo",
  },
  { key: "expenseChangePct", label: "Living costs change", min: -20, max: 60, step: 5, unit: "%" },
  { key: "rateChangePp", label: "Interest rate change", min: -2, max: 5, step: 0.25, unit: " pp" },
] as const;

export function WhatIfPanel({ run }: { run: WorkflowRun }) {
  const [results, setResults] = useState<ScenarioResult[]>(run.scenarios ?? []);
  const baseline = results.find((r) => r.isBaseline)!;
  const others = results.filter((r) => !r.isBaseline);
  const [selected, setSelected] = useState<string>(
    others.find((r) => r.label === "high_strain")?.params.id ?? others[0]?.params.id ?? "baseline",
  );
  const [custom, setCustom] = useState<ScenarioParams>({
    id: "custom",
    name: "Your scenario",
    incomeChangePct: -10,
    incomeStopMonths: 0,
    expenseChangePct: 10,
    rateChangePp: 1,
    oneOffExpense: 0,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState(0);

  if (!baseline) return <Notice tone="info">No scenarios were run for this analysis.</Notice>;
  const sel = results.find((r) => r.params.id === selected) ?? others[0] ?? baseline;

  async function runCustom() {
    setBusy(true);
    setError(null);
    const n = count + 1;
    const params = {
      ...custom,
      id: `custom_${n}`,
      name: n === 1 ? "Your scenario" : `Your scenario ${n}`,
    };
    try {
      const res = await api.scenarios(run.id, [params]);
      const mine = res.results.find((r) => !r.isBaseline);
      if (!mine) throw new Error("The scenario did not return a result");
      setResults((r) => [...r, mine]);
      setSelected(mine.params.id);
      setCount(n);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't run the scenario");
    } finally {
      setBusy(false);
    }
  }

  const strained = others.filter((r) => r.label === "high_strain").length;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[14px] text-pretty text-ink-700">
        {strained ? (
          <>
            <span className="font-semibold text-danger-text">
              {strained} of {others.length} situations
            </span>{" "}
            would put you under serious strain.
          </>
        ) : (
          <>
            <span className="font-semibold text-brand-700">All {others.length} situations</span>{" "}
            stay within the safety rules.
          </>
        )}{" "}
        Each replays the next 12 months from the savings you&apos;d have left — hypothetical, not a
        prediction.
      </p>

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div
          role="radiogroup"
          aria-label="Situation"
          className="-mx-4 flex snap-x [scrollbar-width:none] gap-2 overflow-x-auto px-4 pb-1 lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0"
        >
          {[baseline, ...others].map((s) => {
            const on = s.params.id === sel.params.id;
            return (
              <button
                key={s.params.id}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => setSelected(s.params.id)}
                className={cn(
                  "flex min-w-[220px] snap-start flex-col gap-1.5 rounded-xl border p-3 text-left transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none lg:min-w-0",
                  on
                    ? "border-ink-900 bg-surface shadow-sm"
                    : "border-line bg-surface hover:border-line-strong",
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="text-[13.5px] font-semibold">{s.params.name}</span>
                  {!s.isBaseline ? <AssessmentBadge label={s.label} /> : null}
                </span>
                <span
                  className={cn(
                    "tabular text-[12.5px]",
                    s.monthExhausted !== null ? "text-danger-text" : "text-ink-500",
                  )}
                >
                  {headline(s)}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex min-w-0 flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-5">
          <div className="flex flex-col gap-1">
            <h3 className="text-[15px] font-bold">
              Your savings over 12 months
              {sel.isBaseline ? "" : `: plan vs ${sel.params.name.toLowerCase()}`}
            </h3>
            <p className="text-[13px] text-pretty text-ink-500">{outcomeLine(sel)}</p>
          </div>
          <SavingsTrajectoryChart baseline={baseline} scenario={sel} />
          <div className="grid grid-cols-2 gap-x-4 gap-y-4 border-t border-line pt-4 2xl:grid-cols-4">
            <Compare
              label="Left each month"
              base={baseline.monthlySurplus}
              value={sel.monthlySurplus}
              goodWhen="up"
              fmt={(n) => formatINR(n)}
            />
            <Compare
              label="Lowest savings"
              base={baseline.lowestSavings}
              value={sel.lowestSavings}
              goodWhen="up"
              fmt={(n) => formatINR(n)}
            />
            <Compare
              label="EMI"
              base={baseline.emi}
              value={sel.emi}
              goodWhen="down"
              fmt={(n) => formatINR(n)}
            />
            <div className="flex flex-col gap-1">
              <span className="text-[12px] text-ink-500">Months of cover</span>
              <span className="tabular font-display text-[17px] font-bold">
                {sel.emergencyMonths === null ? "—" : sel.emergencyMonths.toFixed(1)}
              </span>
              <span className="text-xs text-ink-500">at the lowest point</span>
            </div>
          </div>
        </div>
      </div>

      <section
        className="flex flex-col gap-4 rounded-2xl border border-dashed border-line-strong bg-surface p-4 sm:p-5"
        aria-labelledby="own-scenario"
      >
        <div className="flex flex-wrap items-center gap-2">
          <FlaskConical className="size-4 text-agent-500" aria-hidden />
          <h3 id="own-scenario" className="text-[15px] font-bold">
            Build your own scenario
          </h3>
          <span className="text-[12px] text-ink-500">
            Runs on the server with the same stress-test tool
          </span>
        </div>
        <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
          {SLIDERS.map((s) => {
            const v = custom[s.key];
            return (
              <label key={s.key} className="flex flex-col gap-2">
                <span className="flex items-baseline justify-between gap-2 text-[13px]">
                  <span className="font-medium">{s.label}</span>
                  <span className="tabular font-semibold text-ink-900">
                    {v > 0 && s.key !== "incomeStopMonths" ? "+" : ""}
                    {v}
                    {s.unit}
                  </span>
                </span>
                <input
                  type="range"
                  min={s.min}
                  max={s.max}
                  step={s.step}
                  value={v}
                  onChange={(e) => setCustom({ ...custom, [s.key]: Number(e.target.value) })}
                  className="h-2 w-full cursor-pointer accent-[var(--brand-600)]"
                />
              </label>
            );
          })}
          <MoneyInput
            label="Surprise expense"
            value={custom.oneOffExpense || null}
            onChange={(v) => setCustom({ ...custom, oneOffExpense: v ?? 0 })}
            placeholder="e.g. 2 lakh"
          />
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
        <Button onClick={runCustom} disabled={busy} className="w-fit">
          {busy ? <Loader2 className="animate-spin" /> : <Plus />} Run this scenario
        </Button>
      </section>

      <Disclosure
        title="Compare every situation"
        hint="Monthly money left over in each, with the full table"
      >
        <div className="flex flex-col gap-5">
          <ScenarioSurplusChart results={results} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-[13.5px]">
              <thead className="text-left text-[12px] text-ink-500">
                <tr className="border-b border-line">
                  <th className="py-2 font-medium" scope="col">
                    Situation
                  </th>
                  <th className="py-2 text-right font-medium" scope="col">
                    EMI
                  </th>
                  <th className="py-2 text-right font-medium" scope="col">
                    Left each month
                  </th>
                  <th className="py-2 text-right font-medium" scope="col">
                    Lowest savings
                  </th>
                  <th className="py-2 pl-3 font-medium" scope="col">
                    Result
                  </th>
                </tr>
              </thead>
              <tbody className="tabular">
                {results.map((r) => (
                  <tr key={r.params.id} className="border-b border-line last:border-0">
                    <th scope="row" className="py-2.5 pr-3 text-left font-normal">
                      <div className="font-medium">{r.params.name}</div>
                      {r.changedAssumptions.length ? (
                        <div className="text-[12px] text-ink-500">
                          {r.changedAssumptions.join(" · ")}
                        </div>
                      ) : null}
                    </th>
                    <td className="py-2.5 text-right">{formatINR(r.emi)}</td>
                    <td
                      className={cn(
                        "py-2.5 text-right",
                        r.monthlySurplus < 0 && "text-danger-text",
                      )}
                    >
                      {formatINR(r.monthlySurplus)}
                    </td>
                    <td
                      className={cn("py-2.5 text-right", r.lowestSavings < 0 && "text-danger-text")}
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
    </div>
  );
}
