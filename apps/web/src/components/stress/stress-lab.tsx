"use client";

import type { ScenarioCatalogue, StressComparison, StressTestResult } from "@finpulse/contracts";
import { ArrowRight, FlaskConical, Loader2, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { TimeSeriesChart } from "@/components/charts/time-series";
import { StressRiskBadge, ToneBadge } from "@/components/fp/badges";
import { Disclaimer, Panel } from "@/components/fp/layout";
import { ApiErrorPanel } from "@/components/fp/states";
import { getBrowserApiClient } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/client";
import { formatDate, formatMetric, toNumber } from "@/lib/format";
import { label, type Tone } from "@/lib/presentation";
import {
  fieldsOf,
  initialInputs,
  missing,
  shockPayload,
  type Field,
  type FormValue,
} from "@/lib/shock-form";
import { cn } from "@/lib/utils";

type ShockType = ScenarioCatalogue["shock_types"][number];
type Shock = { id: number; type: string; inputs: Record<string, FormValue> };

let nextId = 1;

function shocksFromPreset(catalogue: ScenarioCatalogue, code: string): Shock[] {
  const preset = catalogue.presets.find((p) => p.code === code);
  return (preset?.shocks ?? []).map((params) => {
    const p = params as Record<string, unknown>;
    const type = String(p.type);
    const t = catalogue.shock_types.find((s) => s.type === type);
    return { id: nextId++, type, inputs: initialInputs(fieldsOf(t?.parameters_schema), p) };
  });
}

export function StressLab({
  catalogue,
  entityId,
  asOf,
  initialPreset,
}: {
  catalogue: ScenarioCatalogue;
  entityId: string;
  asOf?: string;
  /** Preset to load and run first (e.g. from a demo link); defaults to a 20% revenue fall. */
  initialPreset?: string;
}) {
  const types = useMemo(
    () =>
      Object.fromEntries(
        catalogue.shock_types.map((t) => [
          t.type,
          { meta: t, fields: fieldsOf(t.parameters_schema) },
        ]),
      ),
    [catalogue],
  );
  const firstPreset =
    catalogue.presets.find((p) => p.code === initialPreset)?.code ??
    catalogue.presets.find((p) => p.code === "revenue_down_20")?.code ??
    catalogue.presets[0]?.code ??
    "";
  const [preset, setPreset] = useState<string>(firstPreset);
  const [shocks, setShocks] = useState<Shock[]>(() => shocksFromPreset(catalogue, firstPreset));
  const [pristine, setPristine] = useState(true); // still exactly the preset
  const [horizon, setHorizon] = useState(6);
  const [result, setResult] = useState<StressTestResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [running, setRunning] = useState(false);

  const invalid = shocks.flatMap((s) => missing(types[s.type]?.fields ?? [], s.inputs));

  const run = useCallback(
    async (opts: { preset?: string; shocks?: Shock[]; horizon: number }) => {
      setRunning(true);
      setError(null);
      try {
        const body = opts.preset
          ? { preset: opts.preset, horizon_months: opts.horizon, ...(asOf ? { as_of: asOf } : {}) }
          : {
              shocks: (opts.shocks ?? []).map((s) =>
                shockPayload(s.type, types[s.type]?.fields ?? [], s.inputs),
              ),
              horizon_months: opts.horizon,
              ...(asOf ? { as_of: asOf } : {}),
            };
        const data = await unwrap(
          getBrowserApiClient().POST("/api/v1/entities/{entity_id}/stress-test", {
            params: { path: { entity_id: entityId } },
            // Shocks are validated by the API against the schemas it published.
            body: body as never,
          }),
        );
        setResult(data);
      } catch (e) {
        setError(e);
      } finally {
        setRunning(false);
      }
    },
    [asOf, entityId, types],
  );

  // Run the default scenario on arrival (a real API call, never a placeholder result).
  useEffect(() => {
    const t = setTimeout(() => void run({ preset: firstPreset, horizon: 6 }), 0);
    return () => clearTimeout(t);
  }, [run, firstPreset]);

  const choosePreset = (code: string) => {
    setPreset(code);
    setShocks(shocksFromPreset(catalogue, code));
    setPristine(true);
    void run({ preset: code, horizon });
  };
  const edit = (id: number, key: string, value: FormValue) => {
    setPristine(false);
    setShocks((all) =>
      all.map((s) => (s.id === id ? { ...s, inputs: { ...s.inputs, [key]: value } } : s)),
    );
  };
  const addShock = (type: string) => {
    setPristine(false);
    setShocks((all) => [
      ...all,
      { id: nextId++, type, inputs: initialInputs(types[type]?.fields ?? []) },
    ]);
  };
  const removeShock = (id: number) => {
    setPristine(false);
    setShocks((all) => all.filter((s) => s.id !== id));
  };
  const submit = () => void run(pristine && preset ? { preset, horizon } : { shocks, horizon });

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <div className="flex flex-col gap-4 lg:sticky lg:top-6 lg:self-start">
        <Panel
          title="Scenario"
          description="Start from a preset, then adjust its parameters or combine shocks."
        >
          <div className="flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-xs font-medium">
              Preset
              <select
                className="h-9 rounded-md border bg-card px-2 text-sm"
                value={preset}
                onChange={(e) => choosePreset(e.target.value)}
              >
                {catalogue.presets.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>

            {shocks.map((s, i) => {
              const t = types[s.type];
              return (
                <fieldset key={s.id} className="flex flex-col gap-3 rounded-lg border p-3">
                  <legend className="flex w-full items-center justify-between gap-2 px-1 text-xs font-semibold">
                    <span>
                      {i + 1}. {t?.meta.name ?? s.type}
                    </span>
                  </legend>
                  <div className="-mt-1 flex items-start justify-between gap-2">
                    <p className="text-[11px] text-pretty text-muted-foreground">
                      {t?.meta.description}
                    </p>
                    {shocks.length > 1 ? (
                      <button
                        type="button"
                        onClick={() => removeShock(s.id)}
                        className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                        aria-label="Remove shock"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    ) : null}
                  </div>
                  <div className="grid grid-cols-2 gap-2.5">
                    {(t?.fields ?? []).map((f) => (
                      <FieldInput
                        key={f.key}
                        field={f}
                        value={s.inputs[f.key] ?? ""}
                        onChange={(v) => edit(s.id, f.key, v)}
                      />
                    ))}
                  </div>
                </fieldset>
              );
            })}

            <label className="flex items-center gap-2 text-xs">
              <Plus className="size-3.5 text-muted-foreground" aria-hidden />
              <select
                className="h-8 flex-1 rounded-md border bg-card px-2 text-xs"
                value=""
                onChange={(e) => e.target.value && addShock(e.target.value)}
              >
                <option value="">Add a shock…</option>
                {catalogue.shock_types.map((t: ShockType) => (
                  <option key={t.type} value={t.type}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1.5 text-xs font-medium">
              <span className="flex justify-between">
                Horizon <span className="tabular text-muted-foreground">{horizon} months</span>
              </span>
              <input
                type="range"
                min={1}
                max={24}
                value={horizon}
                onChange={(e) => setHorizon(Number(e.target.value))}
              />
            </label>

            {invalid.length ? (
              <p className="text-xs text-status-critical">Required: {invalid.join(", ")}.</p>
            ) : null}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={submit}
                disabled={running || invalid.length > 0 || shocks.length === 0}
                className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-xs hover:bg-primary/90 disabled:opacity-60"
              >
                {running ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                ) : (
                  <FlaskConical className="size-4" aria-hidden />
                )}
                Run stress test
              </button>
              <button
                type="button"
                onClick={() => choosePreset(preset)}
                className="inline-flex h-9 items-center rounded-md border px-2.5 text-muted-foreground hover:bg-muted"
                aria-label="Reset to preset"
                title="Reset to preset"
              >
                <RotateCcw className="size-4" />
              </button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              {pristine ? "Runs the preset as defined." : "Runs your custom shocks."} Calculated by
              the deterministic stress engine.
            </p>
          </div>
        </Panel>
      </div>

      <div
        className={cn(
          "flex min-w-0 flex-col gap-4 transition-opacity",
          running && result && "opacity-60",
        )}
      >
        {error ? <ApiErrorPanel error={error} what="the stress test" /> : null}
        {result ? <Results r={result} /> : running ? <ResultsLoading /> : null}
      </div>
    </div>
  );
}

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: Field;
  value: FormValue;
  onChange: (v: FormValue) => void;
}) {
  if (field.kind === "boolean") {
    return (
      <label className="col-span-2 flex items-center gap-2 text-xs" title={field.help}>
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
        />
        {field.label}
      </label>
    );
  }
  const suffix =
    field.kind === "percent"
      ? "%"
      : field.key.endsWith("bps")
        ? "bps"
        : field.key.includes("month")
          ? "mo"
          : field.key === "days"
            ? "days"
            : field.key === "principal"
              ? "₹"
              : "";
  return (
    <label
      className={cn(
        "flex flex-col gap-1 text-[11px] font-medium",
        field.kind === "uuid" && "col-span-2",
      )}
      title={field.help}
    >
      <span className="truncate">
        {field.label}
        {field.required ? <span className="text-status-critical"> *</span> : null}
      </span>
      <span className="relative flex items-center">
        <input
          className="tabular h-8 w-full rounded-md border bg-card px-2 pr-9 text-sm"
          inputMode={field.kind === "uuid" ? "text" : "decimal"}
          placeholder={
            field.kind === "uuid"
              ? "Largest (default)"
              : field.nullable || !field.required
                ? "default"
                : ""
          }
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
        />
        {suffix ? (
          <span className="pointer-events-none absolute right-2 text-[11px] text-muted-foreground">
            {suffix}
          </span>
        ) : null}
      </span>
    </label>
  );
}

function ResultsLoading() {
  return (
    <div className="flex h-64 items-center justify-center gap-2 rounded-xl border border-dashed text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" aria-hidden /> Running the stress engine…
    </div>
  );
}

const DIRECTION_TONE: Record<string, Tone> = {
  better: "good",
  worse: "critical",
  unchanged: "neutral",
};

function BeforeAfter({
  title,
  before,
  after,
  tone,
  note,
}: {
  title: string;
  before: React.ReactNode;
  after: React.ReactNode;
  tone: Tone;
  note?: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-xl border bg-card p-4 shadow-xs">
      <span className="text-xs font-medium text-muted-foreground">{title}</span>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <span className="tabular text-lg text-muted-foreground">{before}</span>
        <ArrowRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <span
          className={cn(
            "tabular text-2xl font-semibold",
            tone === "critical" && "text-status-critical",
            tone === "good" && "text-text-good",
          )}
        >
          {after}
        </span>
      </div>
      {note ? <span className="text-[11px] text-muted-foreground">{note}</span> : null}
    </div>
  );
}

function Results({ r }: { r: StressTestResult }) {
  const c = (key: string) => r.comparisons.find((x) => x.key === key);
  const value = (cmp: StressComparison | undefined, which: "baseline" | "scenario") => {
    if (!cmp) return "—";
    const v = cmp[which];
    if (v === null && cmp.key === "cash_runway_months") return "Not burning";
    return formatMetric(v, cmp.unit, {
      code: cmp.key === "liquidity_ratio" ? "liquidity.ratio" : undefined,
      compact: cmp.unit === "INR",
    });
  };
  const card = (key: string, title: string, note?: string) => {
    const cmp = c(key);
    return (
      <BeforeAfter
        key={key}
        title={title}
        before={value(cmp, "baseline")}
        after={value(cmp, "scenario")}
        tone={DIRECTION_TONE[cmp?.direction ?? "unchanged"] ?? "neutral"}
        note={note}
      />
    );
  };
  const months = r.baseline.months.map((m, i) => ({
    date: m.month,
    baseline: toNumber(m.closing_balance),
    scenario: toNumber(r.stressed.months[i]?.closing_balance),
  }));
  const hi = r.health_impact;
  return (
    <>
      <Panel
        title={r.scenario.name}
        description={`${r.horizon_months}-month projection from ${formatDate(r.projection_start)} · baseline = no shock · engine ${r.engine_version}`}
      >
        <ul className="flex flex-col gap-1 text-sm">
          {r.scenario.shocks.map((s, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-chart-2" />
              {s.description}
            </li>
          ))}
        </ul>
      </Panel>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {card("cash_runway_months", "Cash runway")}
        <BeforeAfter
          title="Financial Health (projected)"
          before={hi.baseline_projected_score ?? "—"}
          after={hi.scenario_score ?? "—"}
          tone={
            (toNumber(hi.change) ?? 0) < 0
              ? "critical"
              : (toNumber(hi.change) ?? 0) > 0
                ? "good"
                : "neutral"
          }
          note={`${label(hi.baseline_band ?? "")} → ${label(hi.scenario_band ?? "")} · today ${hi.current_score ?? "—"}`}
        />
        <BeforeAfter
          title="Risk"
          before={<StressRiskBadge level={r.risk_change.baseline} size="md" />}
          after={<StressRiskBadge level={r.risk_change.scenario} size="md" />}
          tone={r.risk_change.escalated ? "critical" : "neutral"}
          note={r.risk_change.summary}
        />
        {card("closing_balance", "Cash at end of horizon")}
        {card("minimum_balance", "Lowest cash balance")}
        <BeforeAfter
          title="Failure point"
          before={r.baseline.failure_point ? formatDate(r.baseline.failure_point.date) : "None"}
          after={r.stressed.failure_point ? formatDate(r.stressed.failure_point.date) : "None"}
          tone={r.stressed.failure_point && !r.baseline.failure_point ? "critical" : "neutral"}
          note="When funds, including the overdraft, run out"
        />
      </div>

      <Panel
        title="Projected month-end cash"
        description="Closing balance each month: no shock vs scenario. Below zero = overdraft in use."
      >
        <TimeSeriesChart
          data={months}
          unit="INR"
          zeroLine
          series={[
            { key: "scenario", label: "Scenario", color: "var(--chart-2)" },
            { key: "baseline", label: "No shock", color: "var(--chart-1)" },
          ]}
          height={260}
        />
      </Panel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Panel title="All projected measures" bodyClassName="p-0 sm:p-0">
          <div className="overflow-x-auto">
            <table className="tabular w-full text-xs">
              <thead className="bg-muted text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Measure</th>
                  <th className="px-3 py-2 text-right font-medium">No shock</th>
                  <th className="px-3 py-2 text-right font-medium">Scenario</th>
                  <th className="px-4 py-2 text-right font-medium">Change</th>
                </tr>
              </thead>
              <tbody>
                {r.comparisons.map((cmp) => (
                  <tr key={cmp.key} className="border-t">
                    <td className="px-4 py-2">{cmp.label}</td>
                    <td className="px-3 py-2 text-right">{value(cmp, "baseline")}</td>
                    <td className="px-3 py-2 text-right font-medium">{value(cmp, "scenario")}</td>
                    <td className="px-4 py-2 text-right">
                      <ToneBadge tone={DIRECTION_TONE[cmp.direction] ?? "neutral"} icon={null}>
                        {cmp.absolute_change === null
                          ? "—"
                          : formatMetric(cmp.absolute_change, cmp.unit, {
                              code: cmp.key === "liquidity_ratio" ? "liquidity.ratio" : undefined,
                              signed: true,
                              compact: cmp.unit === "INR",
                            })}
                      </ToneBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel
          title="Why"
          description="Risk reasons and the health-score drivers under the scenario."
        >
          <div className="flex flex-col gap-3 text-sm">
            <ul className="flex flex-col gap-1.5">
              {r.stressed.risk.reasons.map((reason) => (
                <li key={reason} className="flex gap-2">
                  <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-status-critical" />
                  {reason}
                </li>
              ))}
            </ul>
            <p className="border-t pt-3 text-xs text-pretty text-muted-foreground">{hi.summary}</p>
          </div>
        </Panel>
      </div>

      <Panel
        title="Evidence"
        description="The inputs and outcomes behind these numbers, as stated by the stress engine."
      >
        <ol className="flex flex-col gap-2">
          {r.evidence.map((e) => (
            <li key={e.id} className="flex gap-3 text-sm">
              <span className="w-16 shrink-0 pt-0.5">
                <ToneBadge
                  tone={
                    e.kind === "outcome" ? "warning" : e.kind === "shock" ? "serious" : "neutral"
                  }
                  icon={null}
                >
                  {e.kind}
                </ToneBadge>
              </span>
              <span className="min-w-0 text-pretty">
                {e.text} <code className="text-[11px] text-muted-foreground">{e.id}</code>
              </span>
            </li>
          ))}
        </ol>
      </Panel>
      <Disclaimer>{r.disclaimer}</Disclaimer>
    </>
  );
}
