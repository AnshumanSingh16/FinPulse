import type { EntitySummary } from "@finpulse/contracts";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { getEntities } from "@/lib/api/finpulse";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "FinPulse", template: "%s · FinPulse" },
  description:
    "Financial intelligence for individuals and small businesses with thin or no credit history.",
};

async function loadEntities(): Promise<EntitySummary[]> {
  try {
    return await getEntities();
  } catch {
    return []; // pages show the API error themselves; the shell still renders
  }
}

export default async function RootLayout({ children }: { children: ReactNode }) {
  const entities = await loadEntities();
  return (
    <html lang="en">
      <body>
        <AppShell entities={entities}>{children}</AppShell>
      </body>
    </html>
  );
}
