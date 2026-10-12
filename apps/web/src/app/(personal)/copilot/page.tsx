import type { Metadata } from "next";
import { Suspense } from "react";

import { CopilotChat } from "@/components/personal/copilot-chat";
import { Loading } from "@/components/personal/ui";

export const metadata: Metadata = { title: "AI Financial Copilot" };

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <CopilotChat />
    </Suspense>
  );
}
