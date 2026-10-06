import type { EntitySummary } from "@finpulse/contracts";
import type { ReactNode } from "react";
import { Suspense } from "react";

import { Sidebar } from "./sidebar";

export function AppShell({
  children,
  entities,
}: {
  children: ReactNode;
  entities: EntitySummary[];
}) {
  return (
    <div className="flex min-h-dvh flex-col lg:flex-row">
      <Suspense fallback={<aside className="hidden w-64 shrink-0 bg-sidebar lg:block" />}>
        <Sidebar entities={entities} />
      </Suspense>
      <div className="flex min-w-0 flex-1 flex-col">
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
