import type { Metadata } from "next";

import { AuditTrail } from "@/components/personal/audit-trail";

export const metadata: Metadata = { title: "Audit Trail" };

// Rendered per request: these pages read the URL (search params) and per-session data.
export const dynamic = "force-dynamic";

export default function Page() {
  return <AuditTrail />;
}
