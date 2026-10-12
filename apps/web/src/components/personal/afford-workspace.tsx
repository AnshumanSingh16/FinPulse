"use client";

import {
  Briefcase,
  Car,
  GraduationCap,
  Home,
  Loader2,
  Play,
  ShoppingBag,
  Wand2,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type { AgentEvent, WorkflowRun } from "@/lib/personal/agents/types";
import { analyze, api } from "@/lib/personal/client";
import { inrWords } from "@/lib/personal/finance/parse-inr";
import {
  DEMO_PURCHASE,
  type ProfileValues,
  type PurchaseRequest,
  type PurchaseType,
} from "@/lib/personal/schemas";
import { cn } from "@/lib/utils";

import { EventFeed, PlanTracker } from "./agent-activity";
import { Field, MoneyInput, NumberInput } from "./fields";
import { usePersonal } from "./provider";
import { RunResults } from "./results";
import { Loading, ModeStrip, Notice, Section, SourceBadge, inputClass } from "./ui";

const TYPES: { id: PurchaseType; label: string; icon: typeof Home; noun: string }[] = [
  { id: "house", label: "House", icon: Home, noun: "house" },
  { id: "car", label: "Car", icon: Car, noun: "car" },
  { id: "education", label: "Education", icon: GraduationCap, noun: "education" },
  { id: "business", label: "Business", icon: Briefcase, noun: "business" },
  { id: "custom", label: "Custom", icon: ShoppingBag, noun: "purchase" },
];

type HouseholdForm = Pick<
  ProfileValues,
  "monthlyIncome" | "monthlyExpenses" | "liquidSavings" | "existingEmis" | "otherMonthlyObligations"
>;

const EMPTY_PURCHASE: PurchaseRequest = {
  type: "house",
  label: "",
  price: 0,
  downPaymentPct: 20,
  upfrontCosts: null,
  financeUpfrontCosts: false,
  interestRate: null,
  tenureMonths: null,
  monthlyOwnershipCost: null,
  researchFinancing: true,
};

function autoLabel(p: PurchaseRequest) {
  if (!p.price) return "";
  return `${inrWords(p.price)} ${TYPES.find((t) => t.id === p.type)!.noun}`;
}

export function AffordWorkspace() {
  const { state, setState, refresh } = usePersonal();
  const router = useRouter();
  const params = useSearchParams();
  const runParam = params.get("run");

  const [purchase, setPurchase] = useState<PurchaseRequest>(EMPTY_PURCHASE);
  const [labelEdited, setLabelEdited] = useState(false);
  const [household, setHousehold] = useState<HouseholdForm | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Prefill the household fields from the profile once it has loaded.
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

  // Show a stored run when linked (?run=…), otherwise the latest one.
  useEffect(() => {
    if (!runParam || run?.id === runParam) return;
    let cancelled = false;
    api.run(runParam).then(
      (r) => {
        if (cancelled) return;
        setRun(r);
        setEvents(r.events);
        setPurchase(r.request);
        setLabelEdited(true);
      },
      () =>
        !cancelled &&
        setError("That analysis is no longer available (data is kept in server memory)."),
    );
    return () => {
      cancelled = true;
    };
  }, [runParam, run?.id]);

  const update = (patch: Partial<PurchaseRequest>) =>
    setPurchase((p) => {
      const next = { ...p, ...patch };
      if (!labelEdited) next.label = autoLabel(next);
      return next;
    });

  async function tryDemo() {
    setError(null);
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
    setLabelEdited(false);
  }

  async function start() {
    if (!purchase.price || purchase.price < 1000) {
      setError("Enter the purchase price.");
      return;
    }
    setError(null);
    setRunning(true);
    setEvents([]);
    setRun(null);
    const label = purchase.label.trim() || autoLabel(purchase) || "Purchase";
    const profile: Partial<ProfileValues> = {};
    if (household)
      for (const [k, val] of Object.entries(household))
        if (val !== null) (profile as Record<string, number>)[k] = val;
    try {
      await analyze(
        { goal: `Can I afford a ${label}?`, purchase: { ...purchase, label }, profile },
        (item) => {
          if (item.type === "event") setEvents((e) => [...e, item.event]);
          else if (item.type === "run") {
            setRun(item.run);
            router.replace(`/afford?run=${item.run.id}`, { scroll: false });
          } else if (item.type === "error") setError(item.message);
        },
      );
      await refresh();
      setTimeout(
        () => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
        50,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "The analysis failed to start");
    } finally {
      setRunning(false);
    }
  }

  if (!state) return <Loading label="Loading your profile…" />;
  const missing = new Set(run?.status === "needs_input" ? run.missing.map((m) => m.field) : []);
  const plan = run?.actionPlanId
    ? state.actionPlans.find((p) => p.id === run.actionPlanId)
    : undefined;
  const sources = state.profile.sources;
  const srcBadge = (f: keyof HouseholdForm) =>
    sources[f] ? <SourceBadge kind={sources[f]!.kind} /> : null;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div className="flex flex-col gap-1">
          <div className="text-xs font-medium tracking-wide text-primary uppercase">
            Purchase intelligence
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Can I afford this?</h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Six agents plan the question, research financing, calculate the loan, stress-test it,
            verify your inputs and prepare next steps. Every figure comes from tested calculation
            tools.
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 md:items-end">
          <ModeStrip status={state.status} />
          <Button variant="outline" onClick={tryDemo} disabled={running}>
            <Wand2 /> Try Demo (fictional profile)
          </Button>
        </div>
      </header>

      {state.profile.isDemo ? (
        <Notice tone="info" title="Demo profile loaded">
          A fictional person: ₹2,00,000 take-home, ₹25 lakh savings, ₹70,000 expenses, ₹15,000 EMIs.
          The 8.5% rate and 20-year tenure are illustrative assumptions, not lender quotes. Edit
          anything and run again.
        </Notice>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Section title="What do you want to buy?">
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Purchase type">
            {TYPES.map((t) => (
              <button
                key={t.id}
                type="button"
                role="radio"
                aria-checked={purchase.type === t.id}
                onClick={() => update({ type: t.id })}
                className={cn(
                  "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition",
                  purchase.type === t.id
                    ? "border-primary bg-primary/10 text-primary"
                    : "text-muted-foreground hover:border-foreground/30 hover:text-foreground",
                )}
              >
                <t.icon className="size-4" /> {t.label}
              </button>
            ))}
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <MoneyInput
              label="Purchase price"
              required
              value={purchase.price || null}
              onChange={(p) => update({ price: p ?? 0 })}
              placeholder="e.g. 75 lakh"
            />
            <Field label="Name for this purchase" htmlFor="label">
              <input
                id="label"
                className={inputClass}
                value={purchase.label}
                placeholder="e.g. 2BHK in Pune"
                maxLength={80}
                onChange={(e) => {
                  setLabelEdited(true);
                  setPurchase((p) => ({ ...p, label: e.target.value }));
                }}
              />
            </Field>
            <NumberInput
              label="Down payment"
              suffix="%"
              min={0}
              max={100}
              value={purchase.downPaymentPct}
              onChange={(d) => update({ downPaymentPct: d })}
              placeholder="blank = typical default"
            />
            <MoneyInput
              label="Upfront costs (stamp duty, fees…)"
              value={purchase.upfrontCosts}
              onChange={(u) => update({ upfrontCosts: u })}
              placeholder="blank = disclosed estimate"
              hint="Leave blank and FinPulse uses a labelled estimate"
            />
            <NumberInput
              label="Interest rate"
              suffix="% p.a."
              min={0}
              max={50}
              step={0.05}
              value={purchase.interestRate}
              onChange={(r) => update({ interestRate: r })}
              placeholder="blank = research it"
            />
            <NumberInput
              label="Tenure"
              suffix="years"
              min={1}
              max={50}
              value={purchase.tenureMonths === null ? null : purchase.tenureMonths / 12}
              onChange={(y) =>
                update({ tenureMonths: y === null ? null : Math.max(1, Math.round(y * 12)) })
              }
              placeholder="blank = typical"
            />
            <MoneyInput
              label="Monthly running costs"
              value={purchase.monthlyOwnershipCost}
              onChange={(m) => update({ monthlyOwnershipCost: m })}
              placeholder="maintenance, insurance, fuel…"
              hint="Optional, but leaving it blank is flagged"
            />
          </div>
          <div className="flex flex-col gap-2 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={purchase.financeUpfrontCosts}
                onChange={(e) => update({ financeUpfrontCosts: e.target.checked })}
                className="size-4 accent-[var(--primary)]"
              />
              Add upfront costs to the loan instead of paying them in cash
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={purchase.researchFinancing}
                onChange={(e) => update({ researchFinancing: e.target.checked })}
                className="size-4 accent-[var(--primary)]"
              />
              Ask the Research Agent to compare financing options
            </label>
          </div>

          <div className="flex flex-col gap-3 border-t pt-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold">Your finances</h3>
              <span className="text-xs text-muted-foreground">
                Saved to your Financial Profile as values you entered.
              </span>
            </div>
            {household ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <MoneyInput
                  label="Monthly take-home income"
                  required
                  highlight={missing.has("monthlyIncome")}
                  value={household.monthlyIncome}
                  onChange={(x) => setHousehold({ ...household, monthlyIncome: x })}
                  badge={srcBadge("monthlyIncome")}
                />
                <MoneyInput
                  label="Monthly living expenses"
                  required
                  highlight={missing.has("monthlyExpenses")}
                  value={household.monthlyExpenses}
                  onChange={(x) => setHousehold({ ...household, monthlyExpenses: x })}
                  badge={srcBadge("monthlyExpenses")}
                />
                <MoneyInput
                  label="Liquid savings"
                  required
                  highlight={missing.has("liquidSavings")}
                  value={household.liquidSavings}
                  onChange={(x) => setHousehold({ ...household, liquidSavings: x })}
                  badge={srcBadge("liquidSavings")}
                />
                <MoneyInput
                  label="Existing EMIs (monthly)"
                  required
                  highlight={missing.has("existingEmis")}
                  value={household.existingEmis}
                  onChange={(x) => setHousehold({ ...household, existingEmis: x })}
                  badge={srcBadge("existingEmis")}
                  placeholder="0 if none"
                />
                <MoneyInput
                  label="Insurance & other fixed obligations"
                  value={household.otherMonthlyObligations}
                  onChange={(x) => setHousehold({ ...household, otherMonthlyObligations: x })}
                  badge={srcBadge("otherMonthlyObligations")}
                  placeholder="monthly, optional"
                />
              </div>
            ) : null}
          </div>

          {error ? <Notice tone="error">{error}</Notice> : null}
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={start} disabled={running} className="h-10 px-5">
              {running ? <Loader2 className="animate-spin" /> : <Play />}
              {running ? "Agents working…" : "Run affordability analysis"}
            </Button>
            <span className="text-xs text-muted-foreground">
              Nothing is submitted anywhere. You approve any next steps.
            </span>
          </div>
        </Section>

        <Section
          title="Agent activity"
          description={
            running
              ? "Live events from the orchestrator and its agents."
              : events.length
                ? "What ran for the analysis below."
                : "The task plan and every tool call appear here as they happen."
          }
        >
          <PlanTracker events={events} running={running} />
          {events.length ? (
            <details className="group" open={running}>
              <summary className="cursor-pointer text-xs text-muted-foreground select-none">
                Event log ({events.length})
              </summary>
              <div className="mt-2">
                <EventFeed events={events} />
              </div>
            </details>
          ) : (
            <p className="text-sm text-muted-foreground">
              No analysis yet. Click <span className="font-medium text-foreground">Try Demo</span>,
              then <span className="font-medium text-foreground">Run</span>.
            </p>
          )}
        </Section>
      </div>

      <div ref={resultsRef} className="scroll-mt-6">
        {run?.status === "needs_input" ? (
          <Notice
            tone="warning"
            title="The Planner needs a few more details before it can give a reliable answer"
          >
            <ul className="mt-1 list-disc pl-5">
              {run.missing.map((m) => (
                <li key={m.field}>{m.question}</li>
              ))}
            </ul>
            <span className="mt-2 block">
              Fill in the highlighted fields above and run again — FinPulse doesn&apos;t guess your
              personal figures.
            </span>
          </Notice>
        ) : null}
        {run?.status === "failed" ? (
          <Notice tone="error" title="The analysis could not finish">
            {run.error} The steps that did run are shown in the agent activity panel.
          </Notice>
        ) : null}
        {run?.status === "completed" ? <RunResults run={run} plan={plan} /> : null}
      </div>
    </div>
  );
}
