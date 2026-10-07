import type { EarlyWarning, Investigation } from "@finpulse/contracts";
import { ArrowRight, BookOpen, FileText } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { DemoResetButton } from "@/components/demo/reset-button";
import {
  BandBadge,
  RiskBadge,
  SeverityBadge,
  StressRiskBadge,
  ToneBadge,
} from "@/components/fp/badges";
import { Disclaimer, PageHeader, Panel } from "@/components/fp/layout";
import { ApiErrorPanel } from "@/components/fp/states";
import { sectionHref } from "@/components/shell/nav";
import {
  getDemo,
  getInvestigation,
  getMetrics,
  getPassport,
  getRiskSummary,
  getWarnings,
  listInvestigations,
  runStressPreset,
} from "@/lib/api/finpulse";
import { evidenceHref } from "@/lib/evidence-link";
import {
  formatDate,
  formatINR,
  formatMetric,
  formatMonth,
  formatNumber,
  formatPercent,
} from "@/lib/format";
import { label, type Tone } from "@/lib/presentation";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Demo walkthrough" };

const PRIORITY_TONE: Record<string, Tone> = { high: "serious", medium: "warning", low: "info" };

function ev(w: EarlyWarning | undefined, id: string): Record<string, unknown> {
  return (w?.evidence.find((e) => e.id === id)?.values ?? {}) as Record<string, unknown>;
}

