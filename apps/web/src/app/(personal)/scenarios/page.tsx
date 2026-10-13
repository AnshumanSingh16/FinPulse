import type { Metadata } from "next";

import { ScenarioLab } from "@/components/personal/scenario-lab";

export const metadata: Metadata = { title: "Scenarios" };

// Rendered per request: these pages read the URL (search params) and per-session data.
export const dynamic = "force-dynamic";

export default function Page() {
  return <ScenarioLab />;
}
