"use client";

import { ArrowRight, Check, Crosshair, Loader2, ShieldAlert, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import type { AgentEvent, OddsSummary, StrategyRun } from "@/lib/personal/agents/types";
import { api, findBetterPlan } from "@/lib/personal/client";
import type { RiskDriver, SpendRoom } from "@/lib/personal/finance/montecarlo";
import { cn } from "@/lib/utils";

import { AgentTimeline } from "./agent-activity";
import { PulseMark } from "./kit";
import { usePersonal } from "./provider";
import { Notice } from "./ui";

export const pct = (x: number) => `${Math.round(x * 100)}%`;

export function oddsTone(x: number) {
  return x >= 0.8
    ? {
        label: "Likely to work",
        text: "text-brand-700",
        chip: "bg-brand-50 text-brand-700",
        bar: "bg-brand-600",
      }
    : x >= 0.5
      ? {
          label: "Uncertain",
          text: "text-caution-text",
          chip: "bg-caution-50 text-caution-text",
          bar: "bg-caution-500",
        }
      : {
          label: "Unlikely to work",
          text: "text-danger-text",
          chip: "bg-danger-50 text-danger-text",
          bar: "bg-danger-500",
        };
}

/** A goal's chance of landing on time, with the within-a-year figure for context. */
export function ChanceBar({
  onTime,
  withinYear,
  name,
}: {
  onTime: number;
  withinYear: number;
  name: string;
}) {
  const t = oddsTone(onTime);
  return (
    <div className="flex items-center gap-3">
      <div
        className="h-2 flex-1 overflow-hidden rounded-full bg-surface-sunken"
        role="meter"
        aria-label={`${name}: chance of landing on time`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(onTime * 100)}
      >
        <div className={cn("h-full rounded-full", t.bar)} style={{ width: `${onTime * 100}%` }} />
      </div>
      <span className="tabular text-[12.5px] whitespace-nowrap text-ink-700">
        <span className={cn("font-semibold", t.text)}>{pct(onTime)}</span> on time ·{" "}
        {pct(withinYear)} within a year
      </span>
    </div>
  );
}

// ---------------------------------------------------------------- risks & room

export function RiskInsights({ planKey }: { planKey: string }) {
  const [data, setData] = useState<{ key: string; drivers: RiskDriver[]; room: SpendRoom } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .insights()
      .then((r) => live && r && setData({ key: planKey, ...r }))
      .catch((e) => live && setError(e instanceof Error ? e.message : "Couldn't load"));
    return () => {
      live = false;
    };
  }, [planKey]);
  const ready = data?.key === planKey ? data : null;
  if (error) return <Notice tone="error">{error}</Notice>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section
        className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-5"
        aria-labelledby="risks-h"
      >
        <h2 id="risks-h" className="text-[15px] font-bold">
          What could knock it off course
        </h2>
        {!ready ? (
          <Pending text="Re-running the futures with each risk switched off…" />
        ) : (
          <ul className="flex flex-col gap-2.5">
            {ready.drivers.map((d) => {
              // Fixed scale (20 points = full bar), so a small cost looks small.
              const share = Math.min(1, d.scoreCost / 0.2);
              return (
                <li key={d.id} className="flex flex-col gap-1">
                  <div className="flex items-baseline justify-between gap-3 text-[13.5px]">
                    <span className="text-ink-900">{d.label}</span>
                    <span className="tabular text-[12.5px] text-ink-500">
                      {d.scoreCost < 0.005
                        ? "barely matters"
                        : `costs ${Math.round(d.scoreCost * 100)} pts`}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-surface-sunken" aria-hidden>
                    <div
                      className="h-full rounded-full bg-ink-700"
                      style={{ width: `${d.scoreCost < 0.005 ? 0 : Math.max(3, share * 100)}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        <p className="text-[12px] text-ink-400">
          Points of plan score (0–100: each goal&apos;s chance of landing on time, top goals
          weighted most) lost to each risk, measured on the same futures with that risk switched
          off.
        </p>
      </section>
      <section
        className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-5"
        aria-labelledby="room-h"
      >
        <h2 id="room-h" className="text-[15px] font-bold">
          Room to spend
        </h2>
        {!ready ? (
          <Pending text="Searching for the spending level that keeps 80% confidence…" />
        ) : ready.room.kind === "spare" ? (
          <>
            <p className="tabular font-display text-[26px] font-extrabold text-brand-700">
              {formatINR(ready.room.monthly)}
              <span className="text-[14px] font-semibold text-ink-500"> a month</span>
            </p>
            <p className="text-[13.5px] text-pretty text-ink-700">
              You could spend this much more each month and every goal would still land on time in
              at least {pct(ready.room.target)} of futures (today: {pct(ready.room.current)}).
            </p>
          </>
        ) : ready.room.kind === "cut" ? (
          <>
            <p className="tabular font-display text-[26px] font-extrabold text-caution-text">
              −{formatINR(ready.room.monthly)}
              <span className="text-[14px] font-semibold text-ink-500"> a month</span>
            </p>
            <p className="text-[13.5px] text-pretty text-ink-700">
              Spending this much less each month would lift the chance of every goal landing on time
              from {pct(ready.room.current)} to {pct(ready.room.target)}.
            </p>
          </>
        ) : (
          <p className="text-[13.5px] text-pretty text-ink-700">
            Even spending 60% less wouldn&apos;t get every goal to {pct(ready.room.target)} — the
            plan needs different dates or budgets. Ask the Strategist below.
          </p>
        )}
      </section>
    </div>
  );
}

function Pending({ text }: { text: string }) {
  return (
    <p className="flex items-center gap-2 text-[13px] text-ink-500">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {text}
    </p>
  );
}

// ---------------------------------------------------------------- strategist

export function StrategistPanel({
  latest,
  disabled,
}: {
  latest: StrategyRun | null;
  disabled?: string;
}) {
  const { setState, refresh } = usePersonal();
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState<StrategyRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deciding, setDeciding] = useState(false);
  const shown = run ?? latest;

  async function search() {
    setRunning(true);
    setError(null);
    setEvents([]);
    setRun(null);
    try {
      await findBetterPlan((item) => {
        if (item.type === "event") setEvents((e) => [...e, item.event]);
        else if (item.type === "strategy") setRun(item.run);
        else setError(item.message);
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The search failed");
    } finally {
      setRunning(false);
    }
  }

  async function decide(action: "apply" | "dismiss") {
    if (!shown) return;
    setDeciding(true);
    setError(null);
    try {
      setState(await api.decideStrategy(shown.id, action));
      setRun(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save your decision");
    } finally {
      setDeciding(false);
    }
  }

  const liveEvents = running ? events : (shown?.events ?? []);
  const p = shown?.proposal;
  return (
    <section
      className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs sm:p-6"
      aria-labelledby="strat-h"
    >
      <div className="flex flex-wrap items-start gap-3">
        <PulseMark active={running} />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h2 id="strat-h" className="text-[16px] font-bold">
            Make the plan more likely to work
          </h2>
          <p className="text-[13px] text-pretty text-ink-500">
            The Strategist agent tries concrete changes — dates, budgets, down payments, loan
            tenures, priorities, spending — scores each on the same 1,000 futures, and proposes the
            smallest set that helps most. Nothing changes until you apply it.
          </p>
        </div>
        <Button onClick={search} disabled={running || !!disabled} title={disabled}>
          {running ? <Loader2 className="animate-spin" /> : <Crosshair />}{" "}
          {running ? "Searching…" : shown ? "Search again" : "Find a better plan"}
        </Button>
      </div>
      {disabled && !shown ? <p className="text-[13px] text-ink-500">{disabled}</p> : null}
      {error ? <Notice tone="error">{error}</Notice> : null}

      {liveEvents.length ? (
        <div className="rounded-xl border border-line p-4">
          <AgentTimeline events={liveEvents} running={running} expandable />
        </div>
      ) : null}

      {!running && shown?.status === "completed" && !p ? (
        <Notice tone="info" title="No change was worth making">
          The search didn&apos;t find a change that improves the odds by more than it disrupts the
          plan.
          {shown.drivers[0] && shown.drivers[0].scoreCost >= 0.02
            ? ` The biggest risk is ${shown.drivers[0].label.toLowerCase()}.`
            : ""}
        </Notice>
      ) : null}

      {!running && p ? (
        <ProposalView
          proposal={p}
          decision={shown!.decision}
          busy={deciding}
          onApply={() => decide("apply")}
          onDismiss={() => decide("dismiss")}
        />
      ) : null}
    </section>
  );
}

function ProposalView({
  proposal: p,
  decision,
  busy,
  onApply,
  onDismiss,
}: {
  proposal: NonNullable<StrategyRun["proposal"]>;
  decision: StrategyRun["decision"];
  busy: boolean;
  onApply: () => void;
  onDismiss: () => void;
}) {
  const before = new Map(p.before.goals.map((g) => [g.id, g]));
  return (
    <div className="flex flex-col gap-4 rounded-xl border border-brand-600/40 bg-brand-50/40 p-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span className="text-[13px] font-semibold text-ink-700">Every goal on time</span>
        <span className="tabular flex items-center gap-2 font-display text-[22px] font-extrabold">
          <span className={oddsTone(p.before.allOnTime).text}>{pct(p.before.allOnTime)}</span>
          <ArrowRight className="size-5 text-ink-400" aria-hidden />
          <span className={oddsTone(p.after.allOnTime).text}>{pct(p.after.allOnTime)}</span>
        </span>
        <span className="text-[12px] text-ink-500">
          checked on {p.after.paths.toLocaleString("en-IN")} fresh futures · {p.evaluations}{" "}
          simulations in the search
        </span>
      </div>
      <ol className="flex flex-col gap-2">
        {p.changes.map((c, i) => (
          <li key={i} className="flex gap-3 text-[14px] text-ink-900">
            <span className="tabular flex size-6 shrink-0 items-center justify-center rounded-full bg-ink-900 text-[12px] font-bold text-white">
              {i + 1}
            </span>
            {c.text}
          </li>
        ))}
      </ol>
      <ul className="grid gap-1.5 text-[13px] sm:grid-cols-2">
        {p.after.goals.map((g) => {
          const b = before.get(g.id);
          return (
            <li key={g.id} className="flex justify-between gap-3 rounded-lg bg-surface px-3 py-2">
              <span className="truncate text-ink-700">{g.name}</span>
              <span className="tabular whitespace-nowrap">
                {b ? pct(b.onTime) : "—"} →{" "}
                <span className={cn("font-semibold", oddsTone(g.onTime).text)}>
                  {pct(g.onTime)}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      {decision === "pending" ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onApply} disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : <Check />} Apply to my plan
          </Button>
          <Button variant="ghost" onClick={onDismiss} disabled={busy}>
            <X /> Dismiss
          </Button>
          <span className="text-[12px] text-ink-500">
            {p.spendingCut > 0
              ? `Applying also records a commitment to spend ${formatINR(p.spendingCut)} less a month; check-ins track it.`
              : "Applying updates the goals above; you can change them again any time."}
          </span>
        </div>
      ) : (
        <p className="flex items-center gap-1.5 text-[13px] font-medium text-ink-700">
          {decision === "applied" ? (
            <>
              <Check className="size-4 text-brand-600" aria-hidden /> Applied to your plan.
            </>
          ) : (
            <>
              <ShieldAlert className="size-4 text-ink-400" aria-hidden /> Dismissed — your plan was
              left as it was.
            </>
          )}
        </p>
      )}
    </div>
  );
}

/** The headline: the chance the whole plan works, with what it's based on. */
export function OddsHeadline({
  odds,
  updating,
  goals,
}: {
  odds: OddsSummary;
  updating?: boolean;
  goals: number;
}) {
  const t = oddsTone(odds.allOnTime);
  return (
    <div
      className={cn("flex flex-col gap-1 transition-opacity", updating && "opacity-60")}
      aria-live="polite"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="health-h" className="text-[20px] leading-snug font-extrabold sm:text-[22px]">
          <span className={cn("tabular", t.text)}>{pct(odds.allOnTime)}</span> chance{" "}
          {goals === 1 ? "your goal lands" : `all ${goals} goals land`} on time
        </h2>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-[12px] font-semibold whitespace-nowrap",
            t.chip,
          )}
        >
          {t.label}
        </span>
        {updating ? (
          <Loader2 className="size-4 animate-spin text-ink-400" aria-label="Updating" />
        ) : null}
      </div>
      <p className="text-[13px] text-ink-500">
        Across {odds.paths.toLocaleString("en-IN")} simulated futures with market swings, inflation,
        uneven raises, job loss and emergencies. Money never runs out in {pct(odds.neverShort)} of
        them.
      </p>
    </div>
  );
}
