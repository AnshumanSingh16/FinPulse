import type { Metadata } from "next";

import { ActionCenter } from "@/components/personal/action-center";

export const metadata: Metadata = { title: "Action Center" };

// Rendered per request: these pages read the URL (search params) and per-session data.
export const dynamic = "force-dynamic";

export default function Page() {
  return <ActionCenter />;
}
