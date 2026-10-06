import type { Investigation } from "@finpulse/contracts";
import { ArrowRight, ShieldAlert, Swords, Target } from "lucide-react";
import Link from "next/link";

import {
  BandBadge,
  RiskBadge,
  SeverityBadge,
  StanceBadge,
  ToneBadge,
} from "@/components/fp/badges";
import { Disclaimer, KeyValue, Panel } from "@/components/fp/layout";
import { evidenceHref } from "@/lib/evidence-link";
import { formatDate, formatDateTime, formatMetric, formatNumber } from "@/lib/format";
import { label, STATEMENT_TYPES, type Tone } from "@/lib/presentation";

import {
  ClaimCard,
  type ClaimRef,
  claimRegistry,
  type ClaimLike,
  type LinkCtx,
  seniorClaimId,
} from "./claims";
import { Pipeline, stepsFromInvestigation } from "./pipeline";

const SECTIONS = [
  ["facts", "FACT"],
  ["calculated_metrics", "CALCULATED_METRIC"],
  ["forecasts", "FORECAST"],
  ["assumptions", "ASSUMPTION"],
  ["interpretations", "AI_INTERPRETATION"],
] as const;

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

type Dict = Record<string, unknown>;
const SHOWN_CHALLENGES = 3;

function ChallengeItem({ ch, target, response }: { ch: Dict; target?: ClaimRef; response?: Dict }) {
  return (
    <li className="flex flex-col gap-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <ToneBadge tone={CHALLENGE_TONE[String(ch.severity)] ?? "neutral"}>
          {label(String(ch.severity))}
        </ToneBadge>
        <span className="font-mono text-[11px] text-muted-foreground">
          on {String(ch.target_claim_id)}
        </span>
      </div>
      {target ? (
        <blockquote className="border-l-2 pl-3 text-xs text-muted-foreground">
          {target.title}: “{target.statement}”
        </blockquote>
      ) : null}
      <p className="text-sm">{String(ch.challenge_summary)}</p>
      {response ? (
        <div className="flex flex-col gap-1.5 rounded-md bg-muted/40 p-2">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">Senior agent:</span>
            <ToneBadge tone={RESOLUTION_TONE[String(response.resolution)] ?? "neutral"}>
              Challenge {label(String(response.resolution)).toLowerCase()}
            </ToneBadge>
          </div>
          <p className="text-xs">{claimOf(response.explanation).statement}</p>
        </div>
      ) : null}
    </li>
  );
}
const claimOf = (v: unknown) => v as ClaimLike;

