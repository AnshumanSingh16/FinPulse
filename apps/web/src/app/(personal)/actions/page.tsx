import type { Metadata } from "next";
import { Suspense } from "react";

import { ActionCenter } from "@/components/personal/action-center";
import { Loading } from "@/components/personal/ui";

export const metadata: Metadata = { title: "Action Center" };

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <ActionCenter />
    </Suspense>
  );
}