export default async function DemoPage() {
  let demo;
  try {
    demo = await getDemo();
  } catch (error) {
    return <ApiErrorPanel error={error} what="the demo" />;
  }
  const id = demo.entity_id;
  let data;
  try {
    const [passport, risk, warnings, metrics, stress, list] = await Promise.all([
      getPassport(id),
      getRiskSummary(id),
      getWarnings(id),
      getMetrics(id),
      runStressPreset(id, demo.stress_preset),
      listInvestigations(id).catch(() => []),
    ]);
    const latest = [...list].sort((a, b) => b.started_at.localeCompare(a.started_at))[0];
    const investigation: Investigation | null = latest
      ? await getInvestigation(latest.investigation_id).catch(() => null)
      : null;
    data = { passport, risk, warnings, metrics, stress, investigation };
  } catch (error) {
    return (
      <div className="flex flex-col gap-4">
        <ApiErrorPanel error={error} what="the demo entity" />
        <DemoResetButton />
      </div>
    );
  }
  const { passport, risk, warnings, metrics, stress, investigation } = data;
  const fh = passport.financial_health;
  const lead = warnings.warnings[0];
  const metric = (code: string) => metrics.metrics.find((m) => m.code === code);
  const concentration = metric("customers.concentration");
  const evidence = (item: string) => evidenceHref(id, item);
  const shock = stress.evidence.find((e) => e.kind === "shock");

  const mainEvidence: { label: string; value: React.ReactNode; item: string }[] = [
    {
      label: "Revenue growth (last 3 months vs the 3 before)",
      value: formatMetric(metric("revenue.growth")?.value, "ratio", { code: "revenue.growth" }),
      item: "metric:revenue.growth",
    },
    {
      label: "Receivables outstanding",
      value: (
        <>
          {formatINR(String(ev(lead, "receivables_now").value ?? ""))}{" "}
          <span className="text-muted-foreground">
            was {formatINR(String(ev(lead, "receivables_then").value ?? ""))}
          </span>
        </>
      ),
      item: "metric:receivables.outstanding",
    },
    {
      label: "Collection time (receivable days)",
      value: (
        <>
          {formatNumber(String(ev(lead, "collection_days").now ?? ""), 1)} days{" "}
          <span className="text-muted-foreground">
            was {formatNumber(String(ev(lead, "collection_days").then ?? ""), 1)}
          </span>
        </>
      ),
      item: "metric:receivables.days",
    },
    {
      label: "Average cash balance (30 days)",
      value: (
        <>
          {formatINR(String(ev(lead, "cash_average").now ?? ""))}{" "}
          <span className="text-muted-foreground">
            was {formatINR(String(ev(lead, "cash_average").then ?? ""))}
          </span>
        </>
      ),
      item: "metric:cash.balance",
    },
    {
      label: `Largest customer${concentration?.components?.largest ? ` (${String(concentration.components.largest)})` : ""}`,
      value: `${formatPercent(concentration?.value)} of revenue`,
      item: "metric:customers.concentration",
    },
    {
      label: "Repayment record (the evidence on the other side)",
      value: `${formatPercent(metric("payments.consistency")?.value)} paid on time`,
      item: "metric:payments.consistency",
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Deterministic demo"
        title={`Demo: ${demo.entity_name}`}
        description="A small business with limited credit history that looks healthy — until FinPulse looks underneath. Every figure on this page is computed live by the engines from seeded synthetic data; reset restores the exact starting state."
        actions={<DemoResetButton />}
      />

      <Panel
        title={
          <span className="flex items-center gap-2">
            <BookOpen className="size-4" aria-hidden />
            The story
          </span>
        }
        description={`Synthetic data, as of ${formatDate(demo.as_of)}.`}
      >
        <p className="max-w-3xl text-sm text-pretty">{demo.narrative}</p>
      </Panel>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold">Walkthrough</h2>
        <ol className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {demo.steps.map((s) => {
            const href =
              s.number === 6
                ? "#brief"
                : `${sectionHref(id, s.section)}${s.section === "stress" ? `?preset=${demo.stress_preset}` : ""}`;
            return (
              <li key={s.number}>
                <Link
                  href={href}
                  className="group flex h-full flex-col gap-2 rounded-xl border bg-card p-4 shadow-xs hover:border-primary/40"
                >
                  <span className="flex items-center gap-2">
                    <span className="tabular flex size-6 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                      {s.number}
                    </span>
                    <span className="text-sm font-semibold">{s.title}</span>
                    <ArrowRight
                      className="ml-auto size-4 text-muted-foreground group-hover:text-primary"
                      aria-hidden
                    />
                  </span>
                  <span className="text-xs text-pretty text-muted-foreground">{s.show}</span>
                </Link>
              </li>
            );
          })}
        </ol>
      </section>

      <section
        id="brief"
        className="scroll-mt-6 overflow-hidden rounded-xl border bg-card shadow-xs"
      >
        <header className="flex flex-wrap items-center gap-3 border-b bg-sidebar px-5 py-4 text-sidebar-foreground sm:px-6">
          <FileText className="size-5" aria-hidden />
          <div>
            <h2 className="text-base font-semibold">Financial brief: {demo.entity_name}</h2>
            <p className="text-xs text-sidebar-muted">
              As of {formatDate(demo.as_of)} · prototype on synthetic data
            </p>
          </div>
        </header>
        <dl className="divide-y">
          <BriefRow term="Financial Passport">
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="text-lg font-semibold">
                Financial Health: <span className="tabular">{formatNumber(fh.score, 1)}</span>/100
              </span>
              <BandBadge band={fh.band?.label} />
              <Link href={sectionHref(id, "passport")} className="text-xs text-primary">
                Passport →
              </Link>
            </div>
            <p className="text-xs text-muted-foreground">
              A prototype financial-health profile, not a credit score.
            </p>
          </BriefRow>
          <BriefRow term="Current risk">
            <div className="flex items-center gap-3">
              <span className="text-lg font-semibold tracking-wide uppercase">
                {label(risk.risk_level)}
              </span>
              <RiskBadge level={risk.risk_level} />
              <span className="tabular text-xs text-muted-foreground">
                early-warning index {risk.early_warning_index}/100
              </span>
            </div>
          </BriefRow>
          <BriefRow term="Early warning">
            {lead ? (
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-lg font-semibold">{lead.title}</span>
                  <SeverityBadge severity={lead.severity} />
                </div>
                <p className="max-w-3xl text-sm text-pretty text-muted-foreground">
                  {lead.description}
                </p>
                <Link
                  href={`${sectionHref(id, "warnings")}?warning=${lead.id}`}
                  className="text-xs text-primary"
                >
                  Early Warning Center →
                </Link>
              </div>
            ) : (
              <span className="text-sm text-muted-foreground">No active warning.</span>
            )}
          </BriefRow>
          <BriefRow term="Main evidence">
            <ul className="grid grid-cols-1 gap-x-8 gap-y-2 md:grid-cols-2">
              {mainEvidence.map((e) => (
                <li key={e.label} className="flex flex-col">
                  <span className="text-xs text-muted-foreground">{e.label}</span>
                  <Link
                    href={evidence(e.item)}
                    className="tabular text-sm font-medium hover:text-primary"
                  >
                    {e.value}
                  </Link>
                </li>
              ))}
            </ul>
          </BriefRow>
          <BriefRow term="Stress test">
            <span className="text-lg font-semibold">{stress.scenario.name}</span>
            {shock ? (
              <p className="max-w-3xl text-sm text-pretty text-muted-foreground">{shock.text}</p>
            ) : null}
          </BriefRow>
          <BriefRow term="Result">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Before title="Six-month risk">
                <span className="flex items-center gap-1.5">
                  <StressRiskBadge level={stress.risk_change.baseline} />
                  <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />
                  <StressRiskBadge level={stress.risk_change.scenario} />
                </span>
              </Before>
              <Before title="Lowest cash balance in six months">
                <span className="tabular">
                  {formatINR(stress.baseline.minimum_balance, { compact: true })} →{" "}
                  <span className="font-semibold">
                    {formatINR(stress.stressed.minimum_balance, { compact: true })}
                  </span>{" "}
                  <span className="text-xs text-muted-foreground">
                    ({formatMonth(`${stress.stressed.minimum_balance_month}-01`)})
                  </span>
                </span>
              </Before>
              <Before title="Projected Financial Health">
                <span className="tabular">
                  {formatNumber(stress.health_impact.baseline_projected_score, 1)} →{" "}
                  <span className="font-semibold">
                    {formatNumber(stress.health_impact.scenario_score, 1)}
                  </span>
                </span>
              </Before>
            </div>
            <p className="mt-2 text-xs text-pretty text-muted-foreground">
              {stress.stressed.risk.reasons.join(" ")}
              {stress.stressed.failure_point
                ? ` Funds run out around ${formatDate(stress.stressed.failure_point.date)}.`
                : ""}
            </p>
            <Link
              href={`${sectionHref(id, "stress")}?preset=${demo.stress_preset}`}
              className="text-xs text-primary"
            >
              Run it in the Stress Test →
            </Link>
          </BriefRow>
          <BriefRow term="Recommended actions">
            {investigation && investigation.recommendations.length ? (
              <div className="flex flex-col gap-2">
                <ol className="flex flex-col gap-2">
                  {(investigation.recommendations as Record<string, unknown>[]).map((r, i) => (
                    <li key={i} className="flex flex-wrap items-start gap-2 text-sm">
                      <span className="tabular mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
                        {i + 1}
                      </span>
                      <span className="min-w-0 flex-1 text-pretty">{String(r.action)}</span>
                      <ToneBadge tone={PRIORITY_TONE[String(r.priority)] ?? "neutral"} size="sm">
                        {label(String(r.priority))}
                      </ToneBadge>
                    </li>
                  ))}
                </ol>
                <p className="text-xs text-muted-foreground">
                  From the AI investigation of {formatDate(investigation.as_of)}
                  {investigation.ai_mode === "demo_script"
                    ? " (demo script, not a live model)"
                    : ""}
                  .{" "}
                  <Link
                    href={`${sectionHref(id, "investigation")}?investigation=${investigation.investigation_id}`}
                    className="text-primary"
                  >
                    Investigation Report →
                  </Link>
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Run the AI investigation (step 5) to generate recommended actions.{" "}
                <Link href={sectionHref(id, "investigation")} className="text-primary">
                  AI Investigation →
                </Link>
              </p>
            )}
          </BriefRow>
        </dl>
      </section>

      <Disclaimer>{passport.disclaimer}</Disclaimer>
    </div>
  );
}

function BriefRow({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-2 px-5 py-4 sm:grid-cols-[11rem_minmax(0,1fr)] sm:px-6">
      <dt className="text-xs font-semibold tracking-wide text-muted-foreground uppercase sm:pt-1">
        {term}
      </dt>
      <dd className={cn("flex min-w-0 flex-col gap-1")}>{children}</dd>
    </div>
  );
}

function Before({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border bg-muted/30 p-3">
      <span className="text-[11px] text-muted-foreground">{title}</span>
      <span className="text-sm">{children}</span>
    </div>
  );
}
