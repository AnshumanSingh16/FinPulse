import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ApiError } from "@/lib/api/errors";
import { getServerApiClient } from "@/lib/api/server";
import { probeHealth, probeReadiness } from "@/lib/api/system";
import { ConfigError } from "@/lib/env";

import { DetailList } from "./detail-list";
import { StatusBadge } from "./status-badge";

// Renders plain strings, not the ApiError itself: in dev, React serialises component props, and
// errors wrapping low-level network failures break that serialisation.
function errorDetail(error: ApiError) {
  return (
    <DetailList
      items={[
        ["Error", error.code],
        ["Detail", error.detail ?? error.title],
        ...(error.requestId ? ([["Request ID", error.requestId]] as [string, string][]) : []),
      ]}
    />
  );
}

/**
 * Server-side checks: the Next.js server calls the API directly (FINPULSE_API_URL). Renders two
 * cards — the API itself and the database behind it.
 */
export async function BackendStatus() {
  let client;
  try {
    client = getServerApiClient();
  } catch (error) {
    if (!(error instanceof ConfigError)) throw error;
    return (
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Backend API</CardTitle>
          <CardDescription>Web server → API</CardDescription>
          <CardAction>
            <StatusBadge tone="error" label="Not configured" />
          </CardAction>
        </CardHeader>
        <CardContent className="text-sm">{error.message}</CardContent>
      </Card>
    );
  }

  const [health, readiness] = await Promise.all([probeHealth(client), probeReadiness(client)]);
  const database = readiness.ok
    ? readiness.data.checks.find((check) => check.name === "database")
    : undefined;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Backend API</CardTitle>
          <CardDescription>Web server → API, checked on page load</CardDescription>
          <CardAction>
            {health.ok ? (
              <StatusBadge tone="ok" label="Connected" />
            ) : (
              <StatusBadge tone="error" label="Unreachable" />
            )}
          </CardAction>
        </CardHeader>
        <CardContent>
          {health.ok ? (
            <DetailList
              items={[
                ["Service", health.data.service],
                ["Version", health.data.version],
                ["Environment", health.data.environment],
                ["Round trip", `${health.latencyMs} ms`],
              ]}
            />
          ) : (
            errorDetail(health.error)
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Database</CardTitle>
          <CardDescription>PostgreSQL, as seen by the API</CardDescription>
          <CardAction>
            {!readiness.ok ? (
              <StatusBadge tone="error" label="Unknown" />
            ) : database?.status === "ok" ? (
              <StatusBadge tone="ok" label="Ready" />
            ) : (
              <StatusBadge tone="warning" label="Not ready" />
            )}
          </CardAction>
        </CardHeader>
        <CardContent>
          {!readiness.ok ? (
            errorDetail(readiness.error)
          ) : database ? (
            <DetailList
              items={[
                ["Status", database.status],
                [
                  database.status === "ok" ? "Query latency" : "Detail",
                  database.status === "ok"
                    ? `${database.latency_ms ?? "—"} ms`
                    : (database.detail ?? "—"),
                ],
              ]}
            />
          ) : (
            <p className="text-sm text-muted-foreground">The API reported no database check.</p>
          )}
        </CardContent>
      </Card>
    </>
  );
}
