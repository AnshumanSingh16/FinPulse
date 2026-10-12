import type { Metadata } from "next";
import { Suspense } from "react";

import { AuditTrail } from "@/components/personal/audit-trail";
import { Loading } from "@/components/personal/ui";

export const metadata: Metadata = { title: "Audit Trail" };

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <AuditTrail />
    </Suspense>
  );
}
