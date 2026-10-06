import type { Metadata } from "next";

import { PageHeader } from "@/components/fp/layout";
import { ApiErrorPanel } from "@/components/fp/states";
import { StressLab } from "@/components/stress/stress-lab";
import { getStressCatalogue } from "@/lib/api/finpulse";
import { entityContext, type EntityPageProps } from "@/lib/page";

export const metadata: Metadata = { title: "Stress Test" };

export default async function StressPage(props: EntityPageProps) {
  const { entityId, asOf } = await entityContext(props);
  let catalogue;
  try {
    catalogue = await getStressCatalogue();
  } catch (error) {
    return <ApiErrorPanel error={error} what="the stress scenarios" />;
  }
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Stress Test"
        description="Project cash month by month under hypothetical shocks — before and after. Every figure comes from the deterministic stress engine; scenarios are not forecasts."
      />
      <StressLab
        key={`${entityId}:${asOf ?? ""}`}
        catalogue={catalogue}
        entityId={entityId}
        asOf={asOf}
      />
    </div>
  );
}
