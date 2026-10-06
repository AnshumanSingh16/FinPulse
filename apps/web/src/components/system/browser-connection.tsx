"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { getBrowserApiClient } from "@/lib/api/browser";
import { probeHealth, type Probe } from "@/lib/api/system";
import { ConfigError } from "@/lib/env";
import type { HealthResponse } from "@finpulse/contracts";

import { DetailList } from "./detail-list";
import { StatusBadge } from "./status-badge";

type State =
  | { kind: "checking" }
  | { kind: "config-error"; message: string }
  | { kind: "done"; probe: Probe<HealthResponse>; at: Date };

/**
 * Client-side check: the browser calls the API directly (NEXT_PUBLIC_API_URL). This is the path
 * that needs CORS to be configured, so it can fail while the server-side check succeeds.
 */
export function BrowserConnection() {
  const [state, setState] = useState<State>({ kind: "checking" });

  const check = useCallback(async () => {
    setState({ kind: "checking" });
    try {
      const probe = await probeHealth(getBrowserApiClient());
      setState({ kind: "done", probe, at: new Date() });
    } catch (error) {
      if (!(error instanceof ConfigError)) throw error;
      setState({ kind: "config-error", message: error.message });
    }
  }, []);

  useEffect(() => {
    // Run once on mount; the state update happens after the request resolves.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void check();
  }, [check]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Browser connection</CardTitle>
        <CardDescription>This browser → API, through CORS</CardDescription>
        <CardAction>
          {state.kind === "checking" ? (
            <StatusBadge tone="pending" label="Checking" />
          ) : state.kind === "config-error" ? (
            <StatusBadge tone="error" label="Not configured" />
          ) : state.probe.ok ? (
            <StatusBadge tone="ok" label="Connected" />
          ) : (
            <StatusBadge tone="error" label="Failed" />
          )}
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {state.kind === "config-error" ? (
          <p className="text-sm">{state.message}</p>
        ) : state.kind === "done" ? (
          state.probe.ok ? (
            <DetailList
              items={[
                ["Round trip", `${state.probe.latencyMs} ms`],
                ["Checked at", state.at.toLocaleTimeString()],
              ]}
            />
          ) : (
            <div className="flex flex-col gap-2">
              <DetailList
                items={[
                  ["Error", state.probe.error.code],
                  ["Detail", state.probe.error.detail ?? state.probe.error.title],
                ]}
              />
              {state.probe.error.isNetworkError ? (
                <p className="text-xs text-muted-foreground">
                  Check that the API is running, that NEXT_PUBLIC_API_URL points at it, and that
                  this page&apos;s origin is listed in CORS_ALLOWED_ORIGINS.
                </p>
              ) : null}
            </div>
          )
        ) : (
          <p className="text-sm text-muted-foreground">Contacting the API…</p>
        )}
        <div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void check()}
            disabled={state.kind === "checking"}
          >
            <RefreshCw aria-hidden />
            Check again
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
