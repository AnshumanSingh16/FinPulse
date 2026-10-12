"use client";

import { ArrowRight, Bot, Calculator, ClipboardCheck, Wand2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatINR } from "@/lib/format";
import { api } from "@/lib/personal/client";
import {
  debtToIncomeRatio,
  emergencyFundCoverageMonths,
  summariseCashFlow,
} from "@/lib/personal/finance/health";
import { PROFILE_LABELS } from "@/lib/personal/schemas";

import { usePersonal } from "./provider";
import { ApprovalBadge, AssessmentBadge, Kpi, Loading, ModeStrip, Notice, Section } from "./ui";

export function Overview() {
  const { state, setState, error } = usePersonal();
  const [busy, setBusy] = useState(false);
  if (error)
    return (
      <Notice tone="error" title="Could not load your data">
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
  const dti = hasCore ? debtToIncomeRatio(v.existingEmis!, v.monthlyIncome!) : null;
  const latest = state.latestRun;
  const pending = state.actionPlans.filter(
    (p) => p.status === "awaiting_review" || p.status === "approved",
  );

  // Alerts derived from the profile and the latest analysis only.
  const alerts: { tone: "warning" | "error" | "info"; text: string }[] = [];
  const missingCore = (
    ["monthlyIncome", "monthlyExpenses", "liquidSavings", "existingEmis"] as const
  ).filter((f) => v[f] === null);
  if (missingCore.length)
    alerts.push({
      tone: "info",
      text: `Profile incomplete: ${missingCore.map((f) => PROFILE_LABELS[f]).join(", ")}.`,
    });
  if (flow && flow.monthlySurplus < 0)
    alerts.push({
      tone: "error",
      text: `You spend ${formatINR(-flow.monthlySurplus)} a month more than you take home.`,
    });
  if (cover !== null && cover < (v.emergencyBufferMonths ?? 6))
    alerts.push({
      tone: "warning",
      text: `Savings cover ${cover.toFixed(1)} months of outgoings — below your ${v.emergencyBufferMonths ?? 6}-month target.`,
    });
  if (dti !== null && dti > 0.35)
    alerts.push({
      tone: "warning",
      text: `EMIs already take ${(dti * 100).toFixed(0)}% of take-home pay.`,
    });
  if (latest?.analysis && latest.analysis.label !== "comfortable")
    alerts.push({
      tone: latest.analysis.label === "high_strain" ? "error" : "warning",
      text: `Latest analysis (${latest.request.label}): ${latest.recommendation?.headline ?? ""}`,
    });
  for (const d of state.documents.filter((d) => d.review === "pending"))
    alerts.push({
      tone: "info",
      text: `"${d.name}" has extracted values waiting for your review.`,
    });

  async function demo() {
    setBusy(true);
    try {
      setState(await api.loadDemo());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-4 rounded-2xl border bg-card p-5 sm:p-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-2">
          <div className="text-xs font-medium tracking-wide text-primary uppercase">
            FinPulse · Your Financial Life. On Autopilot.
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
            Can I afford this, and what should I do next?
          </h1>
          <p className="max-w-2xl text-sm text-muted-foreground">
            An orchestrator plans the question and hands it to research, analysis, risk,
            verification and action agents. Calculations are deterministic and tested; you approve
            every next step.
          </p>
          <ModeStrip status={state.status} />
        </div>
        <div className="flex flex-wrap gap-2 lg:flex-col">
          <Button asChild className="h-10 px-5">
            <Link href="/afford">
              <Calculator /> Start a new analysis
            </Link>
          </Button>
          {!hasCore ? (
            <Button variant="outline" onClick={demo} disabled={busy}>
              <Wand2 /> Try Demo (fictional profile)
            </Button>
          ) : (
            <Button asChild variant="outline">
              <Link href="/copilot">
                <Bot /> Ask the Copilot
              </Link>
            </Button>
          )}
        </div>
      </header>

      <Section
        title="Financial snapshot"
        description={
          state.profile.isDemo ? "From the fictional demo profile." : "From your Financial Profile."
        }
        actions={
          <Link href="/profile" className="text-xs text-primary hover:underline">
            Edit profile
          </Link>
        }
      >
        {hasCore && flow ? (
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
            <Kpi label="Take-home / month" value={formatINR(v.monthlyIncome)} />
            <Kpi label="Living expenses" value={formatINR(v.monthlyExpenses)} />
            <Kpi label="Existing EMIs" value={formatINR(v.existingEmis)} />
            <Kpi
              label="Monthly surplus"
              value={formatINR(flow.monthlySurplus)}
              tone={flow.monthlySurplus < 0 ? "bad" : "good"}
              sub={
                flow.savingsRate !== null
                  ? `${(flow.savingsRate * 100).toFixed(0)}% of income`
                  : undefined
              }
            />
            <Kpi label="Liquid savings" value={formatINR(v.liquidSavings, { compact: true })} />
            <Kpi
              label="Emergency cover"
              value={cover === null ? "—" : `${cover.toFixed(1)} mo`}
              tone={
                cover !== null && cover < 3 ? "bad" : cover !== null && cover < 6 ? "warn" : "good"
              }
            />
          </div>
        ) : (
          <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed p-5 text-sm text-muted-foreground">
            No profile yet. Load the fictional demo profile to explore, or enter your own figures.
            <div className="flex gap-2">
              <Button size="sm" onClick={demo} disabled={busy}>
                <Wand2 /> Try Demo
              </Button>
              <Button size="sm" variant="outline" asChild>
                <Link href="/profile">Enter my details</Link>
              </Button>
            </div>
          </div>
        )}
      </Section>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section
          title="Active goal"
          actions={
            latest ? (
              <Link
                href={`/afford?run=${latest.id}`}
                className="text-xs text-primary hover:underline"
              >
                Open results
              </Link>
            ) : null
          }
        >
          {latest ? (
            <div className="flex flex-col gap-2">
              <div className="text-sm font-medium">{latest.goal}</div>
              {latest.analysis ? (
                <AssessmentBadge label={latest.analysis.label} long />
              ) : (
                <span className="text-sm text-muted-foreground">
                  Status: {latest.status.replace("_", " ")}
                </span>
              )}
              {latest.analysis ? (
                <div className="grid grid-cols-3 gap-2">
                  <Kpi label="EMI" value={formatINR(latest.analysis.emi)} />
                  <Kpi
                    label="Savings after"
                    value={formatINR(latest.analysis.postPurchaseSavings, { compact: true })}
                  />
                  <Kpi
                    label="Left monthly"
                    value={formatINR(latest.analysis.after.cashFlow.monthlySurplus)}
                  />
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {v.goals ?? "No analysis yet."}{" "}
              <Link href="/afford" className="text-primary hover:underline">
                Run one
              </Link>
              .
            </p>
          )}
        </Section>

        <Section title="Risk alerts" description="Derived from your profile and latest analysis.">
          {alerts.length ? (
            <ul className="flex flex-col gap-2">
              {alerts.slice(0, 5).map((a) => (
                <li key={a.text}>
                  <Notice tone={a.tone}>{a.text}</Notice>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              {hasCore
                ? "No alerts from your current figures."
                : "Alerts appear once your profile has figures."}
            </p>
          )}
        </Section>

        <Section
          title="Pending tasks"
          actions={
            <Link href="/actions" className="text-xs text-primary hover:underline">
              Action Center
            </Link>
          }
        >
          {pending.length ? (
            <ul className="flex flex-col divide-y rounded-lg border">
              {pending.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 p-3 text-sm">
                  <span className="flex min-w-0 items-center gap-2">
                    <ClipboardCheck className="size-4 shrink-0 text-muted-foreground" />
                    <span className="truncate">{p.title}</span>
                  </span>
                  <ApprovalBadge status={p.status} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Nothing waiting for you.</p>
          )}
        </Section>

        <Section
          title="Recent agent activity"
          actions={
            <Link href="/audit" className="text-xs text-primary hover:underline">
              Full audit trail
            </Link>
          }
        >
          {state.audit.length ? (
            <ol className="flex flex-col gap-2">
              {state.audit.slice(0, 7).map((e) => (
                <li key={e.id} className="flex gap-3 text-xs">
                  <span className="tabular w-14 shrink-0 text-muted-foreground">
                    {new Date(e.at).toLocaleTimeString("en-IN", {
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: false,
                    })}
                  </span>
                  <span className="w-28 shrink-0 truncate text-primary">{e.actor}</span>
                  <span className="min-w-0 text-pretty">{e.summary}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">No activity yet.</p>
          )}
          <Link
            href="/afford"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            Launch a new analysis <ArrowRight className="size-3" />
          </Link>
        </Section>
      </div>
    </div>
  );
}
