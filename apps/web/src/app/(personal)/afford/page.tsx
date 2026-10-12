import type { Metadata } from "next";
import { Suspense } from "react";

import { AffordWorkspace } from "@/components/personal/afford-workspace";
import { Loading } from "@/components/personal/ui";

export const metadata: Metadata = { title: "Can I Afford This?" };

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <AffordWorkspace />
    </Suspense>
  );
}
