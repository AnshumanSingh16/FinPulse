import type { Metadata } from "next";
import { Suspense } from "react";

import { DocumentCenter } from "@/components/personal/document-center";
import { Loading } from "@/components/personal/ui";

export const metadata: Metadata = { title: "Documents" };

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <DocumentCenter />
    </Suspense>
  );
}
