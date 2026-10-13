"use client";

import { FlaskConical, Loader2, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/personal/client";
import {
  STANDARD_SCENARIOS,
  type ScenarioParams,
  type ScenarioResult,
} from "@/lib/personal/finance/scenarios";
import { cn } from "@/lib/utils";

import { SavingsTrajectoryChart, ScenarioSurplusChart } from "./charts";
import { MoneyInput, NumberInput } from "./fields";
import { usePersonal } from "./provider";
import { Delta } from "./kit";
import {
  AssessmentBadge,
  Disclosure,
  EmptyState,
  Loading,
  Notice,
  PageTitle,
  inputClass,
} from "./ui";

let counter = 0;
const blank = (): ScenarioParams => ({
  id: `custom_${++counter}`,
  name: "Custom scenario",
  incomeChangePct: 0,
  incomeStopMonths: 0,
  expenseChangePct: 0,
  rateChangePp: 0,
  oneOffExpense: 0,
});

export function ScenarioLab() {
  const { state } = usePersonal();
  const params = useSearchParams();
  const completed = state?.runs.filter((r) => r.status === "completed") ?? [];
  const [runId, setRunId] = useState<string | null>(params.get("run"));
  const [scenarios, setScenarios] = useState<ScenarioParams[]>(STANDARD_SCENARIOS.slice(0, 4));
  const [overrides, setOverrides] = useState<{
    annualInterestRate: number | null;
    tenureMonths: number | null;
    downPaymentPct: number | null;
  }>({ annualInterestRate: null, tenureMonths: null, downPaymentPct: null });
  const [results, setResults] = useState<ScenarioResult[] | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ranWith, setRanWith] = useState<string | null>(null);

  if (!state) return <Loading />;
  const selected = completed.find((r) => r.id === runId) ?? completed[0];

  async function run() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const o = Object.fromEntries(
        Object.entries(overrides).filter(([, v]) => v !== null),
      ) as Record<string, number>;
      const res = await api.scenarios(selected.id, scenarios, o);
      setResults(res.results);
      setRanWith(JSON.stringify({ id: selected.id, scenarios, overrides }));
      setFocus(
        res.results.find((r) => !r.isBaseline && r.label === "high_strain")?.params.id ??
          res.results[1]?.params.id ??
          null,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scenario run failed");
    } finally {
      setBusy(false);
    }
  }

  const patch = (i: number, p: Partial<ScenarioParams>) =>
    setScenarios((s) => s.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const baseline = results?.find((r) => r.isBaseline);
  const focused = results?.find((r) => r.params.id === focus);

  const stale =
    results !== null && ranWith !== JSON.stringify({ id: selected?.id, scenarios, overrides });
  const strained = results?.filter((r) => !r.isBaseline && r.label === "high_strain").length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <PageTitle
        eyebrow="Stress-test a plan"
        title="What-if scenarios"
        description="Change the assumptions and stress events, then re-run the Risk Agent's 12-month simulation on the server. These are hypothetical scenarios, not predictions."
      />

      {!selected ? (
        <EmptyState
          icon={FlaskConical}
          title="No completed analysis yet"
          action={
            <Link
              href="/afford"
              className="text-[14px] font-semibold text-brand-700 hover:underline"
            >
              Run an affordability analysis →
            </Link>
          }
        >
          Scenarios replay a finished analysis under different conditions.
        </EmptyState>
      ) : (
        <>
          <section className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-6">
            <div className="flex flex-col gap-1">
              <h2 className="text-[16px] font-bold">Starting point</h2>
              <p className="text-[13px] text-ink-500">
                Leave an override empty to keep the value used in the analysis.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="run" className="text-[13px] font-medium text-ink-700">
                  Analysis
                </label>
                <select
                  id="run"
                  className={inputClass}
                  value={selected.id}
                  onChange={(e) => {
                    setRunId(e.target.value);
                    setResults(null);
                  }}
                >
                  {completed.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.label} ·{" "}
                      {new Date(r.createdAt).toLocaleTimeString("en-IN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </option>
                  ))}
                </select>
              </div>
              <NumberInput
                label="Interest rate"
                suffix="% p.a."
                min={0}
                max={50}
                step={0.05}
                value={overrides.annualInterestRate}
                onChange={(v) => setOverrides({ ...overrides, annualInterestRate: v })}
                placeholder="as analysed"
              />
              <NumberInput
                label="Loan tenure"
                suffix="years"
                min={1}
                max={50}
                value={overrides.tenureMonths === null ? null : overrides.tenureMonths / 12}
                onChange={(v) =>
                  setOverrides({
                    ...overrides,
                    tenureMonths: v === null ? null : Math.round(v * 12),
                  })
                }
                placeholder="as analysed"
              />
              <NumberInput
                label="Down payment"
                suffix="%"
                min={0}
                max={100}
                value={overrides.downPaymentPct}
                onChange={(v) => setOverrides({ ...overrides, downPaymentPct: v })}
                placeholder="as analysed"
              />
            </div>
          </section>

          <section className="flex flex-col gap-4" aria-labelledby="events">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="flex flex-col gap-1">
                <h2 id="events" className="text-[16px] font-bold">
                  Stress events{" "}
                  <span className="tabular font-medium text-ink-400">{scenarios.length}/8</span>
                </h2>
                <p className="text-[13px] text-ink-500">
                  Each card is one scenario. Combine changes in a card to model events happening
                  together.
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setScenarios(STANDARD_SCENARIOS)}
                >
                  Use all presets
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={scenarios.length >= 8}
                  onClick={() => setScenarios([...scenarios, blank()])}
                >
                  <Plus /> Add scenario
                </Button>
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {scenarios.map((s, i) => (
                <div
                  key={s.id}
                  className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-xs"
                >
                  <div className="flex items-center gap-2">
                    <label className="sr-only" htmlFor={`n${s.id}`}>
                      Scenario name
                    </label>
                    <input
                      id={`n${s.id}`}
                      className="-ml-2 h-9 min-w-0 flex-1 rounded-lg border border-transparent bg-transparent px-2 text-[15px] font-semibold text-ink-900 hover:border-line focus:border-brand-600 focus:outline-none"
                      value={s.name}
                      maxLength={80}
                      onChange={(e) => patch(i, { name: e.target.value || "Scenario" })}
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove ${s.name}`}
                      disabled={scenarios.length <= 1}
                      onClick={() => setScenarios(scenarios.filter((_, j) => j !== i))}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    <NumberInput
                      label="Income change"
                      suffix="%"
                      min={-100}
                      max={200}
                      value={s.incomeChangePct}
                      onChange={(v) => patch(i, { incomeChangePct: v ?? 0 })}
                    />
                    <NumberInput
                      label="No income for"
                      suffix="mo"
                      min={0}
                      max={36}
                      step={1}
                      value={s.incomeStopMonths}
                      onChange={(v) => patch(i, { incomeStopMonths: Math.round(v ?? 0) })}
                    />
                    <NumberInput
                      label="Living costs"
                      suffix="%"
                      min={-90}
                      max={300}
                      value={s.expenseChangePct}
                      onChange={(v) => patch(i, { expenseChangePct: v ?? 0 })}
                    />
                    <NumberInput
                      label="Rate change"
                      suffix="pp"
                      min={-10}
                      max={20}
                      step={0.25}
                      value={s.rateChangePp}
                      onChange={(v) => patch(i, { rateChangePp: v ?? 0 })}
                    />
                    <div className="col-span-2">
                      <MoneyInput
                        label="One-off expense"
                        value={s.oneOffExpense || null}
                        onChange={(v) => patch(i, { oneOffExpense: v ?? 0 })}
                        placeholder="0"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {error ? <Notice tone="error">{error}</Notice> : null}
            <div className="z-10 flex flex-wrap items-center gap-3 lg:sticky lg:bottom-4">
              <Button onClick={run} disabled={busy} size="lg" className="shadow-md">
                {busy ? <Loader2 className="animate-spin" /> : <FlaskConical />}{" "}
                {results ? "Re-run scenarios" : "Run scenarios"}
              </Button>
              {stale ? (
                <span className="rounded-full bg-caution-50 px-3 py-1 text-[12.5px] font-medium text-caution-text">
                  Inputs changed — results below are out of date
                </span>
              ) : null}
            </div>
          </section>

          {results && baseline ? (
            <section
              className={cn(
                "flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs transition-opacity sm:p-6",
                stale && "opacity-60",
              )}
              aria-labelledby="results"
              aria-live="polite"
            >
              <div className="flex flex-col gap-1">
                <h2 id="results" className="text-[16px] font-bold">
                  Results
                </h2>
                <p className="text-[13.5px] text-pretty text-ink-700">
                  {strained ? (
                    <span className="font-semibold text-danger-text">
                      {strained} of {results.length - 1} scenarios put you under serious strain.
                    </span>
                  ) : (
                    <span className="font-semibold text-brand-700">
                      Every scenario stays within the safety rules.
                    </span>
                  )}{" "}
                  Against “{selected.label}”, replaying 12 months from the savings left after
                  buying.
                </p>
              </div>

              <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
                <div
                  role="radiogroup"
                  aria-label="Scenario to compare"
                  className="flex flex-col gap-2"
                >
                  {results.map((r) => {
                    const on = focus === r.params.id;
                    return (
                      <button
                        key={r.params.id}
                        type="button"
                        role="radio"
                        aria-checked={on}
                        disabled={r.isBaseline}
                        onClick={() => setFocus(r.params.id)}
                        className={cn(
                          "flex flex-col gap-1 rounded-xl border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                          on ? "border-ink-900 shadow-sm" : "border-line hover:border-line-strong",
                          r.isBaseline && "cursor-default bg-surface-sunken/60",
                        )}
                      >
                        <span className="flex items-center justify-between gap-2">
                          <span className="text-[13.5px] font-semibold">{r.params.name}</span>
                          <AssessmentBadge label={r.label} />
                        </span>
                        <span className="text-[12px] text-ink-500">
                          {r.isBaseline
                            ? "Assumptions as analysed"
                            : r.changedAssumptions.join(" · ") || "No changes"}
                        </span>
                        <span
                          className={cn(
                            "tabular text-[12.5px]",
                            r.monthExhausted !== null
                              ? "font-medium text-danger-text"
                              : "text-ink-700",
                          )}
                        >
                          {r.monthExhausted !== null
                            ? `Savings run out in month ${r.monthExhausted}`
                            : `${formatINR(r.monthlySurplus)}/month left`}
                        </span>
                      </button>
                    );
                  })}
                </div>

                <div className="flex min-w-0 flex-col gap-4">
                  {focused ? (
                    <>
                      <h3 className="text-[14px] font-semibold">
                        Savings over 12 months: plan vs {focused.params.name.toLowerCase()}
                      </h3>
                      <SavingsTrajectoryChart baseline={baseline} scenario={focused} />
                      <div className="grid grid-cols-2 gap-4 border-t border-line pt-4 sm:grid-cols-4">
                        {(
                          [
                            [
                              "Left each month",
                              baseline.monthlySurplus,
                              focused.monthlySurplus,
                              "up",
                            ],
                            ["Lowest savings", baseline.lowestSavings, focused.lowestSavings, "up"],
                            [
                              "After 12 months",
                              baseline.savingsAfterHorizon,
                              focused.savingsAfterHorizon,
                              "up",
                            ],
                            ["EMI", baseline.emi, focused.emi, "down"],
                          ] as const
                        ).map(([label, b, v, good]) => (
                          <div key={label} className="flex flex-col gap-1">
                            <span className="text-[12px] text-ink-500">{label}</span>
                            <span
                              className={cn(
                                "tabular font-display text-[17px] font-bold whitespace-nowrap",
                                v < 0 && "text-danger-text",
                              )}
                            >
                              {formatINR(v)}
                            </span>
                            <Delta
                              value={v - b}
                              format={(n) => formatINR(n)}
                              goodWhen={good}
                              suffix="vs plan"
                            />
                          </div>
                        ))}
                      </div>
                      {focused.breaches.length ? (
                        <p className="rounded-xl bg-caution-50 px-3 py-2 text-[13px] text-caution-text">
                          Breaks the safety rules: {focused.breaches.join(", ")}
                        </p>
                      ) : null}
                    </>
                  ) : null}
                  <Disclosure title="Money left each month, every scenario">
                    <ScenarioSurplusChart results={results} />
                  </Disclosure>
                </div>
              </div>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
