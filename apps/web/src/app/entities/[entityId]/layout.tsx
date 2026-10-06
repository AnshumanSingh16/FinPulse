import { Building2, User } from "lucide-react";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { Suspense } from "react";

import { SyntheticBadge } from "@/components/fp/badges";
import { AsOfSelect, EntitySwitcher } from "@/components/shell/entity-controls";
import { ApiError } from "@/lib/api/errors";
import { getEntities, getMetrics } from "@/lib/api/finpulse";
import { formatMonth, titleCase } from "@/lib/format";

export default async function EntityLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ entityId: string }>;
}) {
  const { entityId } = await params;
  const entities = await getEntities();
  const entity = entities.find((e) => e.id === entityId);
  if (!entity) notFound();
  let coverage = null;
  try {
    coverage = (await getMetrics(entityId)).coverage;
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
  }
  const Icon = entity.kind === "individual" ? User : Building2;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 border-b pb-5 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-5" aria-hidden />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate text-lg font-semibold">{entity.display_name}</span>
              <SyntheticBadge />
            </div>
            <div className="text-xs text-muted-foreground">
              {titleCase(entity.kind)} · {titleCase(entity.segment)}
              {coverage?.first_transaction_on && coverage.last_transaction_on
                ? ` · data ${formatMonth(coverage.first_transaction_on)} – ${formatMonth(coverage.last_transaction_on)} · ${coverage.transaction_count.toLocaleString("en-IN")} transactions`
                : ""}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Suspense>
            <EntitySwitcher entities={entities} entityId={entityId} />
            {coverage?.first_transaction_on && coverage.last_transaction_on ? (
              <AsOfSelect
                first={coverage.first_transaction_on}
                last={coverage.last_transaction_on}
              />
            ) : null}
          </Suspense>
        </div>
      </div>
      {children}
    </div>
  );
}
