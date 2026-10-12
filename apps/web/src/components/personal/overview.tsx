"use client";

import { ChevronRight, ClipboardCheck, FileText, Wand2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/personal/client";
import { emergencyFundCoverageMonths, summariseCashFlow } from "@/lib/personal/finance/health";
import { PROFILE_LABELS } from "@/lib/personal/schemas";

import { GoalInput } from "./goal-input";
import { usePersonal } from "./provider";
import {
  ApprovalBadge,
  AssessmentBadge,
  Disclosure,
  EmptyState,
  Loading,
  ModeStrip,
  Notice,
  Section,
  Stat,
} from "./ui";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

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
  const target = v.emergencyBufferMonths ?? 6;

  // "Needs your attention": derived only from your figures, analyses, plans and documents.
  const attention: {
    key: string;
    tone: "warning" | "error" | "info";
    text: string;
    href?: string;
    cta?: string;
  }[] = [];
  for (const p of state.actionPlans.filter((p) => p.status === "awaiting_review"))
    attention.push({
      key: p.id,
      tone: "info",
      text: `Review your next steps: ${p.title.replace("Next steps: ", "")}`,
      href: "/actions",
      cta: "Review",
    });
  if (flow && flow.monthlySurplus < 0)
    attention.push({
      key: "deficit",
      tone: "error",
      text: `You spend ${formatINR(-flow.monthlySurplus)} a month more than you take home.`,
      href: "/profile",
      cta: "Check",
    });
  if (cover !== null && cover < target)
    attention.push({
      key: "cover",
      tone: "warning",
      text: `Your savings cover ${cover.toFixed(1)} months of spending — below your ${target}-month goal.`,
    });
  for (const d of state.documents.filter((d) => d.review === "pending"))
    attention.push({
      key: d.id,
      tone: "info",
      text: `Confirm the figures read from "${d.name}".`,
      href: "/documents",
      cta: "Review",
    });
  const missing = (
    ["monthlyIncome", "monthlyExpenses", "liquidSavings", "existingEmis"] as const
  ).filter((f) => v[f] === null);
  if (missing.length && state.profile.updatedAt)
    attention.push({
      key: "missing",
      tone: "info",
      text: `Add ${missing.map((f) => PROFILE_LABELS[f].toLowerCase()).join(", ")} for reliable answers.`,
      href: "/profile",
      cta: "Add",
    });

  const analyses = state.runs.slice(0, 4);

  async function demo() {
    setBusy(true);
    try {
      setState(await api.loadDemo());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <p className="text-sm text-muted-foreground">
          {greeting()}
          {state.profile.isDemo ? " (demo profile)" : ""}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">
          What would you like to afford?
        </h1>
      </div>

      {/* The main entry point */}
      <section className="flex flex-col gap-4 rounded-3xl bg-accent/60 p-5 sm:p-7">
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-semibold">Can I afford this?</h2>
          <p className="text-sm text-muted-foreground">
            Tell FinPulse what you&apos;re planning. It checks your finances, works out the costs,
            stress-tests the plan and prepares next steps for you to approve.
          </p>
        </div>
        <GoalInput />
        <ModeStrip status={state.status} />
      </section>

      {/* Snapshot */}
      <Section
        title="Your money this month"
        description={state.profile.isDemo ? "From the fictional demo profile." : undefined}
        actions={
          hasCore ? (
            <Link href="/profile" className="text-sm font-medium text-primary hover:underline">
              Edit
            </Link>
          ) : null
        }
        card={false}
      >
        {hasCore && flow ? (
          <div className="grid grid-cols-2 gap-x-6 gap-y-5 rounded-2xl border p-5 sm:grid-cols-4 sm:divide-x sm:p-6 [&>*]:sm:pl-6 [&>*:first-child]:sm:pl-0">
            <Stat label="Take-home pay" value={formatINR(v.monthlyIncome)} />
            <Stat
              label="Spending + EMIs"
              value={formatINR(
                v.monthlyExpenses! + v.existingEmis! + (v.otherMonthlyObligations ?? 0),
              )}
            />
            <Stat
              label="Left over"
              value={formatINR(flow.monthlySurplus)}
              tone={flow.monthlySurplus < 0 ? "bad" : "good"}
              sub={
                flow.savingsRate !== null
                  ? `${Math.round(flow.savingsRate * 100)}% of pay`
                  : undefined
              }
            />
            <Stat
              label="Savings"
              value={formatINR(v.liquidSavings, { compact: true })}
              sub={cover !== null ? `${cover.toFixed(1)} months of spending` : undefined}
            />
          </div>
        ) : (
          <EmptyState
            title="Add your finances to get personal answers"
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <Button onClick={demo} disabled={busy}>
                  <Wand2 /> Try the demo profile
                </Button>
                <Button variant="outline" asChild>
                  <Link href="/profile">Enter my details</Link>
                </Button>
              </div>
            }
          >
            Income, spending, savings and EMIs are enough. The demo uses a fictional person.
          </EmptyState>
        )}
      </Section>

      <div className="grid gap-8 lg:grid-cols-2">
        <Section title="Needs your attention" card={false}>
          {attention.length ? (
            <ul className="flex flex-col divide-y rounded-2xl border">
              {attention.slice(0, 5).map((a) => (
                <li key={a.key} className="flex items-center gap-3 px-4 py-3 text-sm">
                  <span
                    className={
                      a.tone === "error"
                        ? "text-text-critical"
                        : a.tone === "warning"
                          ? "text-text-warning"
                          : "text-primary"
                    }
                  >
                    {a.href === "/documents" ? (
                      <FileText className="size-4" />
                    ) : (
                      <ClipboardCheck className="size-4" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1 text-pretty">{a.text}</span>
                  {a.href ? (
                    <Link
                      href={a.href}
                      className="shrink-0 font-medium text-primary hover:underline"
                    >
                      {a.cta}
                    </Link>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-2xl border px-4 py-5 text-sm text-muted-foreground">
              {hasCore
                ? "Nothing needs you right now."
                : "Alerts appear once your finances are added."}
            </p>
          )}
        </Section>

        <Section title="Recent analyses" card={false}>
          {analyses.length ? (
            <ul className="flex flex-col divide-y rounded-2xl border">
              {analyses.map((r) => (
                <li key={r.id}>
                  <Link
                    href={`/afford?run=${r.id}`}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-muted/50"
                  >
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-sm font-medium">{r.label}</span>
                      <span className="text-xs text-muted-foreground">
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
                      <span className="text-xs text-muted-foreground">
                        {r.status.replace("_", " ")}
                      </span>
                    )}
                    <ChevronRight className="size-4 text-muted-foreground" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-2xl border px-4 py-5 text-sm text-muted-foreground">
              No analyses yet. Try “I want to buy a ₹75 lakh house”.
            </p>
          )}
        </Section>
      </div>

      <Disclosure
        title="Recent activity"
        hint="What FinPulse's agents and you did, as recorded by the server"
      >
        {state.audit.length ? (
          <ol className="flex flex-col gap-2.5">
            {state.audit.slice(0, 8).map((e) => (
              <li key={e.id} className="flex gap-3 text-sm">
                <span className="tabular w-12 shrink-0 text-xs text-muted-foreground">
                  {new Date(e.at).toLocaleTimeString("en-IN", {
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  })}
                </span>
                <span className="min-w-0 text-pretty">{e.summary}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">No activity yet.</p>
        )}
        <Link
          href="/audit"
          className="mt-3 inline-block text-sm font-medium text-primary hover:underline"
        >
          Full activity log
        </Link>
      </Disclosure>
      {state.actionPlans.some((p) => p.status === "approved") ? (
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          In progress:
          {state.actionPlans
            .filter((p) => p.status === "approved")
            .map((p) => (
              <Link key={p.id} href="/actions" className="inline-flex items-center gap-1.5">
                <ApprovalBadge status={p.status} /> {p.title.replace("Next steps: ", "")}
              </Link>
            ))}
        </div>
      ) : null}
    </div>
  );
}
