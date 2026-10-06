import type { Metadata } from "next";

import { BackendStatus } from "@/components/system/backend-status";
import { BrowserConnection } from "@/components/system/browser-connection";
import { PageHeader } from "@/components/fp/layout";

export const metadata: Metadata = { title: "System status" };

// Status is checked on every request, never at build time.
export const dynamic = "force-dynamic";

export default function SystemPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="System status"
        description="Live checks that the web app, the FinPulse API and its database can reach each other."
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <BackendStatus />
        <BrowserConnection />
      </div>
    </div>
  );
}
