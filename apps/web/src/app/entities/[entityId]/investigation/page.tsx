import type { Investigation, InvestigationSummary } from "@finpulse/contracts";
import type { Metadata } from "next";
import Link from "next/link";

import { RiskBadge } from "@/components/fp/badges";
import { PageHeader, Panel } from "@/components/fp/layout";
import { ApiErrorPanel, EmptyState } from "@/components/fp/states";
import { InvestigationReport } from "@/components/investigation/report";
import { InvestigationRunner } from "@/components/investigation/runner";
import { getInvestigation, listInvestigations } from "@/lib/api/finpulse";
import { formatDate, formatDateTime } from "@/lib/format";
import { entityContext, one, type EntityPageProps } from "@/lib/page";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "AI Investigation" };

export default async function InvestigationPage(props: EntityPageProps) {
  const { entityId, asOf, search } = await entityContext(props);
  let list: InvestigationSummary[];
  try {
    list = await listInvestigations(entityId);
  } catch (error) {
    return <ApiErrorPanel error={error} what="investigations" />;
  }
  const sorted = [...list].sort((a, b) => b.started_at.localeCompare(a.started_at));
  const selectedId = one(search.investigation) ?? sorted[0]?.investigation_id;
  let inv: Investigation | null = null;
  let loadError: unknown = null;
  if (selectedId) {
    try {
      inv = await getInvestigation(selectedId);
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
        description="A structured financial investigation, not a chatbot: deterministic engines compute every number, specialist agents interpret only verified evidence, a red team challenges them, and a senior agent synthesises."
      />

      <InvestigationRunner entityId={entityId} asOf={asOf} />

      {sorted.length > 1 ? (
        <Panel title="Previous investigations" bodyClassName="p-0 sm:p-0">
          <ul className="divide-y">
            {sorted.slice(0, 6).map((s) => (
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

      {loadError ? <ApiErrorPanel error={loadError} what="the investigation" /> : null}
      {inv ? (
        <InvestigationReport inv={inv} />
      ) : !loadError ? (
        <EmptyState title="No investigations yet">
          Run one above. Completed investigations are kept by the API (in memory, or on disk when
          INVESTIGATIONS_DIR is set).
        </EmptyState>
      ) : null}
    </div>
  );
}
