"use client";

import {
  ArrowDown,
  ArrowUp,
  CalendarCheck,
  Car,
  GraduationCap,
  Heart,
  House,
  Loader2,
  Pencil,
  Plane,
  Plus,
  Save,
  Store,
  Target,
  Trash2,
  Undo2,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/personal/client";
import {
  addMonths,
  DEFAULT_ASSUMPTIONS,
  GOAL_KINDS,
  monthsBetween,
  type GoalKind,
  type GoalProjection,
  type PlanAssumptions,
  type PlanProjection,
} from "@/lib/personal/finance/plan";
import {
  effectiveAssumptions,
  GOAL_KIND_LABEL,
  goalTemplate,
  projectFor,
  type Pulse,
} from "@/lib/personal/plan-model";
import type { PlanGoalValues } from "@/lib/personal/schemas";
import { cn } from "@/lib/utils";

import { PlanTimelineChart } from "./charts";
import { Field, MoneyInput, NumberInput } from "./fields";
import { Chip } from "./kit";
import { usePersonal } from "./provider";
import { Disclosure, EmptyState, Loading, Notice, PageTitle, inputClass } from "./ui";

export const GOAL_ICON: Record<GoalKind, LucideIcon> = {
  house: House,
  car: Car,
  education: GraduationCap,
  wedding: Heart,
  travel: Plane,
  business: Store,
  custom: Target,
};

export function fmtMonth(month: string | null): string {
  if (!month) return "—";
  const [y, m] = month.split("-").map(Number);
  return new Date(y!, m! - 1, 1).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

const STATUS = {
  on_track: { label: "On track", cls: "bg-brand-50 text-brand-700" },
  stretched: { label: "Some goals late", cls: "bg-caution-50 text-caution-text" },
  off_track: { label: "Plan doesn't hold", cls: "bg-danger-50 text-danger-text" },
  no_goals: { label: "No goals yet", cls: "bg-surface-sunken text-ink-500" },
} as const;

const GOAL_STATUS = {
  on_track: { label: "On track", cls: "bg-brand-50 text-brand-700" },
  delayed: { label: "Late", cls: "bg-caution-50 text-caution-text" },
  not_reached: { label: "Out of reach", cls: "bg-danger-50 text-danger-text" },
} as const;

export function PlanStatusBadge({ status }: { status: PlanProjection["summary"]["status"] }) {
  const s = STATUS[status];
  return (
    <span
      className={cn(
        "rounded-full px-2.5 py-0.5 text-[12px] font-semibold whitespace-nowrap",
        s.cls,
      )}
    >
      {s.label}
    </span>
  );
}

export function PlanWorkspace() {
  const { state, setState } = usePersonal();
  const [draft, setDraft] = useState<{
    goals: PlanGoalValues[];
    assumptions: Partial<PlanAssumptions>;
  } | null>(null);
  const [baseline, setBaseline] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const saved = state ? JSON.stringify({ g: state.plan.goals, a: state.plan.assumptions }) : null;
  if (state && saved !== baseline) {
    setBaseline(saved);
    setDraft({ goals: state.plan.goals, assumptions: state.plan.assumptions });
  }

  const projected = useMemo(
    () =>
      state && draft
        ? projectFor({
            profile: state.profile.values,
            goals: draft.goals,
            assumptions: draft.assumptions,
            startMonth: state.plan.startMonth,
          })
        : null,
    [state, draft],
  );

  if (!state || !draft || !projected) return <Loading label="Loading your plan…" />;
  const start = state.plan.startMonth;
  const dirty = JSON.stringify({ g: draft.goals, a: draft.assumptions }) !== saved;
  const p = projected.projection;

  const setGoals = (goals: PlanGoalValues[]) =>
    setDraft({ ...draft, goals: goals.map((g, i) => ({ ...g, priority: i + 1 })) });
  const ordered = [...draft.goals].sort((a, b) => a.priority - b.priority);
  const move = (id: string, by: -1 | 1) => {
    const i = ordered.findIndex((g) => g.id === id);
    const j = i + by;
    if (j < 0 || j >= ordered.length) return;
    const next = [...ordered];
    [next[i], next[j]] = [next[j]!, next[i]!];
    setGoals(next);
  };
  const addGoal = (kind: GoalKind) => {
    const g = goalTemplate(kind, start, ordered.length + 1);
    setGoals([...ordered, g]);
    setEditing(g.id);
  };

  async function save() {
    if (!draft) return;
    setBusy(true);
    setMessage(null);
    try {
      setState(await api.savePlan(draft.goals, draft.assumptions));
      setMessage({ tone: "success", text: "Plan saved." });
      setEditing(null);
    } catch (e) {
      setMessage({
        tone: "error",
        text: e instanceof Error ? e.message : "Couldn't save the plan",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageTitle
        eyebrow="Your plan"
        title="Every goal, one plan"
        description="Your goals compete for the same salary and savings. FinPulse projects them together, month by month, so you can see which ones land on time — and what any new purchase would push back."
      />

      {!p ? (
        <EmptyState
          icon={Target}
          title="Add your income, spending and savings first"
          action={
            <Link
              href="/profile"
              className="text-[14px] font-semibold text-brand-700 hover:underline"
            >
              Open My finances →
            </Link>
          }
        >
          The plan needs: {projected.missing.join(", ")}. Or load the demo household from Home.
        </EmptyState>
      ) : (
        <>
          <PlanHealth projection={p} />

          {p.goals.length ? (
            <section className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-6">
              <div className="flex flex-col gap-1">
                <h2 className="text-[16px] font-bold">How your money moves</h2>
                <p className="text-[13px] text-ink-500">
                  Savings set aside (emergency reserve, goal funds and spare savings) and loans
                  taken for goals, at the end of each year. Dots mark the years goals are reached.
                </p>
              </div>
              <PlanTimelineChart years={p.years} />
            </section>
          ) : null}

          <section className="flex flex-col gap-3" aria-labelledby="goals-h">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 id="goals-h" className="text-[16px] font-bold">
                  Goals, most important first
                </h2>
                <p className="text-[13px] text-ink-500">
                  Higher goals are funded first. Use the arrows to change the order.
                </p>
              </div>
            </div>
            {ordered.map((g, i) => {
              const proj = p.goals.find((x) => x.id === g.id)!;
              return (
                <GoalCard
                  key={g.id}
                  goal={g}
                  projection={proj}
                  rank={i + 1}
                  count={ordered.length}
                  editing={editing === g.id}
                  startMonth={start}
                  onEdit={() => setEditing(editing === g.id ? null : g.id)}
                  onMove={(by) => move(g.id, by)}
                  onRemove={() => setGoals(ordered.filter((x) => x.id !== g.id))}
                  onChange={(next) => setGoals(ordered.map((x) => (x.id === g.id ? next : x)))}
                />
              );
            })}
            <div className="flex flex-col gap-2 rounded-2xl border border-dashed border-line-strong bg-surface p-4">
              <span className="text-[13px] font-semibold">
                {ordered.length ? "Add another goal" : "Add your first goal"}
              </span>
              <div className="flex flex-wrap gap-2">
                {GOAL_KINDS.map((k) => {
                  const Icon = GOAL_ICON[k];
                  return (
                    <Chip
                      key={k}
                      icon={Icon}
                      onClick={() => addGoal(k)}
                      className={ordered.length >= 12 ? "pointer-events-none opacity-50" : ""}
                    >
                      {GOAL_KIND_LABEL[k]}
                    </Chip>
                  );
                })}
              </div>
            </div>
          </section>

          <Disclosure
            title="Assumptions"
            hint="Income growth, inflation, returns and the emergency reserve — not forecasts; change them to match your view"
          >
            <AssumptionsEditor
              value={effectiveAssumptions(state.profile.values, draft.assumptions)}
              onChange={(a) => setDraft({ ...draft, assumptions: a })}
            />
          </Disclosure>

          {message ? <Notice tone={message.tone}>{message.text}</Notice> : null}
          {dirty ? (
            <div className="sticky bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-10 flex flex-wrap items-center gap-3 rounded-2xl border border-line-strong bg-surface p-3 shadow-md lg:bottom-4">
              <span className="text-[13px] text-ink-700">
                Unsaved changes — the figures above already reflect them.
              </span>
              <div className="ml-auto flex gap-2">
                <Button
                  variant="ghost"
                  onClick={() => {
                    setDraft({ goals: state.plan.goals, assumptions: state.plan.assumptions });
                    setEditing(null);
                  }}
                  disabled={busy}
                >
                  <Undo2 /> Discard
                </Button>
                <Button onClick={save} disabled={busy}>
                  {busy ? <Loader2 className="animate-spin" /> : <Save />} Save plan
                </Button>
              </div>
            </div>
          ) : null}

          <PulseSection
            pulse={state.plan.pulse}
            startMonth={start}
            income={state.profile.values.monthlyIncome}
          />
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- plan health

function PlanHealth({ projection: p }: { projection: PlanProjection }) {
  const s = p.summary;
  const stats = [
    {
      label: "Left each month today",
      value: formatINR(s.surplusNow),
      note: "after spending and EMIs",
    },
    {
      label: "Your goals need",
      value: `${formatINR(s.requiredMonthlyTotal)}/mo`,
      note:
        s.commitmentPct === null ? "no surplus to fund them" : `${s.commitmentPct}% of what's left`,
    },
    {
      label: "Spare after goals",
      value: formatINR(s.freeMonthlyNow),
      note: s.freeMonthlyNow < 0 ? "spending more than you earn" : "this month",
      bad: s.freeMonthlyNow < 0,
    },
    {
      label: "Emergency reserve",
      value: formatINR(s.reserveTarget),
      note:
        s.reserveNow >= s.reserveTarget
          ? `${p.assumptions.emergencyMonths} months, fully covered`
          : `${formatINR(s.reserveNow)} today · full by ${fmtMonth(s.reserveFullMonth)}`,
    },
  ];
  return (
    <section
      className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-6"
      aria-labelledby="health-h"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="health-h" className="text-[18px] font-bold">
          {s.status === "no_goals"
            ? "Add a goal to see your plan"
            : `${s.onTrack} of ${p.goals.length} goal${p.goals.length === 1 ? "" : "s"} on track`}
        </h2>
        <PlanStatusBadge status={s.status} />
      </div>
      {s.shortfallMonths > 0 ? (
        <Notice tone="error">
          In {s.shortfallMonths} month(s) of the projection, spending and EMIs exceed income and
          every balance — the plan needs changes.
        </Notice>
      ) : null}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((x) => (
          <div key={x.label} className="flex flex-col gap-0.5">
            <span className="text-[12px] text-ink-500">{x.label}</span>
            <span
              className={cn(
                "tabular font-display text-[18px] font-bold whitespace-nowrap sm:text-[20px]",
                x.bad && "text-danger-text",
              )}
            >
              {x.value}
            </span>
            <span className="text-[12px] text-ink-400">{x.note}</span>
          </div>
        ))}
      </div>
      <p className="text-[12px] text-ink-400">
        Projected from {fmtMonth(p.startMonth)} for {Math.round(p.horizonMonths / 12)} years.
        Existing investments are left untouched to keep growing, and things you buy aren&apos;t
        counted as savings.
      </p>
    </section>
  );
}

// ---------------------------------------------------------------- goal card

function GoalCard({
  goal,
  projection: g,
  rank,
  count,
  editing,
  startMonth,
  onEdit,
  onMove,
  onRemove,
  onChange,
}: {
  goal: PlanGoalValues;
  projection: GoalProjection;
  rank: number;
  count: number;
  editing: boolean;
  startMonth: string;
  onEdit: () => void;
  onMove: (by: -1 | 1) => void;
  onRemove: () => void;
  onChange: (g: PlanGoalValues) => void;
}) {
  const Icon = GOAL_ICON[goal.kind];
  const st = GOAL_STATUS[g.status];
  return (
    <article
      className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-5"
      aria-labelledby={`goal-${goal.id}`}
    >
      <div className="flex items-start gap-3">
        <div className="flex flex-col items-center gap-1">
          <span className="flex size-10 items-center justify-center rounded-xl bg-surface-sunken text-ink-700">
            <Icon className="size-5" aria-hidden />
          </span>
          <span className="tabular text-[11px] font-semibold text-ink-400">#{rank}</span>
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 id={`goal-${goal.id}`} className="text-[15px] font-bold">
              {goal.name}
            </h3>
            <span className={cn("rounded-full px-2 py-0.5 text-[11.5px] font-semibold", st.cls)}>
              {st.label}
            </span>
          </div>
          <p className="text-[13px] text-pretty text-ink-700">
            {formatINR(goal.targetAmount)} today ·{" "}
            {goal.funding === "loan"
              ? `${goal.downPaymentPct}% down, rest on a loan`
              : "paid in cash"}
            {" · "}wanted {fmtMonth(goal.targetMonth)}
          </p>
          <p
            className={cn(
              "text-[13px] font-medium",
              g.status === "on_track"
                ? "text-brand-700"
                : g.status === "delayed"
                  ? "text-caution-text"
                  : "text-danger-text",
            )}
          >
            {g.status === "on_track"
              ? `Reached ${fmtMonth(g.achievedMonth)}, on time`
              : g.status === "delayed"
                ? `Reached ${fmtMonth(g.achievedMonth)} — ${g.delayMonths} month${g.delayMonths === 1 ? "" : "s"} late`
                : "Not reached within the projection"}
          </p>
        </div>
        <div className="flex shrink-0 items-center">
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Move ${goal.name} up`}
            disabled={rank === 1}
            onClick={() => onMove(-1)}
          >
            <ArrowUp />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Move ${goal.name} down`}
            disabled={rank === count}
            onClick={() => onMove(1)}
          >
            <ArrowDown />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Edit ${goal.name}`}
            aria-expanded={editing}
            onClick={onEdit}
          >
            <Pencil />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-3 border-t border-line pt-3 sm:grid-cols-4">
        <Fig label="Needs each month" value={formatINR(g.requiredMonthly)} />
        <Fig
          label="Gets this month"
          value={formatINR(g.allocatedMonthly)}
          warn={g.allocatedMonthly + 1 < g.requiredMonthly}
        />
        <Fig
          label={`Cash needed ${fmtMonth(goal.targetMonth)}`}
          value={formatINR(g.cashNeededAtTarget)}
          note={`price then ${formatINR(g.priceAtTarget)}`}
        />
        {g.loan ? (
          <Fig
            label="EMI once bought"
            value={formatINR(g.loan.emi)}
            note={`${g.loan.ratePct}% · ${Math.round(g.loan.tenureMonths / 12)} yrs`}
          />
        ) : (
          <Fig label="Set aside today" value={formatINR(g.startingAllocation)} />
        )}
      </div>
      {g.dueIndex > 0 ? (
        <div className="flex items-center gap-3">
          <div
            className="h-2 flex-1 overflow-hidden rounded-full bg-surface-sunken"
            role="progressbar"
            aria-label={`${goal.name}: funded on the target date`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={g.fundedPctAtTarget}
          >
            <div
              className={cn(
                "h-full rounded-full",
                g.fundedPctAtTarget >= 100 ? "bg-brand-600" : "bg-caution-500",
              )}
              style={{ width: `${g.fundedPctAtTarget}%` }}
            />
          </div>
          <span className="tabular text-[12px] whitespace-nowrap text-ink-500">
            {g.fundedPctAtTarget}% funded by {fmtMonth(goal.targetMonth)}
          </span>
        </div>
      ) : null}

      {editing ? (
        <GoalEditor goal={goal} startMonth={startMonth} onChange={onChange} onRemove={onRemove} />
      ) : null}
    </article>
  );
}

function Fig({
  label,
  value,
  note,
  warn,
}: {
  label: string;
  value: string;
  note?: string;
  warn?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-[12px] text-ink-500">{label}</span>
      <span
        className={cn(
          "tabular text-[15px] font-semibold whitespace-nowrap",
          warn && "text-caution-text",
        )}
      >
        {value}
      </span>
      {note ? <span className="text-[11.5px] text-ink-400">{note}</span> : null}
    </div>
  );
}

function GoalEditor({
  goal,
  startMonth,
  onChange,
  onRemove,
}: {
  goal: PlanGoalValues;
  startMonth: string;
  onChange: (g: PlanGoalValues) => void;
  onRemove: () => void;
}) {
  const set = <K extends keyof PlanGoalValues>(k: K, v: PlanGoalValues[K]) =>
    onChange({ ...goal, [k]: v });
  const months = monthsBetween(startMonth, goal.targetMonth);
  return (
    <div className="flex flex-col gap-4 rounded-xl bg-surface-sunken/60 p-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Name" htmlFor={`n-${goal.id}`}>
          <input
            id={`n-${goal.id}`}
            className={inputClass}
            maxLength={60}
            value={goal.name}
            onChange={(e) => set("name", e.target.value.trimStart() || GOAL_KIND_LABEL[goal.kind])}
          />
        </Field>
        <MoneyInput
          label="Price in today's money"
          value={goal.targetAmount}
          onChange={(v) => set("targetAmount", Math.max(1000, v ?? 1000))}
        />
        <Field
          label="Wanted by"
          htmlFor={`m-${goal.id}`}
          hint={
            months <= 0
              ? "Now"
              : `In ${Math.floor(months / 12) ? `${Math.floor(months / 12)} yr ` : ""}${months % 12 ? `${months % 12} mo` : ""}`
          }
        >
          <input
            id={`m-${goal.id}`}
            type="month"
            className={inputClass}
            min={startMonth}
            max={addMonths(startMonth, 360)}
            value={goal.targetMonth}
            onChange={(e) =>
              /^\d{4}-\d{2}$/.test(e.target.value) && set("targetMonth", e.target.value)
            }
          />
        </Field>
      </div>
      <div
        className="flex flex-wrap items-center gap-2"
        role="radiogroup"
        aria-label="How it's paid for"
      >
        <span className="text-[13px] font-medium text-ink-700">Paid for with</span>
        {(["cash", "loan"] as const).map((f) => (
          <Chip
            key={f}
            selected={goal.funding === f}
            onClick={() =>
              onChange({
                ...goal,
                funding: f,
                downPaymentPct: f === "cash" ? 100 : Math.min(goal.downPaymentPct, 30),
                loanRatePct: f === "loan" && !goal.loanRatePct ? 9 : goal.loanRatePct,
              })
            }
          >
            {f === "cash" ? "Savings" : "A loan"}
          </Chip>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {goal.funding === "loan" ? (
          <>
            <NumberInput
              label="Down payment"
              suffix="%"
              min={0}
              max={100}
              value={goal.downPaymentPct}
              onChange={(v) => set("downPaymentPct", Math.min(100, Math.max(0, v ?? 0)))}
            />
            <NumberInput
              label="Loan rate"
              suffix="% p.a."
              min={0}
              max={30}
              step={0.05}
              value={goal.loanRatePct}
              onChange={(v) => set("loanRatePct", Math.min(30, Math.max(0, v ?? 0)))}
            />
            <NumberInput
              label="Loan tenure"
              suffix="years"
              min={1}
              max={30}
              value={goal.loanTenureMonths / 12}
              onChange={(v) =>
                set("loanTenureMonths", Math.min(360, Math.max(6, Math.round((v ?? 1) * 12))))
              }
            />
          </>
        ) : null}
        <NumberInput
          label="Price inflation"
          suffix="%/yr"
          min={0}
          max={25}
          step={0.5}
          value={goal.inflationPct}
          onChange={(v) => set("inflationPct", Math.min(25, Math.max(0, v ?? 0)))}
        />
        <NumberInput
          label="One-time costs"
          suffix="%"
          min={0}
          max={30}
          step={0.5}
          value={goal.upfrontCostPct}
          onChange={(v) => set("upfrontCostPct", Math.min(30, Math.max(0, v ?? 0)))}
          hint={goal.kind === "house" ? "Stamp duty, registration" : undefined}
        />
      </div>
      <div className="flex justify-end">
        <Button variant="ghost" size="sm" onClick={onRemove} className="text-danger-text">
          <Trash2 /> Remove goal
        </Button>
      </div>
    </div>
  );
}

function AssumptionsEditor({
  value,
  onChange,
}: {
  value: PlanAssumptions;
  onChange: (a: Partial<PlanAssumptions>) => void;
}) {
  const set = (k: keyof PlanAssumptions, v: number | null) => onChange({ ...value, [k]: v });
  const fields: [keyof PlanAssumptions, string, string, number, number, number][] = [
    ["incomeGrowthPct", "Take-home income growth", "%/yr", -10, 30, 0.5],
    ["expenseInflationPct", "Living-cost inflation", "%/yr", 0, 25, 0.5],
    ["safeReturnPct", "Return on near-term money", "%/yr", 0, 15, 0.25],
    ["growthReturnPct", "Return on long-term goal funds", "%/yr", 0, 20, 0.5],
    ["emergencyMonths", "Emergency reserve", "months", 0, 36, 1],
  ];
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {fields.map(([k, label, suffix, min, max, step]) => (
          <NumberInput
            key={k}
            label={label}
            suffix={suffix}
            min={min}
            max={max}
            step={step}
            value={value[k] as number}
            onChange={(v) => set(k, v ?? (DEFAULT_ASSUMPTIONS[k] as number))}
          />
        ))}
        <NumberInput
          label="Existing EMIs end in"
          suffix="months"
          min={0}
          max={360}
          step={1}
          value={value.existingEmiMonthsLeft}
          placeholder="never (keeps paying)"
          onChange={(v) => set("existingEmiMonthsLeft", v === null ? null : Math.round(v))}
        />
      </div>
      <p className="text-[12px] text-ink-500">
        Goal funds more than three years from their date earn the long-term return; everything else
        earns the near-term return. Defaults are round, conservative assumptions — not forecasts or
        product rates.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- pulse

function PulseSection({
  pulse,
  startMonth,
  income,
}: {
  pulse: Pulse;
  startMonth: string;
  income: number | null;
}) {
  const { setState } = usePersonal();
  const [month, setMonth] = useState(addMonths(startMonth, -1));
  const [inc, setInc] = useState<number | null>(income);
  const [spent, setSpent] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (inc === null || spent === null) return;
    setBusy(true);
    setError(null);
    try {
      setState(await api.checkIn({ month, income: inc, spending: spent }));
      setSpent(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save the check-in");
    } finally {
      setBusy(false);
    }
  }

  const trendText =
    pulse.trend === "behind"
      ? `You've been saving ${formatINR(Math.abs(pulse.averageGap!))} a month less than your plan assumes.`
      : pulse.trend === "ahead"
        ? `You've been saving ${formatINR(pulse.averageGap!)} a month more than your plan assumes.`
        : pulse.trend === "on_plan"
          ? "Your recent months match the plan."
          : "Record what actually came in and went out each month to see whether the plan is holding.";

  return (
    <section
      id="pulse"
      className="flex scroll-mt-24 flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-6"
      aria-labelledby="pulse-h"
    >
      <div className="flex flex-wrap items-center gap-3">
        <CalendarCheck className="size-5 text-brand-600" aria-hidden />
        <h2 id="pulse-h" className="text-[16px] font-bold">
          Monthly check-in
        </h2>
        {pulse.streak > 1 ? (
          <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-[12px] font-semibold text-brand-700">
            {pulse.streak}-month streak
          </span>
        ) : null}
        {pulse.due ? (
          <span className="rounded-full bg-caution-50 px-2.5 py-0.5 text-[12px] font-semibold text-caution-text">
            Due
          </span>
        ) : null}
      </div>
      <p className="text-[14px] text-pretty text-ink-700">
        {trendText}
        {pulse.trend === "behind" || pulse.trend === "ahead" ? (
          pulse.ifContinues.length ? (
            <>
              {" "}
              If that continues:{" "}
              {pulse.ifContinues
                .map((c) =>
                  c.after.achievedMonth
                    ? `${c.name} moves to ${fmtMonth(c.after.achievedMonth)}`
                    : `${c.name} goes out of reach`,
                )
                .join("; ")}
              .
            </>
          ) : pulse.freeMonthly ? (
            <>
              {" "}
              Your goals still land on time; your spare money after goals would be{" "}
              {formatINR(pulse.freeMonthly.ifContinues)} a month instead of{" "}
              {formatINR(pulse.freeMonthly.now)}.
            </>
          ) : null
        ) : null}
      </p>

      <form
        className="grid items-end gap-3 sm:grid-cols-[150px_1fr_1fr_auto]"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Field label="Month" htmlFor="ci-month">
          <input
            id="ci-month"
            type="month"
            className={inputClass}
            max={startMonth}
            value={month}
            onChange={(e) => e.target.value && setMonth(e.target.value)}
          />
        </Field>
        <MoneyInput label="Take-home received" value={inc} onChange={setInc} />
        <MoneyInput
          label="Total spent (incl. EMIs)"
          value={spent}
          onChange={setSpent}
          placeholder="e.g. 95,000"
        />
        <Button
          type="submit"
          disabled={busy || inc === null || spent === null}
          className="mb-[22px]"
        >
          {busy ? <Loader2 className="animate-spin" /> : <Plus />} Check in
        </Button>
      </form>
      {error ? <Notice tone="error">{error}</Notice> : null}

      {pulse.entries.length ? (
        <div className="overflow-x-auto">
          <table className="tabular w-full min-w-[480px] text-[13.5px]">
            <thead className="text-left text-[12px] text-ink-500">
              <tr className="border-b border-line">
                <th className="py-2 font-medium">Month</th>
                <th className="py-2 text-right font-medium">Saved</th>
                <th className="py-2 text-right font-medium">Plan expects</th>
                <th className="py-2 text-right font-medium">Difference</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {pulse.entries.slice(0, 12).map((e) => (
                <tr key={e.month} className="border-b border-line last:border-0">
                  <td className="py-2">
                    {fmtMonth(e.month)}
                    {e.note ? (
                      <span className="ml-2 text-[12px] text-ink-400">{e.note}</span>
                    ) : null}
                  </td>
                  <td className={cn("py-2 text-right", e.saved < 0 && "text-danger-text")}>
                    {formatINR(e.saved)}
                  </td>
                  <td className="py-2 text-right text-ink-500">{formatINR(e.expected)}</td>
                  <td
                    className={cn(
                      "py-2 text-right font-medium",
                      e.gap < 0 ? "text-caution-text" : "text-brand-700",
                    )}
                  >
                    {e.gap > 0 ? "+" : ""}
                    {formatINR(e.gap)}
                  </td>
                  <td className="py-2 text-right">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove the check-in for ${fmtMonth(e.month)}`}
                      onClick={async () => setState(await api.removeCheckIn(e.month))}
                    >
                      <Trash2 />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
