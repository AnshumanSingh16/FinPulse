import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** Mirrors DEVELOPMENT_PLAN.md. Static text: it describes the plan, not live system state. */
const PHASES = [
  { n: 0, name: "Foundations", detail: "Monorepo, API skeleton, logging, errors, web shell" },
  {
    n: 1,
    name: "Synthetic data",
    detail: "Personas with ground truth and simulated bureau events",
  },
  { n: 2, name: "Analytics", detail: "Normalisation, recurring flows, metric registry" },
  { n: 3, name: "Financial Passport", detail: "Seven-dimension transparent scoring" },
  { n: 4, name: "Early warning", detail: "Rules, change detection, lead-time evaluation" },
  { n: 5, name: "Stress testing", detail: "Scenario engine and resilience dimension" },
  { n: 6, name: "Product UI", detail: "Passport, health, alerts and stress views" },
  {
    n: 7,
    name: "Evidence & verification",
    detail: "Evidence packs, agent tools, grounding checks",
  },
  { n: 8, name: "Agents", detail: "Specialists, synthesiser, red team, orchestration" },
  { n: 9, name: "Investigation UI", detail: "Live trace, verified claims, challenges" },
  { n: 10, name: "Hardening", detail: "Security, performance, evaluation, demo cohort" },
] as const;

const CURRENT_PHASE = 0;

export function Roadmap() {
  return (
    <section aria-labelledby="roadmap-heading">
      <Card>
        <CardHeader>
          <CardTitle id="roadmap-heading">Roadmap</CardTitle>
          <CardDescription>Build order from the development plan</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {PHASES.map(({ n, name, detail }) => (
              <li key={n} className="flex items-start gap-3">
                <span className="mt-0.5 w-6 shrink-0 font-mono text-xs text-muted-foreground">
                  {n}
                </span>
                <div className="flex min-w-0 flex-col gap-0.5">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    {name}
                    {n === CURRENT_PHASE ? <Badge variant="secondary">Current</Badge> : null}
                  </div>
                  <p className="text-xs text-muted-foreground">{detail}</p>
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </section>
  );
}
