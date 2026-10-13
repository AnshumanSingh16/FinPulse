import type { Metadata } from "next";

import { CopilotChat } from "@/components/personal/copilot-chat";

export const metadata: Metadata = { title: "AI Financial Copilot" };

// Rendered per request: these pages read the URL (search params) and per-session data.
export const dynamic = "force-dynamic";

export default function Page() {
  return <CopilotChat />;
}
