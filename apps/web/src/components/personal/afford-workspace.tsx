"use client";

import {
  ArrowLeft,
  Briefcase,
  Car,
  GraduationCap,
  Home,
  Loader2,
  Pencil,
  ShoppingBag,
  Wand2,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import type { AgentEvent, WorkflowRun } from "@/lib/personal/agents/types";
import { analyze, api } from "@/lib/personal/client";
import { inrWords } from "@/lib/personal/finance/parse-inr";
import { interpretGoal } from "@/lib/personal/goal";
import {
  DEMO_PURCHASE,
  type ProfileValues,
  type PurchaseRequest,
  type PurchaseType,
} from "@/lib/personal/schemas";
import { cn } from "@/lib/utils";

import { AgentTimeline, EventFeed } from "./agent-activity";
import { Field, MoneyInput, NumberInput } from "./fields";
import { GoalInput } from "./goal-input";
import { usePersonal } from "./provider";
import { RunResults } from "./results";
import { AgentGlyph, Chip, Kicker, PulseMark } from "./kit";
import { Disclosure, Loading, ModeStrip, Notice, SourceBadge } from "./ui";

const TYPES: { id: PurchaseType; label: string; icon: typeof Home; noun: string }[] = [
  { id: "house", label: "House", icon: Home, noun: "house" },
  { id: "car", label: "Car", icon: Car, noun: "car" },
  { id: "education", label: "Education", icon: GraduationCap, noun: "education" },
  { id: "business", label: "Business", icon: Briefcase, noun: "business" },
  { id: "custom", label: "Something else", icon: ShoppingBag, noun: "purchase" },
];

type HouseholdForm = Pick<
  ProfileValues,
  "monthlyIncome" | "monthlyExpenses" | "liquidSavings" | "existingEmis" | "otherMonthlyObligations"
>;
const HOUSEHOLD_FIELDS: {
  key: keyof HouseholdForm;
  question: string;
  label: string;
  required: boolean;
  placeholder?: string;
}[] = [
  {
    key: "monthlyIncome",
    label: "Take-home pay",
    question: "How much do you take home each month?",
    required: true,
  },
  {
    key: "monthlyExpenses",
    label: "Living expenses",
    question: "What do you spend in a typical month?",
    required: true,
    placeholder: "rent, food, bills, travel…",
  },
  {
    key: "liquidSavings",
    label: "Savings you can use",
    question: "How much could you use from savings?",
    required: true,
    placeholder: "bank, FDs, liquid funds",
  },
  {
    key: "existingEmis",
    label: "Current EMIs",
    question: "Do you pay any EMIs now? (monthly total)",
    required: true,
    placeholder: "0 if none",
  },
  {
    key: "otherMonthlyObligations",
    label: "Insurance & other fixed costs",
    question: "Insurance premiums or other fixed monthly costs?",
    required: false,
    placeholder: "optional",
  },
];

const BLANK: PurchaseRequest = {
  type: "house",
  label: "",
  price: 0,
  downPaymentPct: null,
  upfrontCosts: null,
  financeUpfrontCosts: false,
  interestRate: null,
  tenureMonths: null,
  monthlyOwnershipCost: null,
  researchFinancing: true,
};

const noun = (t: PurchaseType) => TYPES.find((x) => x.id === t)!.noun;
const labelFor = (p: PurchaseRequest) => (p.price ? `${inrWords(p.price)} ${noun(p.type)}` : "");

type Stage = "goal" | "details" | "running" | "result";

export function AffordWorkspace() {
  const { state, setState, refresh } = usePersonal();
  const router = useRouter();
  const params = useSearchParams();
  const runParam = params.get("run");
  const goalParam = params.get("goal");

  const [stage, setStage] = useState<Stage>(runParam ? "result" : goalParam ? "details" : "goal");
  const [goalText, setGoalText] = useState(goalParam ?? "");
  const [understood, setUnderstood] = useState<string[]>([]);
  const [purchase, setPurchase] = useState<PurchaseRequest>(BLANK);
  const [household, setHousehold] = useState<HouseholdForm | null>(null);
  const [editFinances, setEditFinances] = useState(false);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seededGoal, setSeededGoal] = useState<string | null>(null);
  const top = useRef<HTMLDivElement>(null);

  function applyGoal(text: string) {
    const g = interpretGoal(text);
    setGoalText(text);
    setUnderstood(g.understood);
    setPurchase((p) => {
      const next: PurchaseRequest = {
        ...p,
        type: g.type ?? p.type,
        price: g.price ?? p.price,
        downPaymentPct: g.downPaymentPct ?? p.downPaymentPct,
        tenureMonths: g.tenureMonths ?? p.tenureMonths,
        interestRate: g.interestRate ?? p.interestRate,
      };
      return { ...next, label: labelFor(next) };
    });
    setStage("details");
  }

  // Seed the household answers from the saved profile once it loads.
  const v = state?.profile.values;
  if (v && household === null) {
    setHousehold({
      monthlyIncome: v.monthlyIncome,
      monthlyExpenses: v.monthlyExpenses,
      liquidSavings: v.liquidSavings,
      existingEmis: v.existingEmis,
      otherMonthlyObligations: v.otherMonthlyObligations,
    });
  }

  // A goal from the URL (the home-page box) is read once with the rule-based interpreter.
  if (goalParam && seededGoal !== goalParam) {
    setSeededGoal(goalParam);
    applyGoal(goalParam);
  }

  // Show a stored analysis when linked (?run=…).
  useEffect(() => {
    if (!runParam || run?.id === runParam) return;
    let cancelled = false;
    api.run(runParam).then(
      (r) => {
        if (cancelled) return;
        setRun(r);
        setEvents(r.events);
        setPurchase(r.request);
        setGoalText(r.goal);
        setStage(r.status === "needs_input" ? "details" : "result");
      },
      () => {
        if (cancelled) return;
        setError("That analysis is no longer available (analyses are kept in server memory).");
        setStage("goal");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [runParam, run?.id]);

  const update = (patch: Partial<PurchaseRequest>) =>
    setPurchase((p) => {
      const next = { ...p, ...patch };
      return { ...next, label: labelFor(next) };
    });

  async function useDemo() {
    setError(null);
    try {
      const s = await api.loadDemo();
      setState(s);
      const dv = s.profile.values;
      setHousehold({
        monthlyIncome: dv.monthlyIncome,
        monthlyExpenses: dv.monthlyExpenses,
        liquidSavings: dv.liquidSavings,
        existingEmis: dv.existingEmis,
        otherMonthlyObligations: dv.otherMonthlyObligations,
      });
      setPurchase(DEMO_PURCHASE);
      setGoalText("I want to buy a ₹75 lakh house");
      setUnderstood(["Purchase type: house", "Price: ₹75 lakh"]);
      setEditFinances(false);
      setStage("details");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load the demo");
    }
  }

  function startOver() {
    router.replace("/afford", { scroll: false });
    setRun(null);
    setEvents([]);
    setGoalText("");
    setUnderstood([]);
    setPurchase(BLANK);
    setStage("goal");
  }

  async function start() {
    if (!purchase.price || purchase.price < 1000) {
      setError("Tell us how much it costs.");
      return;
    }
    setError(null);
    setStage("running");
    setEvents([]);
    setRun(null);
    top.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const label = purchase.label || labelFor(purchase);
    const profile: Partial<ProfileValues> = {};
    if (household)
      for (const [k, val] of Object.entries(household))
        if (val !== null) (profile as Record<string, number>)[k] = val;
    let finalRun: WorkflowRun | null = null;
    try {
      await analyze(
        {
          goal: goalText.trim() || `Can I afford a ${label}?`,
          purchase: { ...purchase, label },
          profile,
        },
        (item) => {
          if (item.type === "event") setEvents((e) => [...e, item.event]);
          else if (item.type === "run") {
            finalRun = item.run;
            setRun(item.run);
            router.replace(`/afford?run=${item.run.id}`, { scroll: false });
          } else if (item.type === "error") setError(item.message);
        },
      );
      await refresh();
      const r = finalRun as WorkflowRun | null;
      if (r?.status === "needs_input") setEditFinances(true);
      setStage(r && r.status !== "needs_input" ? "result" : "details");
    } catch (e) {
      setError(e instanceof Error ? e.message : "The analysis couldn't start");
      setStage("details");
    }
  }

  if (!state || !household) return <Loading label="Loading your profile…" />;
  const missing = new Set(run?.status === "needs_input" ? run.missing.map((m) => m.field) : []);
  const plan = run?.actionPlanId
    ? state.actionPlans.find((p) => p.id === run.actionPlanId)
    : undefined;
  const sources = state.profile.sources;
  const financesComplete = HOUSEHOLD_FIELDS.filter((f) => f.required).every(
    (f) => household[f.key] !== null,
  );
  const showFinanceInputs = editFinances || !financesComplete;

  const liveTools = events.filter((e) => e.kind === "tool_result").length;
  const livePlan = events.find((e) => e.kind === "plan_created")?.plan ?? [];
  const liveDone = events.filter((e) => e.kind === "step_completed").length;

  return (
    <div ref={top} className="flex scroll-mt-20 flex-col gap-6">
      {stage === "goal" ? (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-10">
          <div className="flex flex-col gap-6 pt-2">
            <div className="flex flex-col gap-2">
              <Kicker>Purchase intelligence</Kicker>
              <h1 className="text-[30px] leading-[1.1] font-extrabold text-balance sm:text-[40px]">
                Can I afford this?
              </h1>
              <p className="max-w-xl text-[16px] leading-relaxed text-pretty text-ink-500">
                Describe what you want to buy. FinPulse&apos;s agents check your finances, work out
                the real costs, test what could go wrong and prepare next steps — you stay in
                control.
              </p>
            </div>
            {error ? <Notice tone="error">{error}</Notice> : null}
            <GoalInput autoFocus onSubmit={applyGoal} />
            <ModeStrip status={state.status} />
          </div>
          <aside className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-5 shadow-xs">
            <div className="flex items-center gap-3">
              <PulseMark size="sm" />
              <div>
                <h2 className="text-[15px] font-bold">What happens when you ask</h2>
                <p className="text-[12px] text-ink-500">
                  The plan FinPulse&apos;s orchestrator runs
                </p>
              </div>
            </div>
            <ol className="flex flex-col gap-3">
              {(
                [
                  ["planner", "Understands your goal and checks your profile"],
                  ["research", "Finds financing options (live or labelled estimates)"],
                  ["analysis", "Calculates EMI, costs and cash flow"],
                  ["risk", "Stress-tests six things that could go wrong"],
                  ["verification", "Challenges assumptions and flags gaps"],
                  ["action", "Prepares next steps for your approval"],
                ] as const
              ).map(([agent, text]) => (
                <li key={agent} className="flex items-center gap-3 text-[13.5px] text-ink-700">
                  <AgentGlyph agent={agent} size="sm" />
                  {text}
                </li>
              ))}
            </ol>
            <div className="flex flex-col gap-2 rounded-xl bg-surface-sunken p-3.5">
              <p className="text-[13px] text-ink-700">
                New here? See it work on a fictional person buying a ₹75 lakh house.
              </p>
              <Button variant="outline" size="sm" onClick={useDemo} className="w-fit">
                <Wand2 /> Try the demo
              </Button>
            </div>
          </aside>
        </div>
      ) : null}

      {stage === "details" ? (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="flex min-w-0 flex-col gap-5">
            <button
              type="button"
              onClick={() => setStage("goal")}
              className="flex min-h-9 w-fit items-center gap-1 text-[13px] font-medium text-ink-500 hover:text-ink-900"
            >
              <ArrowLeft className="size-4" /> Change goal
            </button>
            <div className="flex flex-col gap-1.5">
              <Kicker>Step 1 of 2 · Confirm the details</Kicker>
              <h1 className="text-[26px] leading-tight font-extrabold text-balance sm:text-[32px]">
                {purchase.price
                  ? `Let's check a ${inrWords(purchase.price)} ${noun(purchase.type)}`
                  : "Let's check your goal"}
              </h1>
              {goalText ? (
                <p className="text-[14px] text-pretty text-ink-500">
                  You said “{goalText}”
                  {understood.length
                    ? ` — understood ${understood.join(", ").toLowerCase()}.`
                    : "."}
                </p>
              ) : null}
            </div>

            {run?.status === "needs_input" ? (
              <Notice tone="warning" title="A little more is needed for a reliable answer">
                FinPulse doesn&apos;t guess your personal figures. Please answer the highlighted
                questions.
              </Notice>
            ) : null}

            <section className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-5 shadow-xs">
              <h2 className="text-[16px] font-bold">What do you want to buy?</h2>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Purchase type">
                {TYPES.map((t) => (
                  <Chip
                    key={t.id}
                    icon={t.icon}
                    selected={purchase.type === t.id}
                    onClick={() => update({ type: t.id })}
                  >
                    {t.label}
                  </Chip>
                ))}
              </div>
              <MoneyInput
                label="How much does it cost?"
                required
                highlight={!purchase.price}
                value={purchase.price || null}
                onChange={(p) => update({ price: p ?? 0 })}
                placeholder="e.g. 75 lakh"
              />
            </section>

            <section className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-5 shadow-xs">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-[16px] font-bold">Your finances</h2>
                {!showFinanceInputs ? (
                  <Button variant="ghost" size="sm" onClick={() => setEditFinances(true)}>
                    <Pencil /> Edit
                  </Button>
                ) : null}
              </div>
              {showFinanceInputs ? (
                <>
                  {!financesComplete && !state.profile.updatedAt ? (
                    <Notice
                      tone="info"
                      title="Just exploring?"
                      action={
                        <Button variant="outline" size="sm" onClick={useDemo}>
                          Use demo
                        </Button>
                      }
                    >
                      Fill in a fictional person&apos;s figures in one click.
                    </Notice>
                  ) : null}
                  <div className="grid gap-4 sm:grid-cols-2">
                    {HOUSEHOLD_FIELDS.map((f) => (
                      <MoneyInput
                        key={f.key}
                        label={f.question}
                        required={f.required}
                        highlight={
                          missing.has(f.key) ||
                          (f.required && run?.status === "needs_input" && household[f.key] === null)
                        }
                        value={household[f.key]}
                        onChange={(x) => setHousehold({ ...household, [f.key]: x })}
                        placeholder={f.placeholder}
                        badge={sources[f.key] ? <SourceBadge kind={sources[f.key]!.kind} /> : null}
                      />
                    ))}
                  </div>
                  <p className="text-[12px] text-ink-500">
                    Saved to your profile as figures you entered. FinPulse never asks for bank
                    passwords, PINs or OTPs.
                  </p>
                </>
              ) : (
                <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
                  {HOUSEHOLD_FIELDS.filter((f) => household[f.key] !== null).map((f) => (
                    <div key={f.key} className="flex flex-col gap-1">
                      <dt className="flex flex-wrap items-center gap-1.5 text-[12px] text-ink-500">
                        {f.label}
                        {sources[f.key] ? <SourceBadge kind={sources[f.key]!.kind} /> : null}
                      </dt>
                      <dd className="tabular font-display text-[17px] font-bold">
                        {formatINR(household[f.key])}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </section>

            <Disclosure
              title="Loan and cost details"
              hint="Optional — blanks use clearly labelled estimates"
            >
              <div className="flex flex-col gap-5">
                <Field label="Down payment">
                  <div className="flex flex-wrap gap-2">
                    {[10, 20, 30, 50].map((d) => (
                      <Chip
                        key={d}
                        selected={purchase.downPaymentPct === d}
                        onClick={() => update({ downPaymentPct: d })}
                      >
                        {d}%
                      </Chip>
                    ))}
                    <Chip
                      selected={purchase.downPaymentPct === null}
                      onClick={() => update({ downPaymentPct: null })}
                    >
                      Not sure
                    </Chip>
                  </div>
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <NumberInput
                    label="Interest rate"
                    suffix="% a year"
                    min={0}
                    max={50}
                    step={0.05}
                    value={purchase.interestRate}
                    onChange={(r) => update({ interestRate: r })}
                    placeholder="Leave blank to research"
                    hint="Have a quote? Enter it. Otherwise FinPulse estimates it."
                  />
                  <NumberInput
                    label="Loan tenure"
                    suffix="years"
                    min={1}
                    max={50}
                    value={purchase.tenureMonths === null ? null : purchase.tenureMonths / 12}
                    onChange={(y) =>
                      update({ tenureMonths: y === null ? null : Math.max(1, Math.round(y * 12)) })
                    }
                    placeholder="typical for this loan"
                  />
                  <MoneyInput
                    label="One-time costs (stamp duty, fees…)"
                    value={purchase.upfrontCosts}
                    onChange={(u) => update({ upfrontCosts: u })}
                    placeholder="blank = labelled estimate"
                  />
                  <MoneyInput
                    label="Running costs per month"
                    value={purchase.monthlyOwnershipCost}
                    onChange={(m) => update({ monthlyOwnershipCost: m })}
                    placeholder="maintenance, insurance, fuel…"
                  />
                </div>
                <label className="flex min-h-10 items-center gap-3 text-[14px]">
                  <input
                    type="checkbox"
                    checked={purchase.financeUpfrontCosts}
                    onChange={(e) => update({ financeUpfrontCosts: e.target.checked })}
                    className="size-4 accent-[var(--brand-600)]"
                  />
                  Add one-time costs to the loan instead of paying them upfront
                </label>
                <label className="flex min-h-10 items-center gap-3 text-[14px]">
                  <input
                    type="checkbox"
                    checked={purchase.researchFinancing}
                    onChange={(e) => update({ researchFinancing: e.target.checked })}
                    className="size-4 accent-[var(--brand-600)]"
                  />
                  Compare financing options for me
                </label>
              </div>
            </Disclosure>
          </div>

          <aside className="sticky bottom-[calc(4.5rem+env(safe-area-inset-bottom))] z-10 flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-md lg:top-6 lg:bottom-auto lg:p-5 lg:shadow-xs">
            <div className="hidden flex-col gap-3 lg:flex">
              <h2 className="text-[15px] font-bold">Ready to analyse</h2>
              <dl className="flex flex-col gap-2 text-[13.5px]">
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-500">Goal</dt>
                  <dd className="text-right font-semibold">{purchase.label || "—"}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-500">Your finances</dt>
                  <dd
                    className={cn(
                      "font-semibold",
                      financesComplete ? "text-brand-700" : "text-caution-text",
                    )}
                  >
                    {financesComplete ? "Complete" : "Missing figures"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-ink-500">Rate</dt>
                  <dd className="font-semibold">
                    {purchase.interestRate !== null
                      ? `${purchase.interestRate}%`
                      : "FinPulse researches"}
                  </dd>
                </div>
              </dl>
              <p className="text-[12px] leading-snug text-ink-500">
                6 agents will run about a dozen calculation and research tools. You&apos;ll see each
                step as it happens.
              </p>
            </div>
            {error ? <Notice tone="error">{error}</Notice> : null}
            <Button size="lg" onClick={start} className="w-full">
              Check if I can afford it
            </Button>
            <p className="text-center text-[12px] text-ink-500">
              Takes a few seconds. Nothing is submitted anywhere.
            </p>
          </aside>
        </div>
      ) : null}

      {stage === "running" ? (
        <div className="mx-auto flex w-full max-w-2xl flex-col gap-5 pt-2">
          <div className="flex items-center gap-4">
            <PulseMark size="lg" active />
            <div className="flex flex-col gap-0.5">
              <Kicker>Step 2 of 2 · Agents at work</Kicker>
              <h1 className="text-[22px] leading-tight font-extrabold text-balance sm:text-[26px]">
                Checking your {purchase.label || "purchase"}
              </h1>
              <p className="tabular text-[13px] text-ink-500" aria-live="polite">
                {livePlan.length
                  ? `${liveDone} of ${livePlan.length} stages done · ${liveTools} tool calls so far`
                  : "Starting the orchestrator…"}
              </p>
            </div>
          </div>
          <section className="rounded-2xl border border-line bg-surface p-5 shadow-sm">
            {events.length ? (
              <AgentTimeline events={events} running />
            ) : (
              <p className="flex items-center gap-2 text-[14px] text-ink-500">
                <Loader2 className="size-4 animate-spin" /> Starting…
              </p>
            )}
          </section>
          <p className="text-[12px] text-ink-500">
            Each stage turns green only when the server reports it finished. Expand a stage to see
            the tools it called.
          </p>
          <Disclosure title="Technical log" hint="Every event as it happens">
            <EventFeed events={events} />
          </Disclosure>
        </div>
      ) : null}

      {stage === "result" ? (
        run?.status === "completed" ? (
          <RunResults run={run} plan={plan} onEdit={() => setStage("details")} onNew={startOver} />
        ) : run?.status === "failed" ? (
          <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
            <Notice tone="error" title="We couldn't finish this analysis">
              {run.error} The stages below show exactly what ran.
            </Notice>
            <section className="rounded-2xl border border-line bg-surface p-5 shadow-xs">
              <AgentTimeline events={events} running={false} />
            </section>
            <Button onClick={() => setStage("details")} className="w-fit">
              Try again
            </Button>
          </div>
        ) : (
          <Loading label="Loading the analysis…" />
        )
      ) : null}
    </div>
  );
}
