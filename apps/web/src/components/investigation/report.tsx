import type { AgentRun, EvidenceItem, EvidencePack, Investigation } from "@finpulse/contracts";
import {
  ArrowDown,
  ArrowRight,
  FileSearch,
  FlaskConical,
  Gauge,
  ListChecks,
  ShieldAlert,
  Swords,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

import {
  BandBadge,
  RiskBadge,
  SeverityBadge,
  StatementTypeBadge,
  ToneBadge,
} from "@/components/fp/badges";
import { Disclaimer, KeyValue } from "@/components/fp/layout";
import { evidenceHref } from "@/lib/evidence-link";
import { formatDate, formatDateTime, formatINR, formatMetric, formatNumber } from "@/lib/format";
import { label, STATEMENT_TYPES, stressRiskTone, type Tone } from "@/lib/presentation";
import { cn } from "@/lib/utils";

import {
  ClaimCard,
  claimRegistry,
  EvidenceChips,
  type ClaimLike,
  type LinkCtx,
  seniorClaimId,
} from "./claims";

type Dict = Record<string, unknown>;
const claimOf = (v: unknown) => v as ClaimLike;
const asList = (v: unknown) => (Array.isArray(v) ? (v as Dict[]) : []);

const CONFIDENCE_TONE: Record<string, Tone> = { high: "good", medium: "warning", low: "serious" };
const CHALLENGE_TONE: Record<string, Tone> = {
  major: "serious",
  moderate: "warning",
  minor: "info",
};
const RESOLUTION_TONE: Record<string, Tone> = {
  upheld: "serious",
  partially_upheld: "warning",
  rejected: "good",
};
const PRIORITY_TONE: Record<string, Tone> = { high: "serious", medium: "warning", low: "info" };
const STRENGTH_TONE: Record<string, Tone> = {
  strong: "good",
  moderate: "warning",
  weak: "serious",
};
const KIND_TYPE: Record<string, string> = {
  fact: "FACT",
  calculated_metric: "CALCULATED_METRIC",
  forecast: "FORECAST",
  assumption: "ASSUMPTION",
};
const CHALLENGES_SHOWN = 2;
const SECTIONS = [
  ["facts", "FACT"],
  ["calculated_metrics", "CALCULATED_METRIC"],
  ["forecasts", "FORECAST"],
  ["assumptions", "ASSUMPTION"],
  ["interpretations", "AI_INTERPRETATION"],
] as const;

function claimIdAt(run: AgentRun | null | undefined, path: string): string | undefined {
  return run?.claims?.find((c) => c.path === path)?.claim_id;
}

/** A numbered report section; the arrow carries the reader to the next one. */
function ReportSection({
  n,
  title,
  subtitle,
  icon: Icon,
  last = false,
  children,
}: {
  n: number;
  title: string;
  subtitle: string;
  icon: LucideIcon;
  last?: boolean;
  children: React.ReactNode;
}) {
  return (
    <>
      <section
        className="flex min-w-0 flex-col rounded-xl border bg-card shadow-xs"
        aria-labelledby={`report-${n}`}
      >
        <header className="flex items-start gap-3 border-b px-4 py-3 sm:px-5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <h3 id={`report-${n}`} className="text-sm font-semibold">
              <span className="tabular mr-1.5 text-muted-foreground">{n}.</span>
              {title}
            </h3>
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          </div>
        </header>
        <div className="min-w-0 p-4 sm:p-5">{children}</div>
      </section>
      {!last ? (
        <div className="flex justify-center py-1.5 text-muted-foreground" aria-hidden>
          <ArrowDown className="size-4" />
        </div>
      ) : null}
    </>
  );
}

function StressTable({ pack, inv, ctx }: { pack: EvidencePack; inv: Investigation; ctx: LinkCtx }) {
  const stressRun = inv.agent_analyses["stress_interpretation"];
  const out = (stressRun?.output ?? {}) as Dict;
  const worst =
    typeof out.most_damaging_scenario_evidence_id === "string"
      ? out.most_damaging_scenario_evidence_id
      : null;
  const baseline = pack.items.find((i) => i.id === "stress:baseline");
  const scenarios = pack.items.filter(
    (i) => /^stress:[^:]+$/.test(i.id) && i.id !== "stress:baseline",
  );
  const interp = new Map(asList(out.scenarios).map((s) => [String(s.scenario_evidence_id), s]));
  const v = (i: EvidenceItem, k: string) => (i.values as Dict)[k];
  const cash = (x: unknown) =>
    x === null || x === undefined ? "—" : formatINR(String(x), { compact: true });
  const link = (id: string) =>
    evidenceHref(ctx.entityId, id, { asOf: ctx.asOf, investigation: ctx.investigationId });
  return (
    <div className="flex flex-col gap-4">
      {baseline ? (
        <p className="text-xs text-pretty text-muted-foreground">
          <span className="font-medium text-foreground">Baseline, with no shock: </span>
          {baseline.text}
        </p>
      ) : null}
      <div className="overflow-x-auto rounded-lg border">
        <table className="tabular w-full min-w-[40rem] text-xs">
          <thead className="bg-muted/60 text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Scenario</th>
              <th className="px-3 py-2 text-left font-medium">Risk</th>
              <th className="px-3 py-2 text-right font-medium">Closing cash</th>
              <th className="px-3 py-2 text-right font-medium">Funds run out</th>
              <th className="px-3 py-2 text-right font-medium">Financial Health (projected)</th>
            </tr>
          </thead>
          <tbody>
            {scenarios.map((s) => {
              const applicable = v(s, "applicable") !== false;
              return (
                <tr key={s.id} className={cn("border-t", s.id === worst && "bg-status-critical/5")}>
                  <td className="px-3 py-2">
                    <Link href={link(s.id)} className="font-medium hover:text-primary">
                      {s.title.replace(/^Stress scenario: /, "")}
                    </Link>
                    {s.id === worst ? (
                      <span className="ml-2 inline-block">
                        <ToneBadge tone="critical" size="sm">
                          Most damaging (agent)
                        </ToneBadge>
                      </span>
                    ) : null}
                  </td>
                  {applicable ? (
                    <>
                      <td className="px-3 py-2">
                        <span className="flex items-center gap-1 whitespace-nowrap">
                          <ToneBadge tone={stressRiskTone(String(v(s, "risk_baseline")))} size="sm">
                            {label(String(v(s, "risk_baseline")))}
                          </ToneBadge>
                          <ArrowRight className="size-3 text-muted-foreground" aria-hidden />
                          <ToneBadge tone={stressRiskTone(String(v(s, "risk_scenario")))} size="sm">
                            {label(String(v(s, "risk_scenario")))}
                          </ToneBadge>
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        {cash(v(s, "baseline_closing_balance"))} →{" "}
                        <span className="font-semibold">{cash(v(s, "closing_balance"))}</span>
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        {v(s, "failure_date")
                          ? formatDate(String(v(s, "failure_date")))
                          : "Not within horizon"}
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        {v(s, "health_baseline_projected") !== undefined
                          ? `${formatNumber(String(v(s, "health_baseline_projected")), 1)} → `
                          : ""}
                        <span className="font-semibold">
                          {v(s, "health_scenario") !== undefined
                            ? formatNumber(String(v(s, "health_scenario")), 1)
                            : "—"}
                        </span>
                      </td>
                    </>
                  ) : (
                    <td colSpan={4} className="px-3 py-2 text-muted-foreground">
                      Not applicable to this entity
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {worst && interp.get(worst) ? (
        <ClaimCard
          claim={claimOf(interp.get(worst)!.key_vulnerability)}
          claimId={claimIdAt(
            stressRun,
            `scenarios[${asList(out.scenarios).findIndex((x) => x.scenario_evidence_id === worst)}].key_vulnerability`,
          )}
          ctx={ctx}
          className="border-status-critical/30"
        />
      ) : null}
      {out.resilience_summary ? (
        <ClaimCard
          claim={claimOf(out.resilience_summary)}
          claimId={claimIdAt(stressRun, "resilience_summary")}
          ctx={ctx}
        />
      ) : null}
      {pack.sha256 !== inv.evidence_pack.sha256 ? (
        <p className="text-[11px] text-muted-foreground">
          Note: these figures come from the current evidence pack, whose hash differs from the one
          this investigation used.
        </p>
      ) : (
        <p className="text-[11px] text-muted-foreground">
          Figures from the stress-test engine, in the same hashed evidence pack the agents used. The
          agents interpret them but never compute them.
        </p>
      )}
    </div>
  );
}

export function InvestigationReport({
  inv,
  pack,
}: {
  inv: Investigation;
  pack: EvidencePack | null;
}) {
  const ctx: LinkCtx = {
    entityId: inv.entity_id,
    investigationId: inv.investigation_id,
    asOf: inv.as_of,
  };
  const fa = inv.final_assessment;
  const registry = claimRegistry(inv);
  const health = fa.financial_health as Dict;
  const red = inv.red_team_run;
  const challenges = (inv.red_team_findings?.challenges ?? []) as Dict[];
  const responses = new Map(
    (fa.challenges_addressed as Dict[]).map((r) => [String(r.target_claim_id), r]),
  );
  const riskRun = inv.agent_analyses["risk_investigation"];
  const risks = asList((riskRun?.output as Dict | null)?.risks);
  const challengedIds = new Set(challenges.map((c) => String(c.target_claim_id)));
  const renderChallenge = (ch: Dict, i: number) => {
    const target = registry.get(String(ch.target_claim_id));
    const response = responses.get(String(ch.target_claim_id));
    const groups: [string, Dict[]][] = [
      ["Contradictory evidence", asList(ch.contradictory_evidence)],
      ["Alternative explanations", asList(ch.alternative_explanations)],
      ["Weak assumptions", asList(ch.weak_assumptions)],
    ];
    const missing = Array.isArray(ch.missing_information)
      ? (ch.missing_information as string[])
      : [];
    return (
      <article key={i} className="flex flex-col gap-2.5 rounded-lg border p-3">
        <div className="flex flex-wrap items-center gap-2">
          <ToneBadge tone={CHALLENGE_TONE[String(ch.severity)] ?? "neutral"}>
            {label(String(ch.severity))} challenge
          </ToneBadge>
          <span className="text-[11px] text-muted-foreground">
            against <span className="font-mono">{String(ch.target_claim_id)}</span>
            {target ? ` · ${target.title}` : ""}
          </span>
        </div>
        {target ? (
          <blockquote className="border-l-2 pl-3 text-xs text-pretty text-muted-foreground">
            “{target.statement}”
          </blockquote>
        ) : null}
        <p className="text-sm font-medium text-pretty">{String(ch.challenge_summary)}</p>
        {groups.map(([title, items]) =>
          items.length ? (
            <div key={title} className="flex flex-col gap-1">
              <span className="text-[11px] font-medium text-muted-foreground">{title}</span>
              <ul className="flex flex-col gap-1.5">
                {items.map((c, j) => (
                  <li key={j} className="flex flex-col gap-1 text-xs">
                    <span className="text-pretty">{claimOf(c).statement}</span>
                    <EvidenceChips ids={claimOf(c).evidence_ids} ctx={ctx} />
                  </li>
                ))}
              </ul>
            </div>
          ) : null,
        )}
        {missing.length ? (
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-medium text-muted-foreground">
              Missing information
            </span>
            <ul className="list-disc pl-4 text-xs">
              {missing.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {response ? (
          <div className="flex flex-col gap-1 rounded-md bg-muted/40 p-2">
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              Senior agent ruling:
              <ToneBadge tone={RESOLUTION_TONE[String(response.resolution)] ?? "neutral"} size="sm">
                Challenge {label(String(response.resolution)).toLowerCase()}
              </ToneBadge>
            </div>
            <p className="text-xs text-pretty">{claimOf(response.explanation).statement}</p>
          </div>
        ) : (
          <p className="text-[11px] text-muted-foreground">No ruling from the senior agent.</p>
        )}
      </article>
    );
  };
  const keyEvidence = [...inv.evidence_references]
    .sort((a, b) => b.cited_by.length - a.cited_by.length)
    .slice(0, 6);

  return (
    <div className="flex flex-col">
      <ReportSection
        n={1}
        title="Overall assessment"
        subtitle="Written by the Senior Financial Intelligence Agent from verified, challenged findings."
        icon={Gauge}
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <ToneBadge tone={fa.source === "senior_synthesis" ? "info" : "warning"}>
              {fa.source === "senior_synthesis"
                ? "Senior agent synthesis"
                : "Deterministic fallback (no AI synthesis)"}
            </ToneBadge>
            {inv.ai_mode === "demo_script" ? (
              <ToneBadge tone="warning">Demo script, not a live model</ToneBadge>
            ) : null}
            <span>As of {formatDate(inv.as_of)}</span>
            <span>·</span>
            <span>Run {formatDateTime(inv.started_at)}</span>
          </div>
          <p className="text-xl font-semibold text-balance sm:text-2xl">{fa.headline}</p>
          <div className="grid grid-cols-1 gap-4 border-y py-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">
                Early-warning risk (deterministic)
              </span>
              <div className="flex items-center gap-2">
                <RiskBadge level={fa.risk_level} />
                <span className="tabular text-sm text-muted-foreground">
                  index {fa.early_warning_index}/100
                </span>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">
                Financial Health (prototype, not a credit score)
              </span>
              <div className="flex items-center gap-2">
                <span className="tabular text-lg font-semibold">
                  {formatNumber(health.score as number, 1)}
                </span>
                <BandBadge band={(health.band as string | undefined) ?? null} />
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-muted-foreground">
                Confidence in this investigation
              </span>
              <div className="flex items-center gap-2">
                <ToneBadge tone={CONFIDENCE_TONE[inv.confidence.level] ?? "neutral"}>
                  {label(inv.confidence.level)}
                </ToneBadge>
                <span className="text-xs text-muted-foreground">
                  capped at {inv.confidence.cap} by rule
                </span>
              </div>
            </div>
          </div>
          {fa.overall_assessment ? (
            <ClaimCard
              claim={claimOf(fa.overall_assessment)}
              claimId={seniorClaimId(inv, "overall_assessment")}
              ctx={ctx}
              className="bg-muted/30"
            />
          ) : null}
          {inv.confidence.adjustments.length ? (
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer">
                Why confidence is capped at {inv.confidence.cap}
              </summary>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {inv.confidence.adjustments.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      </ReportSection>

      <ReportSection
        n={2}
        title="Key evidence"
        subtitle="The evidence items the verified conclusions cite most often."
        icon={FileSearch}
      >
        {keyEvidence.length === 0 ? (
          <p className="text-sm text-muted-foreground">No evidence was cited.</p>
        ) : (
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {keyEvidence.map((e) => (
              <li key={e.id} className="flex min-w-0 flex-col gap-2 rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <StatementTypeBadge type={KIND_TYPE[e.kind] ?? ""} />
                  <Link
                    href={evidenceHref(ctx.entityId, e.id, {
                      asOf: inv.as_of,
                      investigation: inv.investigation_id,
                    })}
                    className="ml-auto truncate font-mono text-[10px] text-muted-foreground hover:text-primary"
                  >
                    {e.id}
                  </Link>
                </div>
                <p className="text-sm font-medium">{e.title}</p>
                <p className="line-clamp-3 text-xs text-pretty text-muted-foreground">{e.text}</p>
                <div className="flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
                  Cited by {e.cited_by.length} claim{e.cited_by.length === 1 ? "" : "s"}:
                  {e.cited_by.slice(0, 6).map((c) => (
                    <Link
                      key={c}
                      href={evidenceHref(ctx.entityId, e.id, {
                        asOf: inv.as_of,
                        investigation: inv.investigation_id,
                        claim: c,
                      })}
                      className="rounded border px-1 font-mono hover:border-primary/40 hover:text-primary"
                    >
                      {c}
                    </Link>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </ReportSection>

      <ReportSection
        n={3}
        title="Primary risks"
        subtitle="Ranked by the Risk Investigation Agent, with likely causes and the strength of evidence."
        icon={ShieldAlert}
      >
        {risks.length ? (
          <ol className="flex flex-col gap-3">
            {risks.map((r, i) => {
              const id = claimIdAt(riskRun, `risks[${i}].risk`);
              return (
                <li key={i} className="flex flex-col gap-2 rounded-lg border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="tabular flex size-5 items-center justify-center rounded-full bg-muted text-[11px] font-semibold">
                      {i + 1}
                    </span>
                    <span className="text-sm font-semibold">{String(r.title)}</span>
                    <SeverityBadge severity={String(r.severity)} />
                    <ToneBadge
                      tone={STRENGTH_TONE[String(r.evidence_strength)] ?? "neutral"}
                      size="sm"
                    >
                      {label(String(r.evidence_strength))} evidence
                    </ToneBadge>
                    {id && challengedIds.has(id) ? (
                      <ToneBadge tone="warning" size="sm">
                        Challenged by red team
                      </ToneBadge>
                    ) : null}
                    {id ? (
                      <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                        {id}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-sm text-pretty">{claimOf(r.risk).statement}</p>
                  <EvidenceChips ids={claimOf(r.risk).evidence_ids} ctx={ctx} claimId={id} />
                  {asList(r.likely_causes).length ? (
                    <div className="flex flex-col gap-1 border-t pt-2">
                      <span className="text-[11px] font-medium text-muted-foreground">
                        Likely causes
                      </span>
                      <ul className="flex flex-col gap-1">
                        {asList(r.likely_causes).map((c, j) => (
                          <li key={j} className="flex flex-wrap items-start gap-2 text-xs">
                            <StatementTypeBadge type={claimOf(c).statement_type} />
                            <span className="min-w-0 flex-1 text-pretty">
                              {claimOf(c).statement}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ol>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">
              The Risk Investigation Agent produced no verified output, so these are the
              deterministic early warnings.
            </p>
            <ul className="flex flex-col divide-y">
              {inv.triggered_warnings.map((w) => (
                <li key={w.warning_id} className="flex items-start gap-3 py-2">
                  <SeverityBadge severity={w.severity} />
                  <div>
                    <p className="text-sm font-medium">{w.title}</p>
                    <p className="text-xs text-muted-foreground">{w.description}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </ReportSection>

      <ReportSection
        n={4}
        title="Contradictory evidence"
        subtitle="What the Red-Team Agent found against the specialists' conclusions, and how the senior agent ruled."
        icon={Swords}
      >
        {challenges.length === 0 && inv.disagreements.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {red
              ? "The red team raised no challenges and the agents agreed."
              : "The red team did not run."}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            {challenges.slice(0, CHALLENGES_SHOWN).map(renderChallenge)}
            {challenges.length > CHALLENGES_SHOWN ? (
              <details className="rounded-lg border border-dashed">
                <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
                  {challenges.length - CHALLENGES_SHOWN} more red-team challenge
                  {challenges.length - CHALLENGES_SHOWN === 1 ? "" : "s"}
                </summary>
                <div className="flex flex-col gap-3 border-t p-3">
                  {challenges
                    .slice(CHALLENGES_SHOWN)
                    .map((ch, i) => renderChallenge(ch, i + CHALLENGES_SHOWN))}
                </div>
              </details>
            ) : null}
            {inv.disagreements.map((d) => (
              <article
                key={d.id}
                className="flex flex-col gap-1.5 rounded-lg border border-dashed p-3"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <ToneBadge tone={d.severity === "major" ? "serious" : "warning"}>
                    {label(d.severity)} disagreement
                  </ToneBadge>
                  <span className="text-[11px] text-muted-foreground">
                    {d.agents.map(label).join(" vs ")} · {d.resolved ? "resolved" : "unresolved"}
                  </span>
                </div>
                <p className="text-sm text-pretty">{d.description}</p>
              </article>
            ))}
          </div>
        )}
      </ReportSection>

      <ReportSection
        n={5}
        title="Stress-test results"
        subtitle="Deterministic six-month projections under each scenario, before → after, with the agent's reading."
        icon={FlaskConical}
      >
        {pack ? (
          <StressTable pack={pack} inv={inv} ctx={ctx} />
        ) : (
          <p className="text-sm text-muted-foreground">
            The evidence pack could not be loaded, so the scenario figures are unavailable.
          </p>
        )}
      </ReportSection>

      <ReportSection
        n={6}
        title="Recommended actions"
        subtitle="Next steps for an analyst: what to verify, request or monitor. Never a lending decision."
        icon={ListChecks}
        last
      >
        {inv.recommendations.length ? (
          <ol className="flex flex-col gap-3">
            {(inv.recommendations as Dict[]).map((r, i) => (
              <li key={i} className="flex flex-col gap-2 rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="tabular flex size-5 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">
                    {i + 1}
                  </span>
                  <span className="min-w-0 flex-1 text-sm font-medium text-pretty">
                    {String(r.action)}
                  </span>
                  <ToneBadge tone={PRIORITY_TONE[String(r.priority)] ?? "neutral"}>
                    {label(String(r.priority))} priority
                  </ToneBadge>
                </div>
                <div className="flex flex-col gap-1 pl-7">
                  <span className="text-[11px] text-muted-foreground">Why</span>
                  <p className="text-xs text-pretty">{claimOf(r.rationale).statement}</p>
                  <EvidenceChips
                    ids={claimOf(r.rationale).evidence_ids}
                    ctx={ctx}
                    claimId={seniorClaimId(inv, `recommendations[${i}].rationale`)}
                  />
                </div>
              </li>
            ))}
            {fa.open_questions.length ? (
              <li className="rounded-lg border border-dashed p-3">
                <span className="text-[11px] font-medium text-muted-foreground">
                  Open questions
                </span>
                <ul className="mt-1 list-disc pl-4 text-xs">
                  {fa.open_questions.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              </li>
            ) : null}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">
            No recommendations: the senior agent did not produce a synthesis.
          </p>
        )}
      </ReportSection>

      <details className="group mt-6 rounded-xl border bg-card">
        <summary className="cursor-pointer px-4 py-3 text-sm font-medium sm:px-5">
          Appendix: full assessment by statement type, metrics used and audit
        </summary>
        <div className="flex flex-col gap-6 border-t p-4 sm:p-5">
          {SECTIONS.map(([key, type]) => {
            const items = (fa[key] as Dict[]) ?? [];
            if (!items.length) return null;
            const meta = STATEMENT_TYPES[type];
            return (
              <section key={key} className="flex flex-col gap-2">
                <h4 className="flex items-center gap-2 text-sm font-semibold">
                  <meta.icon className="size-4 text-muted-foreground" aria-hidden />
                  {meta.label}
                </h4>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {items.map((c, i) => (
                    <ClaimCard
                      key={i}
                      compact
                      claim={claimOf(c)}
                      claimId={seniorClaimId(inv, `${key}[${i}]`)}
                      ctx={ctx}
                    />
                  ))}
                </div>
              </section>
            );
          })}
          <section className="flex flex-col gap-2">
            <h4 className="text-sm font-semibold">Metrics the conclusions rest on</h4>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <tbody>
                  {inv.financial_metrics_used.map((m) => (
                    <tr key={m.code} className="border-t">
                      <td className="py-1.5 pr-2">
                        <Link
                          href={evidenceHref(ctx.entityId, m.evidence_id, {
                            asOf: inv.as_of,
                            investigation: inv.investigation_id,
                          })}
                          className="hover:text-primary"
                        >
                          {m.name}
                        </Link>
                      </td>
                      <td className="tabular py-1.5 text-right">
                        {formatMetric(m.value, m.unit, { code: m.code })}
                      </td>
                      <td className="tabular py-1.5 text-right text-muted-foreground">
                        cited {m.cited_by.length}×
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="grid grid-cols-1 gap-x-8 sm:grid-cols-2">
            <KeyValue
              items={[
                ["Verified claims", inv.claim_audit.claims_verified],
                ["Statements pruned", inv.claim_audit.claims_pruned],
                ["Verification issues caught", inv.claim_audit.issues_caught],
              ]}
            />
            <KeyValue
              items={[
                [
                  "Evidence references resolve",
                  inv.claim_audit.evidence_references_resolve ? "Yes" : "No",
                ],
                ["Evidence pack", inv.evidence_pack.sha256.slice(0, 12)],
                ["Model calls", inv.usage.calls],
              ]}
            />
          </section>
        </div>
      </details>

      <div className="mt-6">
        <Disclaimer>{inv.disclaimer}</Disclaimer>
      </div>
    </div>
  );
}
