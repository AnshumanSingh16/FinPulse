"use client";

import {
  ArrowRight,
  Calculator,
  Car,
  ChevronRight,
  ClipboardCheck,
  FileText,
  Home,
  ShieldHalf,
  Umbrella,
  Wand2,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/personal/client";
import { DEFAULT_RULES } from "@/lib/personal/finance/affordability";
import { emergencyFundCoverageMonths, summariseCashFlow } from "@/lib/personal/finance/health";
import { cn } from "@/lib/utils";

import { stepsFromEvents } from "./agent-activity";
import { GoalInput } from "./goal-input";
import { AgentGlyph, Meter, PulseMark } from "./kit";
import { usePersonal } from "./provider";
import { AssessmentBadge, Loading, ModeStrip, Notice } from "./ui";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** Prompts that start real work: two open the guided analysis, two ask the copilot's tools. */
const PROMPTS = [
  {
    label: "Can I afford a house?",
    href: "/afford?goal=Can%20I%20afford%20a%20house%3F",
    icon: Home,
  },
  { label: "Plan my car purchase", href: "/afford?goal=Plan%20my%20car%20purchase", icon: Car },
  {
    label: "Build an emergency fund",
    href: "/copilot?q=Build%20an%20emergency%20fund",
    icon: Umbrella,
  },
  {
    label: "Stress-test my finances",
    href: "/copilot?q=Stress-test%20my%20finances",
    icon: ShieldHalf,
  },
];

export function Overview() {
  const { state, setState, error } = usePersonal();
  const [busy, setBusy] = useState(false);
  if (error)
    return (
      <Notice tone="error" title="Couldn't load your data">
        {error}
      </Notice>
    );
  if (!state) return <Loading />;

  const v = state.profile.values;
  const hasCore =
    v.monthlyIncome !== null &&
    v.monthlyExpenses !== null &&
    v.liquidSavings !== null &&
    v.existingEmis !== null;
  const flow = hasCore
    ? summariseCashFlow({
        monthlyIncome: v.monthlyIncome!,
        monthlyExpenses: v.monthlyExpenses!,
        monthlyDebtPayments: v.existingEmis!,
        monthlyOtherObligations: v.otherMonthlyObligations ?? 0,
      })
    : null;
  const cover = flow
    ? emergencyFundCoverageMonths(v.liquidSavings!, flow.totalMonthlyOutflow)
    : null;
  const target = v.emergencyBufferMonths ?? DEFAULT_RULES.emergencyComfortableMonths;
  const latest = state.latestRun;
  const awaiting = state.actionPlans.find((p) => p.status === "awaiting_review");
  const pendingDocs = state.documents.filter((d) => d.review === "pending");

  // The single most important thing, from real state, in priority order.
  const insight: {
    tone: "warn" | "bad" | "info";
    title: string;
    body: string;
    href: string;
    cta: string;
  } | null =
    flow && flow.monthlySurplus < 0
      ? {
          tone: "bad",
          title: "You're spending more than you earn",
          body: `Outgoings exceed take-home pay by ${formatINR(-flow.monthlySurplus)} a month.`,
          href: "/profile",
          cta: "Check figures",
        }
      : awaiting
        ? {
            tone: "info",
            title: "Your next steps are ready for review",
            body: `${awaiting.title.replace("Next steps: ", "")}: ${awaiting.items.length} steps prepared by the Action agent.`,
            href: "/actions",
            cta: "Review",
          }
        : cover !== null && cover < target
          ? {
              tone: "warn",
              title: "Your safety buffer is below your goal",
              body: `Savings cover ${cover.toFixed(1)} months of spending; your goal is ${target}.`,
              href: "/copilot?q=Build%20an%20emergency%20fund",
              cta: "Plan it",
            }
          : pendingDocs.length
            ? {
                tone: "info",
                title: "Confirm figures from your documents",
                body: `${pendingDocs.length} document${pendingDocs.length === 1 ? "" : "s"} waiting for your review.`,
                href: "/documents",
                cta: "Review",
              }
            : null;

  const latestSteps = latest ? stepsFromEvents(latest.events, false) : [];

  async function demo() {
    setBusy(true);
    try {
      setState(await api.loadDemo());
    } finally {
      setBusy(false);
    }
  }

  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        {/* Primary action */}
        <section className="flex flex-col gap-5 pt-1">
          <div className="flex flex-col gap-1.5">
            <p className="text-[14px] text-ink-500">
              {greeting()}
              {v.name ? `, ${v.name}` : ""} · {today}
              {state.profile.isDemo ? " · demo profile" : ""}
            </p>
            <h1 className="text-[30px] leading-[1.1] font-extrabold text-balance sm:text-[40px]">
              What do you want to plan today?
            </h1>
          </div>
          <GoalInput examples={[]} />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {PROMPTS.map((p) => (
              <Link
                key={p.label}
                href={p.href}
                className="group flex min-h-[72px] flex-col justify-between gap-2 rounded-xl border border-line bg-surface p-3 text-[13.5px] leading-snug font-medium text-ink-900 shadow-xs transition hover:border-line-strong hover:shadow-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <p.icon className="size-[18px] text-brand-600" aria-hidden />
                {p.label}
              </Link>
            ))}
          </div>
          <ModeStrip status={state.status} />
        </section>

        {/* Snapshot */}
        <section
          className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-5 shadow-sm"
          aria-labelledby="snapshot"
        >
          <div className="flex items-center justify-between">
            <h2 id="snapshot" className="text-[15px] font-bold">
              Your money this month
            </h2>
            {hasCore ? (
              <Link
                href="/profile"
                className="text-[13px] font-semibold text-brand-700 hover:underline"
              >
                Edit
              </Link>
            ) : null}
          </div>
          {hasCore && flow ? (
            <>
              <div className="flex flex-col gap-1">
                <span className="text-[12px] text-ink-500">Left after spending and EMIs</span>
                <span
                  className={cn(
                    "tabular font-display text-[30px] leading-none font-extrabold",
                    flow.monthlySurplus < 0 && "text-danger-text",
                  )}
                >
                  {formatINR(flow.monthlySurplus)}
                </span>
                <span className="text-[12px] text-ink-500">
                  of {formatINR(v.monthlyIncome)} take-home
                  {flow.savingsRate !== null
                    ? ` · ${Math.round(flow.savingsRate * 100)}% saved`
                    : ""}
                </span>
              </div>
              <div
                className="flex h-2.5 gap-[2px] overflow-hidden rounded-full bg-surface-sunken"
                role="img"
                aria-label={`Spending ${formatINR(v.monthlyExpenses)}, EMIs ${formatINR(v.existingEmis)}, left over ${formatINR(flow.monthlySurplus)}`}
              >
                {[
                  [v.monthlyExpenses! + (v.otherMonthlyObligations ?? 0), "bg-ink-400"],
                  [v.existingEmis!, "bg-ink-700"],
                  [Math.max(0, flow.monthlySurplus), "bg-brand-500"],
                ].map(([n, cls], i) =>
                  (n as number) > 0 ? (
                    <span
                      key={i}
                      className={cn("fp-grow h-full", cls as string)}
                      style={{ width: `${((n as number) / Math.max(1, v.monthlyIncome!)) * 100}%` }}
                    />
                  ) : null,
                )}
              </div>
              <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-ink-500">
                <li className="flex items-center gap-1.5">
                  <span className="size-2 rounded-sm bg-ink-400" aria-hidden />
                  Spending {formatINR(v.monthlyExpenses! + (v.otherMonthlyObligations ?? 0))}
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="size-2 rounded-sm bg-ink-700" aria-hidden />
                  EMIs {formatINR(v.existingEmis)}
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="size-2 rounded-sm bg-brand-500" aria-hidden />
                  Left over
                </li>
              </ul>
              <div className="flex flex-col gap-2 border-t border-line pt-4">
                <div className="flex items-baseline justify-between">
                  <span className="text-[12px] text-ink-500">Savings you can use</span>
                  <span className="tabular font-display text-[17px] font-bold">
                    {formatINR(v.liquidSavings, { compact: true })}
                  </span>
                </div>
                {cover !== null ? (
                  <Meter
                    label="Months of spending your savings cover"
                    value={Math.min(cover, 24)}
                    max={Math.max(12, target + 2)}
                    valueText={`${cover.toFixed(1)} months`}
                    zones={[
                      { to: DEFAULT_RULES.emergencyMinimumMonths, tone: "bad" },
                      { to: target, tone: "warn" },
                      { to: Math.max(12, target + 2), tone: "good" },
                    ]}
                    markers={[{ at: target, label: `${target} mo goal` }]}
                  />
                ) : null}
                <span className="text-[12px] text-ink-500">
                  {cover !== null ? `${cover.toFixed(1)} months of spending covered` : ""}
                </span>
              </div>
            </>
          ) : (
            <div className="flex flex-col gap-3">
              <p className="text-[14px] text-pretty text-ink-500">
                Add your income, spending, savings and EMIs to get personal answers — or explore
                with a fictional person.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={demo} disabled={busy}>
                  <Wand2 /> Try the demo
                </Button>
                <Button variant="outline" asChild>
                  <Link href="/profile">Enter my details</Link>
                </Button>
              </div>
            </div>
          )}
        </section>
      </div>

      {insight ? (
        <Link
          href={insight.href}
          className={cn(
            "group flex items-center gap-4 rounded-2xl border p-4 shadow-xs transition hover:shadow-sm sm:p-5",
            insight.tone === "bad"
              ? "border-danger-500/30 bg-danger-50"
              : insight.tone === "warn"
                ? "border-caution-200 bg-caution-50"
                : "border-line bg-surface",
          )}
        >
          <span
            className={cn(
              "flex size-10 shrink-0 items-center justify-center rounded-xl",
              insight.tone === "bad"
                ? "bg-danger-500 text-white"
                : insight.tone === "warn"
                  ? "bg-caution-500 text-white"
                  : "bg-ink-900 text-white",
            )}
          >
            {insight.href === "/documents" ? (
              <FileText className="size-5" />
            ) : (
              <ClipboardCheck className="size-5" />
            )}
          </span>
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="text-[15px] font-bold">{insight.title}</span>
            <span className="text-[13.5px] text-pretty text-ink-700">{insight.body}</span>
          </span>
          <span className="hidden shrink-0 items-center gap-1 text-[14px] font-semibold text-ink-900 sm:flex">
            {insight.cta}{" "}
            <ArrowRight className="size-4 transition group-hover:translate-x-0.5" aria-hidden />
          </span>
        </Link>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="flex flex-col gap-3" aria-labelledby="recent">
          <div className="flex items-center justify-between">
            <h2 id="recent" className="text-[16px] font-bold">
              Recent analyses
            </h2>
            <Link
              href="/afford"
              className="text-[13px] font-semibold text-brand-700 hover:underline"
            >
              New
            </Link>
          </div>
          {state.runs.length ? (
            <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface shadow-xs">
              {state.runs.slice(0, 4).map((r) => (
                <li key={r.id}>
                  <Link
                    href={`/afford?run=${r.id}`}
                    className="flex items-center gap-3 px-4 py-3.5 hover:bg-surface-sunken/60"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-sunken text-ink-700">
                      <Calculator className="size-4" aria-hidden />
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-[14px] font-semibold">{r.label}</span>
                      <span className="tabular text-[12px] text-ink-500">
                        {r.emi !== null ? `EMI ${formatINR(r.emi)} · ` : ""}
                        {new Date(r.createdAt).toLocaleString("en-IN", {
                          day: "numeric",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </span>
                    {r.assessment ? (
                      <AssessmentBadge label={r.assessment} />
                    ) : (
                      <span className="text-[12px] text-ink-500">{r.status.replace("_", " ")}</span>
                    )}
                    <ChevronRight className="size-4 shrink-0 text-ink-400" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="rounded-2xl border border-dashed border-line-strong bg-surface px-4 py-6 text-[14px] text-ink-500">
              No analyses yet. Try “I want to buy a ₹75 lakh house”.
            </div>
          )}
        </section>

        <section className="flex flex-col gap-3" aria-labelledby="agents">
          <div className="flex items-center justify-between">
            <h2 id="agents" className="text-[16px] font-bold">
              Agent activity
            </h2>
            <Link
              href="/audit"
              className="text-[13px] font-semibold text-brand-700 hover:underline"
            >
              Activity log
            </Link>
          </div>
          {latest && latestSteps.length ? (
            <Link
              href={`/afford?run=${latest.id}`}
              className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-4 shadow-xs transition hover:shadow-sm"
            >
              <div className="flex items-center gap-3">
                <PulseMark size="sm" />
                <span className="flex min-w-0 flex-col">
                  <span className="truncate text-[14px] font-semibold">{latest.request.label}</span>
                  <span className="tabular text-[12px] text-ink-500">
                    {latestSteps.filter((s) => s.status === "done").length}/{latestSteps.length}{" "}
                    stages · {latest.toolCalls.length} tool calls ·{" "}
                    {new Date(latest.finishedAt ?? latest.createdAt).toLocaleTimeString("en-IN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </span>
              </div>
              <ol className="flex flex-wrap gap-1.5" aria-label="Stages">
                {latestSteps.map((s) => (
                  <li
                    key={s.id}
                    title={`${s.title}: ${s.status}`}
                    className={cn(
                      "flex items-center gap-1.5 rounded-full py-1 pr-2.5 pl-1 text-[12px]",
                      s.status === "done"
                        ? "bg-brand-50 text-brand-700"
                        : s.status === "failed"
                          ? "bg-danger-50 text-danger-text"
                          : "bg-surface-sunken text-ink-500",
                    )}
                  >
                    <AgentGlyph agent={s.agent} size="sm" className="size-5 bg-surface" />
                    {s.title.replace("your ", "").replace("Understanding goal", "Goal")}
                  </li>
                ))}
              </ol>
            </Link>
          ) : (
            <div className="rounded-2xl border border-dashed border-line-strong bg-surface px-4 py-6 text-[14px] text-ink-500">
              When FinPulse runs an analysis, you&apos;ll see what each agent did here.
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
