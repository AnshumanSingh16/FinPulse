import type { Metadata } from "next";

import { DecideWorkspace } from "@/components/personal/decide-workspace";

export const metadata: Metadata = { title: "Decide" };

// Rendered per request: these pages read the URL (search params) and per-session data.
export const dynamic = "force-dynamic";

export default function Page() {
  return <DecideWorkspace />;
}
