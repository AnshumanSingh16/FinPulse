import type { Metadata } from "next";

import { PlanWorkspace } from "@/components/personal/plan-workspace";

export const metadata: Metadata = { title: "My plan" };

// Rendered per request: these pages read the URL (search params) and per-session data.
export const dynamic = "force-dynamic";

export default function Page() {
  return <PlanWorkspace />;
}
