import type { Metadata } from "next";

import { AffordWorkspace } from "@/components/personal/afford-workspace";

export const metadata: Metadata = { title: "Can I Afford This?" };

// Rendered per request: these pages read the URL (search params) and per-session data.
export const dynamic = "force-dynamic";

export default function Page() {
  return <AffordWorkspace />;
}
