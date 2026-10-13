import type { Metadata } from "next";

import { Overview } from "@/components/personal/overview";

export const metadata: Metadata = { title: "Overview" };

// Rendered per request: these pages read the URL (search params) and per-session data.
export const dynamic = "force-dynamic";

export default function Page() {
  return <Overview />;
}
