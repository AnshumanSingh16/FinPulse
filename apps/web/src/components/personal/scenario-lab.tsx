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
import { AssessmentBadge, Loading, Notice, Section, inputClass } from "./ui";

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

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <div className="text-xs font-medium tracking-wide text-primary uppercase">
          Risk agent · what-if lab
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">Scenarios</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Change the assumptions and stress events, then re-run the Risk Agent&apos;s simulation.
          These are hypothetical scenarios, not predictions.
        </p>
      </header>

      {!selected ? (
        <Notice tone="info" title="No completed analysis yet">
          Scenarios are run against an affordability analysis.{" "}
          <Link href="/afford" className="text-primary hover:underline">
            Run one first
          </Link>
          .
        </Notice>
      ) : (
        <>
          <Section title="Base analysis & assumptions">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="run" className="text-xs font-medium text-muted-foreground">
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
                      {new Date(r.createdAt).toLocaleTimeString("en-IN", { hour12: false })}
                    </option>
                  ))}
                </select>
              </div>
              <NumberInput
                label="Interest rate (override)"
                suffix="% p.a."
                min={0}
                max={50}
                step={0.05}
                value={overrides.annualInterestRate}
                onChange={(v) => setOverrides({ ...overrides, annualInterestRate: v })}
                placeholder="as analysed"
              />
              <NumberInput
                label="Tenure (override)"
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
                label="Down payment (override)"
                suffix="%"
                min={0}
                max={100}
                value={overrides.downPaymentPct}
                onChange={(v) => setOverrides({ ...overrides, downPaymentPct: v })}
                placeholder="as analysed"
              />
            </div>
          </Section>

          <Section
            title="Stress events"
            description="Each row is one scenario. Combine several changes in a row to model events happening together."
            actions={
              <>
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
                  <Plus /> Add
                </Button>
              </>
            }
          >
            <div className="flex flex-col gap-3">
              {scenarios.map((s, i) => (
                <div
                  key={s.id}
                  className="grid items-end gap-3 rounded-lg border bg-background/30 p-3 sm:grid-cols-2 lg:grid-cols-[1.4fr_repeat(5,1fr)_auto]"
                >
                  <div className="flex flex-col gap-1.5">
                    <label
                      className="text-xs font-medium text-muted-foreground"
                      htmlFor={`n${s.id}`}
                    >
                      Name
                    </label>
                    <input
                      id={`n${s.id}`}
                      className={inputClass}
                      value={s.name}
                      maxLength={80}
                      onChange={(e) => patch(i, { name: e.target.value || "Scenario" })}
                    />
                  </div>
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
                    label="Expenses change"
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
                  <MoneyInput
                    label="One-off expense"
                    value={s.oneOffExpense || null}
                    onChange={(v) => patch(i, { oneOffExpense: v ?? 0 })}
                    placeholder="0"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Remove ${s.name}`}
                    disabled={scenarios.length <= 1}
                    onClick={() => setScenarios(scenarios.filter((_, j) => j !== i))}
                  >
                    <Trash2 />
                  </Button>
                </div>
              ))}
            </div>
            {error ? <Notice tone="error">{error}</Notice> : null}
            <Button onClick={run} disabled={busy} className="w-fit">
              {busy ? <Loader2 className="animate-spin" /> : <FlaskConical />} Run scenarios
            </Button>
          </Section>

          {results && baseline ? (
            <Section
              title="Results"
              description={`Against "${selected.label}". Each scenario replays 12 months from the savings left after purchase.`}
            >
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {results.map((r) => (
                  <button
                    key={r.params.id}
                    type="button"
                    onClick={() => !r.isBaseline && setFocus(r.params.id)}
                    className={cn(
                      "flex flex-col gap-2 rounded-lg border p-3 text-left transition",
                      focus === r.params.id
                        ? "border-primary/60 bg-primary/5"
                        : "bg-background/30 hover:border-foreground/30",
                      r.isBaseline && "cursor-default",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">{r.params.name}</span>
                      <AssessmentBadge label={r.label} />
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {r.isBaseline
                        ? "Assumptions as analysed"
                        : r.changedAssumptions.join(" · ") || "No changes"}
                    </span>
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
                      <dt className="text-muted-foreground">Monthly surplus</dt>
                      <dd
                        className={cn(
                          "tabular text-right",
                          r.monthlySurplus < 0 && "text-chart-negative",
                        )}
                      >
                        {formatINR(r.monthlySurplus)}
                      </dd>
                      <dt className="text-muted-foreground">EMI</dt>
                      <dd className="tabular text-right">{formatINR(r.emi)}</dd>
                      <dt className="text-muted-foreground">Savings after 12 mo</dt>
                      <dd
                        className={cn(
                          "tabular text-right",
                          r.savingsAfterHorizon < 0 && "text-chart-negative",
                        )}
                      >
                        {formatINR(r.savingsAfterHorizon)}
                      </dd>
                      <dt className="text-muted-foreground">Emergency cover</dt>
                      <dd className="tabular text-right">
                        {r.emergencyMonths === null ? "—" : `${r.emergencyMonths.toFixed(1)} mo`}
                      </dd>
                    </dl>
                    {r.monthExhausted !== null ? (
                      <span className="text-xs text-chart-negative">
                        Savings run out in month {r.monthExhausted}
                      </span>
                    ) : null}
                    {r.breaches.length ? (
                      <span className="text-xs text-status-warning">
                        Breaches: {r.breaches.join(", ")}
                      </span>
                    ) : null}
                  </button>
                ))}
              </div>
              <div className="grid gap-5 lg:grid-cols-2">
                <div className="flex flex-col gap-2">
                  <h3 className="text-sm font-medium">Monthly surplus by scenario</h3>
                  <ScenarioSurplusChart results={results} />
                </div>
                {focused ? (
                  <div className="flex flex-col gap-2">
                    <h3 className="text-sm font-medium">
                      Liquid savings: baseline vs {focused.params.name}
                    </h3>
                    <SavingsTrajectoryChart baseline={baseline} scenario={focused} />
                  </div>
                ) : null}
              </div>
            </Section>
          ) : null}
        </>
      )}
    </div>
  );
}
