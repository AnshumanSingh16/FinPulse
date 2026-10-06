import type { Investigation } from "@finpulse/contracts";
import Link from "next/link";

import { StatementTypeBadge } from "@/components/fp/badges";
import { evidenceHref } from "@/lib/evidence-link";
import { cn } from "@/lib/utils";

export type ClaimLike = {
  statement: string;
  statement_type: string;
  evidence_ids: string[];
  confidence: string;
  based_on_claims?: string[];
};

export type ClaimRef = { claimId: string; agent: string; title: string } & ClaimLike;

/** Every verified claim in the investigation, by id. */
export function claimRegistry(inv: Investigation): Map<string, ClaimRef> {
  const runs = [
    ...Object.values(inv.agent_analyses),
    inv.red_team_run,
    inv.senior_synthesis_run,
  ].filter((r): r is NonNullable<typeof r> => Boolean(r));
  const out = new Map<string, ClaimRef>();
  for (const run of runs) {
    for (const c of run.claims ?? []) {
      out.set(c.claim_id, { ...c, claimId: c.claim_id, agent: run.agent, title: run.title });
    }
  }
  return out;
}

/** The senior agent's registered id for a final-assessment claim at `path`. */
export function seniorClaimId(inv: Investigation, path: string): string | undefined {
  return inv.senior_synthesis_run?.claims?.find((c) => c.path === path)?.claim_id;
}

export type LinkCtx = { entityId: string; investigationId: string; asOf?: string };

export function EvidenceChips({
  ids,
  ctx,
  claimId,
}: {
  ids: string[];
  ctx: LinkCtx;
  claimId?: string;
}) {
  return (
    <div className="flex flex-wrap gap-1">
      {ids.map((id) => (
        <Link
          key={id}
          href={evidenceHref(ctx.entityId, id, {
            investigation: ctx.investigationId,
            claim: claimId,
            asOf: ctx.asOf,
          })}
          className="max-w-full truncate rounded border bg-muted/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground hover:border-primary/40 hover:text-primary"
          title="See the evidence"
        >
          {id}
        </Link>
      ))}
    </div>
  );
}

export function ClaimCard({
  claim,
  claimId,
  ctx,
  className,
  compact = false,
}: {
  claim: ClaimLike;
  claimId?: string;
  ctx: LinkCtx;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div className={cn("flex flex-col gap-2 rounded-lg border bg-card p-3", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <StatementTypeBadge type={claim.statement_type} />
        <span className="text-[11px] text-muted-foreground">{claim.confidence} confidence</span>
        {claimId ? (
          <Link
            href={evidenceHref(ctx.entityId, claim.evidence_ids[0] ?? "", {
              investigation: ctx.investigationId,
              claim: claimId,
              asOf: ctx.asOf,
            })}
            className="ml-auto font-mono text-[11px] text-muted-foreground hover:text-primary"
          >
            {claimId}
          </Link>
        ) : null}
      </div>
      <p className={cn("text-pretty", compact ? "text-xs" : "text-sm")}>{claim.statement}</p>
      <EvidenceChips ids={claim.evidence_ids} ctx={ctx} claimId={claimId} />
      {claim.based_on_claims?.length ? (
        <p className="text-[11px] text-muted-foreground">
          Builds on {claim.based_on_claims.join(", ")}
        </p>
      ) : null}
    </div>
  );
}
