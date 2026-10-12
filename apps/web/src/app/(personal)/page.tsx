import type { Metadata } from "next";
import { Suspense } from "react";

import { Overview } from "@/components/personal/overview";
import { Loading } from "@/components/personal/ui";

export const metadata: Metadata = { title: "Overview" };

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <Overview />
    </Suspense>
  );
}
