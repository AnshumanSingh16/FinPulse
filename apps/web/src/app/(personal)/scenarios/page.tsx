import type { Metadata } from "next";
import { Suspense } from "react";

import { ScenarioLab } from "@/components/personal/scenario-lab";
import { Loading } from "@/components/personal/ui";

export const metadata: Metadata = { title: "Scenarios" };

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <ScenarioLab />
    </Suspense>
  );
}
