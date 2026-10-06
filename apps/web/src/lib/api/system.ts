import type { HealthResponse, ReadinessResponse } from "@finpulse/contracts";

import { unwrap, type ApiClient } from "./client";
import { ApiError, apiErrorFromResponse, networkError } from "./errors";

export type Probe<T> =
  { ok: true; data: T; latencyMs: number } | { ok: false; error: ApiError; latencyMs: number };

function elapsed(started: number): number {
  return Math.round(performance.now() - started);
}

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : networkError(error);
}

export async function probeHealth(client: ApiClient): Promise<Probe<HealthResponse>> {
  const started = performance.now();
  try {
    const data = await unwrap(client.GET("/health"));
    return { ok: true, data, latencyMs: elapsed(started) };
  } catch (error) {
    return { ok: false, error: asApiError(error), latencyMs: elapsed(started) };
  }
}

function isReadiness(value: unknown): value is ReadinessResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    "status" in value &&
    "checks" in value &&
    Array.isArray((value as { checks: unknown }).checks)
  );
}

/** Readiness answers 503 with a normal body when a dependency is down — that is data, not an error. */
export async function probeReadiness(client: ApiClient): Promise<Probe<ReadinessResponse>> {
  const started = performance.now();
  try {
    const { data, error, response } = await client.GET("/ready");
    if (data) return { ok: true, data, latencyMs: elapsed(started) };
    if (response.status === 503 && isReadiness(error)) {
      return { ok: true, data: error, latencyMs: elapsed(started) };
    }
    return { ok: false, error: apiErrorFromResponse(response, error), latencyMs: elapsed(started) };
  } catch (error) {
    return { ok: false, error: asApiError(error), latencyMs: elapsed(started) };
  }
}
