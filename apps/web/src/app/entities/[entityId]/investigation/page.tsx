import type { EvidencePack, Investigation, InvestigationSummary } from "@finpulse/contracts";
import { History } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { RiskBadge } from "@/components/fp/badges";
import { PageHeader, Panel } from "@/components/fp/layout";
import { ApiErrorPanel, EmptyState } from "@/components/fp/states";
import { InvestigationReport } from "@/components/investigation/report";
import { InvestigationRunner } from "@/components/investigation/runner";
import { TimelineView } from "@/components/investigation/timeline";
import {
  getEntities,
  getEvidencePack,
  getInvestigation,
  listInvestigations,
} from "@/lib/api/finpulse";
import { formatDate, formatDateTime } from "@/lib/format";
import { entityContext, one, type EntityPageProps } from "@/lib/page";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "AI Investigation" };

export default async function InvestigationPage(props: EntityPageProps) {
  const { entityId, asOf, search } = await entityContext(props);
  let list: InvestigationSummary[];
  let entityName = "this entity";
  try {
    const [l, entities] = await Promise.all([
      listInvestigations(entityId),
      getEntities().catch(() => []),
    ]);
    list = l;
    entityName = entities.find((e) => e.id === entityId)?.display_name ?? entityName;
  } catch (error) {
    return <ApiErrorPanel error={error} what="investigations" />;
  }
  const sorted = [...list].sort((a, b) => b.started_at.localeCompare(a.started_at));
  const selectedId = one(search.investigation) ?? sorted[0]?.investigation_id;
  let inv: Investigation | null = null;
  let pack: EvidencePack | null = null;
  let loadError: unknown = null;
  if (selectedId) {
    try {
      inv = await getInvestigation(selectedId);
      pack = await getEvidencePack(entityId, inv.as_of).catch(() => null);
    } catch (error) {
      loadError = error;
    }
  }
  const href = (id: string) => {
    const q = new URLSearchParams();
    if (asOf) q.set("asOf", asOf);
    q.set("investigation", id);
    return `?${q.toString()}`;
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="AI Investigation"
        description="A structured financial investigation, not a chat. Engines compute every number, and agents may only interpret verified evidence. Each step below corresponds to real backend execution."
      />

      <InvestigationRunner entityId={entityId} entityName={entityName} asOf={asOf} />

      {loadError ? <ApiErrorPanel error={loadError} what="the investigation" /> : null}

      {inv ? (
        <>
          <Panel
            title="Investigation timeline"
            description={`Recorded run of ${formatDateTime(inv.started_at)} · ${(inv.duration_ms / 1000).toFixed(1)} s · ${inv.usage.calls} model calls. Each step is rebuilt from the run's own stage records and events.`}
          >
            {inv.timeline ? (
              <TimelineView
                timeline={inv.timeline}
                ctx={{ entityId, asOf: inv.as_of, investigationId: inv.investigation_id }}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                This investigation was recorded before step timelines existed.
              </p>
            )}
          </Panel>

          <div className="flex flex-col gap-1">
            <h2 className="text-lg font-semibold">Investigation Report</h2>
            <p className="text-sm text-muted-foreground">
              {entityName} · as of {formatDate(inv.as_of)}. Read top to bottom: the conclusion, the
              evidence behind it, the risks, what argues against it, how it holds under stress, and
              what to do next.
            </p>
          </div>
          <InvestigationReport inv={inv} pack={pack} />
        </>
      ) : !loadError ? (
        <EmptyState title="No investigations yet">
          Start one above. Completed investigations are kept by the API (in memory, or on disk when
          INVESTIGATIONS_DIR is set).
        </EmptyState>
      ) : null}

      {sorted.length > 1 ? (
        <Panel
          title={
            <span className="flex items-center gap-2">
              <History className="size-4" aria-hidden />
              Previous investigations
            </span>
          }
          bodyClassName="p-0 sm:p-0"
        >
          <ul className="divide-y">
            {sorted.slice(0, 8).map((s) => (
              <li key={s.investigation_id}>
                <Link
                  href={href(s.investigation_id)}
                  className={cn(
                    "flex flex-wrap items-center gap-3 px-4 py-2.5 text-sm hover:bg-muted/50 sm:px-5",
                    s.investigation_id === selectedId && "bg-muted/60",
                  )}
                >
                  <RiskBadge level={s.risk_level} size="sm" />
                  <span className="min-w-0 flex-1 truncate">{s.headline}</span>
                  <span className="text-xs text-muted-foreground">
                    as of {formatDate(s.as_of)} · {formatDateTime(s.started_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}