export function InvestigationReport({ inv }: { inv: Investigation }) {
  const ctx: LinkCtx = {
    entityId: inv.entity_id,
    investigationId: inv.investigation_id,
    asOf: inv.as_of,
  };
  const fa = inv.final_assessment;
  const registry = claimRegistry(inv);
  const health = fa.financial_health as Dict;
  const { steps, agents } = stepsFromInvestigation(inv);
  const challenges = (inv.red_team_findings?.challenges ?? []) as Dict[];
  const responses = new Map(
    (fa.challenges_addressed as Dict[]).map((r) => [String(r.target_claim_id), r]),
  );
  const resolutions = new Map(
    (fa.disagreements_resolved as Dict[]).map((r) => [String(r.disagreement_id), r]),
  );
  const robustness = inv.red_team_findings?.overall_robustness;

  return (
    <div className="flex flex-col gap-6">
      {/* Headline */}
      <section className="flex flex-col gap-4 rounded-xl border bg-card p-5 shadow-xs sm:p-6">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <ToneBadge tone={fa.source === "senior_synthesis" ? "info" : "warning"}>
            {fa.source === "senior_synthesis" ? "Senior agent synthesis" : "Deterministic fallback"}
          </ToneBadge>
          <span>As of {formatDate(inv.as_of)}</span>
          <span>·</span>
          <span>Run {formatDateTime(inv.started_at)}</span>
          <span>·</span>
          <span className="tabular">{(inv.duration_ms / 1000).toFixed(1)} s</span>
        </div>
        <h2 className="text-xl font-semibold text-balance sm:text-2xl">{fa.headline}</h2>
        <div className="grid grid-cols-1 gap-4 border-t pt-4 sm:grid-cols-3">
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
            <span className="text-xs text-muted-foreground">Confidence in this investigation</span>
            <div className="flex items-center gap-2">
              <ToneBadge tone={CONFIDENCE_TONE[inv.confidence.level] ?? "neutral"}>
                {label(inv.confidence.level)}
              </ToneBadge>
              <span className="text-xs text-muted-foreground">ceiling {inv.confidence.cap}</span>
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
            {inv.confidence.senior_rationale ? (
              <p className="mt-2">Senior agent: {inv.confidence.senior_rationale}</p>
            ) : null}
          </details>
        ) : null}
      </section>

      <Panel
        title="How this investigation ran"
        description="Deterministic engines, specialist agents, red-team challenge and senior synthesis, as recorded."
      >
        <Pipeline steps={steps} agents={agents} />
      </Panel>

      {/* Final assessment by statement type */}
      <Panel
        title="Final assessment"
        description="Every statement is typed and cites evidence the verifier checked. Select an id to see the supporting data."
      >
        <div className="flex flex-col gap-6">
          {SECTIONS.map(([key, type]) => {
            const items = (fa[key] as Dict[]) ?? [];
            if (!items.length) return null;
            const meta = STATEMENT_TYPES[type];
            return (
              <section key={key} className="flex flex-col gap-2">
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <meta.icon className="size-4 text-muted-foreground" aria-hidden />
                  {meta.label}
                  <span className="text-xs font-normal text-muted-foreground">{items.length}</span>
                </h3>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  {items.map((c, i) => (
                    <ClaimCard
                      key={i}
                      claim={claimOf(c)}
                      claimId={seniorClaimId(inv, `${key}[${i}]`)}
                      ctx={ctx}
                    />
                  ))}
                </div>
              </section>
            );
          })}
          {fa.open_questions.length ? (
            <section className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">Open questions</h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {fa.open_questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </Panel>

      {inv.recommendations.length ? (
        <Panel
          title={
            <span className="flex items-center gap-2">
              <Target className="size-4" aria-hidden />
              Recommended next steps
            </span>
          }
          description="What an analyst should verify, request or monitor. Never a lending decision."
        >
          <ol className="flex flex-col gap-3">
            {(inv.recommendations as Dict[]).map((r, i) => (
              <li key={i} className="flex flex-col gap-2 rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <ToneBadge tone={PRIORITY_TONE[String(r.priority)] ?? "neutral"}>
                    {label(String(r.priority))} priority
                  </ToneBadge>
                  <span className="text-sm font-medium">{String(r.action)}</span>
                </div>
                <ClaimCard
                  compact
                  claim={claimOf(r.rationale)}
                  claimId={seniorClaimId(inv, `recommendations[${i}].rationale`)}
                  ctx={ctx}
                  className="border-dashed"
                />
              </li>
            ))}
          </ol>
        </Panel>
      ) : null}

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <Panel
          title={
            <span className="flex items-center gap-2">
              <Swords className="size-4" aria-hidden />
              Red-team challenges
            </span>
          }
          description={
            inv.red_team_findings
              ? `${inv.red_team_findings.coverage.reviewed} of ${inv.red_team_findings.coverage.requested} significant claims reviewed.`
              : "The red team did not run."
          }
        >
          {challenges.length === 0 ? (
            <p className="text-sm text-muted-foreground">No challenges were raised.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {challenges.slice(0, SHOWN_CHALLENGES).map((ch, i) => (
                <ChallengeItem
                  key={i}
                  ch={ch}
                  target={registry.get(String(ch.target_claim_id))}
                  response={responses.get(String(ch.target_claim_id))}
                />
              ))}
              {challenges.length > SHOWN_CHALLENGES ? (
                <li>
                  <details>
                    <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                      {challenges.length - SHOWN_CHALLENGES} more challenge
                      {challenges.length - SHOWN_CHALLENGES === 1 ? "" : "s"}
                    </summary>
                    <ul className="mt-3 flex flex-col gap-3">
                      {challenges.slice(SHOWN_CHALLENGES).map((ch, i) => (
                        <ChallengeItem
                          key={i}
                          ch={ch}
                          target={registry.get(String(ch.target_claim_id))}
                          response={responses.get(String(ch.target_claim_id))}
                        />
                      ))}
                    </ul>
                  </details>
                </li>
              ) : null}
            </ul>
          )}
          {robustness ? (
            <div className="mt-3">
              <p className="mb-1 text-xs font-medium text-muted-foreground">Overall robustness</p>
              <ClaimCard compact claim={claimOf(robustness)} ctx={ctx} />
            </div>
          ) : null}
        </Panel>

        <Panel
          title={
            <span className="flex items-center gap-2">
              <ShieldAlert className="size-4" aria-hidden />
              Disagreements
            </span>
          }
          description="Found deterministically by comparing agents' stances with each other and with the engines."
        >
          {inv.disagreements.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              The agents and the deterministic engines agreed.
            </p>
          ) : (
            <ul className="flex flex-col gap-3">
              {inv.disagreements.map((d) => {
                const res = resolutions.get(d.id);
                return (
                  <li key={d.id} className="flex flex-col gap-2 rounded-lg border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <ToneBadge tone={d.severity === "major" ? "serious" : "warning"}>
                        {label(d.severity)}
                      </ToneBadge>
                      <span className="font-mono text-[11px] text-muted-foreground">{d.id}</span>
                      <span className="text-[11px] text-muted-foreground">
                        {d.resolved ? "resolved" : "unresolved"}
                      </span>
                    </div>
                    <p className="text-sm">{d.description}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {d.agents.map(label).join(" · ")}
                    </p>
                    {res ? (
                      <ClaimCard
                        compact
                        claim={claimOf(res.resolution)}
                        ctx={ctx}
                        className="border-dashed"
                      />
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </div>

      <Panel
        title="Specialist analyses"
        description="Each agent's verified claims. Unverifiable statements were removed before anything downstream saw them."
      >
        <div className="flex flex-col divide-y rounded-lg border">
          {Object.values(inv.agent_analyses).map((run) => {
            const stance = (run.output as Dict | null)?.risk_stance as string | undefined;
            return (
              <details key={run.agent} className="group">
                <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2.5 text-sm">
                  <span className="font-medium">{run.title}</span>
                  {stance ? <StanceBadge stance={stance} /> : null}
                  <span className="ml-auto text-xs text-muted-foreground">
                    {run.status === "succeeded"
                      ? `${(run.claims ?? []).length} claims`
                      : label(run.status)}
                  </span>
                </summary>
                <div className="grid grid-cols-1 gap-2 border-t bg-muted/20 p-3 md:grid-cols-2">
                  {(run.claims ?? []).map((c) => (
                    <ClaimCard key={c.claim_id} compact claim={c} claimId={c.claim_id} ctx={ctx} />
                  ))}
                  {run.error ? (
                    <p className="text-xs text-status-critical">
                      {run.error.code}: {run.error.message}
                    </p>
                  ) : null}
                </div>
              </details>
            );
          })}
        </div>
      </Panel>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
        <Panel
          title="Warnings investigated"
          description="Deterministic warnings in scope and whether an agent explained them."
        >
          <ul className="flex flex-col divide-y">
            {inv.triggered_warnings.map((w) => (
              <li key={w.warning_id} className="flex items-start gap-3 py-2">
                <span className="w-18 shrink-0">
                  <SeverityBadge severity={w.severity} />
                </span>
                <div className="min-w-0 flex-1">
                  <Link
                    href={evidenceHref(ctx.entityId, w.evidence_id, {
                      asOf: inv.as_of,
                      investigation: inv.investigation_id,
                    })}
                    className="text-sm font-medium hover:text-primary"
                  >
                    {w.title}
                  </Link>
                  <p className="text-[11px] text-muted-foreground">
                    {w.investigated
                      ? `Explained in ${w.investigation_claim_ids.join(", ")}`
                      : "Not explained by an agent"}
                  </p>
                </div>
              </li>
            ))}
            {inv.triggered_warnings.length === 0 ? (
              <li className="py-2 text-sm text-muted-foreground">No warnings were active.</li>
            ) : null}
          </ul>
        </Panel>
        <Panel
          title="Metrics the conclusions rest on"
          description="Values computed by the analytics engine; the agents only cite them."
        >
          <div className="max-h-80 overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-card text-muted-foreground">
                <tr>
                  <th className="py-1.5 text-left font-medium">Metric</th>
                  <th className="py-1.5 text-right font-medium">Value</th>
                  <th className="py-1.5 text-right font-medium">Cited by</th>
                </tr>
              </thead>
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
                      {m.cited_by.length}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <Panel title="Audit" description="What the deterministic verifier checked.">
        <div className="grid grid-cols-1 gap-x-8 sm:grid-cols-2">
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
              ["Evidence items in pack", inv.evidence_pack.items],
              ["Workflow", inv.workflow_version],
            ]}
          />
        </div>
        {inv.claim_audit.unmet_requirements.length ? (
          <ul className="mt-3 list-disc pl-5 text-xs text-muted-foreground">
            {inv.claim_audit.unmet_requirements.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        ) : null}
        <Link
          href={evidenceHref(ctx.entityId, inv.evidence_references[0]?.id ?? "", {
            asOf: inv.as_of,
            investigation: inv.investigation_id,
          })}
          className="mt-4 flex items-center gap-1 text-xs font-medium text-primary"
        >
          Explore all {inv.evidence_references.length} cited evidence items{" "}
          <ArrowRight className="size-3" aria-hidden />
        </Link>
      </Panel>

      <Disclaimer>{inv.disclaimer}</Disclaimer>
    </div>
  );
}
