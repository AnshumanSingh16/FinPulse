import type {
  EvidencePack,
  Investigation,
  InvestigationSummary,
  Metric,
} from "@finpulse/contracts";
import { ArrowRight, Fingerprint, Link2 } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { EvidenceCard, SOURCE_LABEL } from "@/components/evidence/evidence-card";
import { RiskBadge, StatementTypeBadge } from "@/components/fp/badges";
import { PageHeader, Panel } from "@/components/fp/layout";
import { ApiErrorPanel, EmptyState, toErrorInfo } from "@/components/fp/states";
import { ClaimCard, claimRegistry, type ClaimRef } from "@/components/investigation/claims";
import {
  getEvidencePack,
  getInvestigation,
  getMetrics,
  listInvestigations,
} from "@/lib/api/finpulse";
import { formatDate, formatDateTime } from "@/lib/format";
import { entityContext, one, type EntityPageProps } from "@/lib/page";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Evidence" };

const KINDS = [
  ["fact", "Facts"],
  ["calculated_metric", "Calculated metrics"],
  ["forecast", "Forecasts"],
  ["assumption", "Assumptions"],
] as const;
const PAGE = 40;

export default async function EvidencePage(props: EntityPageProps) {
  const { entityId, asOf, search } = await entityContext(props);
  const investigationId = one(search.investigation);
  const claimParam = one(search.claim);
  const itemParam = one(search.item);
  const kind = one(search.kind);
  const source = one(search.source);

  let inv: Investigation | null = null;
  let list: InvestigationSummary[] = [];
  let pack: EvidencePack;
  let metrics: Metric[];
  try {
    [inv, list] = await Promise.all([
      investigationId ? getInvestigation(investigationId) : Promise.resolve(null),
      listInvestigations(entityId).catch(() => []),
    ]);
    // The evidence the investigation actually saw: its own as-of date.
    const packAsOf = inv?.as_of ?? asOf;
    const [p, m] = await Promise.all([
      getEvidencePack(entityId, packAsOf),
      getMetrics(entityId, packAsOf),
    ]);
    pack = p;
    metrics = m.metrics;
  } catch (error) {
    return <ApiErrorPanel error={toErrorInfo(error)} what="the evidence" />;
  }

  const byId = new Map(pack.items.map((i) => [i.id, i]));
  const metricOf = (id: string) =>
    id.startsWith("metric:") ? metrics.find((m) => m.code === id.slice(7)) : undefined;
  const registry = inv ? claimRegistry(inv) : new Map<string, ClaimRef>();
  const claims = [...registry.values()].sort((a, b) => order(a) - order(b));
  const claim = inv ? (registry.get(claimParam ?? "") ?? claims[0]) : undefined;
  const citing = (id: string) => claims.filter((c) => c.evidence_ids.includes(id));

  const href = (patch: Record<string, string | null | undefined>, hash?: string) => {
    const q = new URLSearchParams();
    const base = {
      asOf,
      investigation: investigationId,
      claim: claimParam,
      item: itemParam,
      kind,
      source,
      ...patch,
    };
    for (const [k, v] of Object.entries(base)) if (v) q.set(k, v);
    return `?${q.toString()}${hash ? `#${hash}` : ""}`;
  };

  const filtered = pack.items.filter(
    (i) => (!kind || i.kind === kind) && (!source || i.source === source),
  );
  const focused = itemParam ? byId.get(itemParam) : undefined;
  const sources = [...new Set(pack.items.map((i) => i.source))];
  const count = (k: string) =>
    pack.items.filter((i) => i.kind === k && (!source || i.source === source)).length;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Evidence"
        description="Every number an AI conclusion may cite comes from this pack, built by the deterministic engines. The agents can only reference items by id, and the verifier rejects anything that does not resolve."
      />

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border bg-card px-4 py-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <Fingerprint className="size-3.5" aria-hidden />
          Pack <code className="text-foreground">{pack.sha256.slice(0, 12)}</code>
        </span>
        <span>As of {formatDate(pack.as_of)}</span>
        <span className="tabular">{pack.items.length} items</span>
        <span>Pack {pack.pack_version}</span>
        <span className="truncate">
          Engines:{" "}
          {Object.entries(pack.engine_versions)
            .map(([k, v]) => `${k} ${v}`)
            .join(" · ")}
        </span>
      </div>

      {/* Claim tracer */}
      <Panel
        title={
          <span className="flex items-center gap-2">
            <Link2 className="size-4" aria-hidden />
            Trace an AI conclusion to its data
          </span>
        }
        description={
          inv
            ? `Investigation of ${formatDateTime(inv.started_at)}: pick any verified claim to see the evidence it rests on.`
            : "Choose an investigation to trace its conclusions."
        }
        actions={
          inv ? (
            <Link
              href={`/entities/${entityId}/investigation?${new URLSearchParams({ ...(asOf ? { asOf } : {}), investigation: inv.investigation_id })}`}
              className="flex items-center gap-1 text-xs font-medium text-primary"
            >
              Full report <ArrowRight className="size-3" aria-hidden />
            </Link>
          ) : null
        }
      >
        {!inv ? (
          list.length ? (
            <ul className="flex flex-col divide-y rounded-lg border">
              {list.slice(0, 6).map((s) => (
                <li key={s.investigation_id}>
                  <Link
                    href={href({ investigation: s.investigation_id, claim: null, item: null })}
                    className="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm hover:bg-muted/50"
                  >
                    <RiskBadge level={s.risk_level} size="sm" />
                    <span className="min-w-0 flex-1 truncate">{s.headline}</span>
                    <span className="text-xs text-muted-foreground">
                      {formatDateTime(s.started_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No investigations to trace yet">
              Run one from{" "}
              <Link
                className="text-primary"
                href={`/entities/${entityId}/investigation${asOf ? `?asOf=${asOf}` : ""}`}
              >
                AI Investigation
              </Link>
              . You can still browse every evidence item below.
            </EmptyState>
          )
        ) : (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <nav aria-label="Claims" className="max-h-[36rem] overflow-auto rounded-lg border">
              <ul className="divide-y">
                {claims.map((c) => (
                  <li key={c.claimId}>
                    <Link
                      href={href({ claim: c.claimId, item: null })}
                      aria-current={c.claimId === claim?.claimId ? "true" : undefined}
                      className={cn(
                        "flex flex-col gap-1 px-3 py-2 text-xs hover:bg-muted/50",
                        c.claimId === claim?.claimId &&
                          "bg-primary/5 shadow-[inset_3px_0_0_var(--primary)]",
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <span className="font-mono text-[11px] text-muted-foreground">
                          {c.claimId}
                        </span>
                        <span className="truncate text-muted-foreground">{c.title}</span>
                      </span>
                      <span className="line-clamp-2 text-foreground">{c.statement}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
            {claim ? (
              <div className="flex flex-col gap-3">
                <p className="text-xs text-muted-foreground">
                  {claim.title} · <span className="font-mono">{claim.claimId}</span>
                </p>
                <ClaimCard
                  claim={claim}
                  claimId={claim.claimId}
                  ctx={{ entityId, investigationId: inv.investigation_id, asOf: inv.as_of }}
                  className="bg-muted/30"
                />
                <h3 className="mt-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Supported by {claim.evidence_ids.length} evidence item
                  {claim.evidence_ids.length === 1 ? "" : "s"}
                </h3>
                {claim.evidence_ids.map((id) => {
                  const item = byId.get(id);
                  if (!item) {
                    return (
                      <p
                        key={id}
                        className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground"
                      >
                        <code>{id}</code> is not in the pack at this date.
                      </p>
                    );
                  }
                  const others = citing(id).filter((c) => c.claimId !== claim.claimId);
                  return (
                    <EvidenceCard
                      key={id}
                      item={item}
                      metric={metricOf(id)}
                      href={href({ item: id }, id)}
                      citedBy={
                        <CitedBy
                          claims={others}
                          href={(c) => href({ claim: c, item: null })}
                          label="Also cited by"
                        />
                      }
                    />
                  );
                })}
                {claim.based_on_claims?.length ? (
                  <p className="text-xs text-muted-foreground">
                    Builds on{" "}
                    {claim.based_on_claims.map((c, i) => (
                      <span key={c}>
                        {i ? ", " : ""}
                        <Link
                          href={href({ claim: c, item: null })}
                          className="font-mono text-primary"
                        >
                          {c}
                        </Link>
                      </span>
                    ))}
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                This investigation has no verified claims.
              </p>
            )}
          </div>
        )}
      </Panel>

      {/* Pack browser */}
      <Panel
        title="Evidence pack"
        description="Everything the agents were allowed to cite, filterable by kind and engine."
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <FilterRow
              options={[
                [null, `All kinds`],
                ...KINDS.map(([k, l]) => [k, `${l} · ${count(k)}`] as [string, string]),
              ]}
              value={kind ?? null}
              href={(v) => href({ kind: v, item: null })}
            />
            <FilterRow
              options={[
                [null, "All engines"],
                ...sources.map((s) => [s, SOURCE_LABEL[s] ?? s] as [string, string]),
              ]}
              value={source ?? null}
              href={(v) => href({ source: v, item: null })}
            />
          </div>
          {focused ? (
            <EvidenceCard
              item={focused}
              metric={metricOf(focused.id)}
              focused
              citedBy={
                inv ? (
                  <CitedBy
                    claims={citing(focused.id)}
                    href={(c) => href({ claim: c })}
                    label="Cited by"
                  />
                ) : null
              }
            />
          ) : itemParam ? (
            <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
              <code>{itemParam}</code> is not in the evidence pack at {formatDate(pack.as_of)}.
            </p>
          ) : null}
          <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {filtered.slice(0, PAGE).map((i) => (
              <li key={i.id}>
                <Link
                  href={href({ item: i.id })}
                  className={cn(
                    "flex h-full flex-col gap-1 rounded-lg border p-3 hover:border-primary/40 hover:bg-muted/30",
                    i.id === itemParam && "border-primary/60 bg-primary/5",
                  )}
                >
                  <span className="flex items-center gap-2">
                    <StatementTypeBadge type={i.kind.toUpperCase()} />
                    <span className="truncate font-mono text-[10px] text-muted-foreground">
                      {i.id}
                    </span>
                  </span>
                  <span className="text-sm font-medium">{i.title}</span>
                  <span className="line-clamp-2 text-xs text-muted-foreground">{i.text}</span>
                </Link>
              </li>
            ))}
          </ul>
          {filtered.length > PAGE ? (
            <p className="text-xs text-muted-foreground">
              Showing {PAGE} of {filtered.length}. Narrow by kind or engine to see the rest.
            </p>
          ) : null}
        </div>
      </Panel>
    </div>
  );
}

function order(c: ClaimRef): number {
  const agents = [
    "senior_synthesis",
    "financial_profile",
    "credit_intelligence",
    "early_warning_investigation",
    "risk_investigation",
    "stress_interpretation",
    "red_team",
  ];
  const i = agents.indexOf(c.agent);
  return (i < 0 ? agents.length : i) * 1000 + Number(c.claimId.replace(/\D/g, "") || 0);
}

function CitedBy({
  claims,
  href,
  label,
}: {
  claims: ClaimRef[];
  href: (claimId: string) => string;
  label: string;
}) {
  if (!claims.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1 border-t pt-2 text-[11px] text-muted-foreground">
      <span>{label}</span>
      {claims.map((c) => (
        <Link
          key={c.claimId}
          href={href(c.claimId)}
          title={c.statement}
          className="rounded border px-1 font-mono hover:border-primary/40 hover:text-primary"
        >
          {c.claimId}
        </Link>
      ))}
    </div>
  );
}

function FilterRow({
  options,
  value,
  href,
}: {
  options: [string | null, string][];
  value: string | null;
  href: (v: string | null) => string;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(([v, l]) => (
        <Link
          key={v ?? "all"}
          href={href(v)}
          aria-current={value === v ? "true" : undefined}
          className={cn(
            "rounded-full border px-2.5 py-1 text-xs",
            value === v
              ? "border-primary/50 bg-primary/10 font-medium text-foreground"
              : "text-muted-foreground hover:bg-muted",
          )}
        >
          {l}
        </Link>
      ))}
    </div>
  );
}
