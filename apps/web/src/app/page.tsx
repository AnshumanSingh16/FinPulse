import { BackendStatus } from "@/components/system/backend-status";
import { BrowserConnection } from "@/components/system/browser-connection";
import { Roadmap } from "@/components/system/roadmap";

// Status is checked on every request, never at build time.
export const dynamic = "force-dynamic";

export default function OverviewPage() {
  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          FinPulse assesses the financial health of people and small businesses with little or no
          credit history. This build is the platform foundation: the checks below confirm that the
          web app, the API and the database can reach each other. Financial analysis arrives in the
          phases listed under Roadmap.
        </p>
      </header>

      <section aria-labelledby="status-heading" className="flex flex-col gap-4">
        <h2 id="status-heading" className="text-sm font-medium text-muted-foreground">
          Platform status
        </h2>
        <div className="grid gap-4 lg:grid-cols-3">
          <BackendStatus />
          <BrowserConnection />
        </div>
      </section>

      <Roadmap />
    </div>
  );
}
