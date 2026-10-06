import { describe, expect, it, vi } from "vitest";

import { createApiClient, unwrap } from "./client";
import { ApiError } from "./errors";
import { probeHealth, probeReadiness } from "./system";

const BASE = "http://api.test";

function jsonResponse(status: number, body: unknown, contentType = "application/json"): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": contentType, "x-request-id": "req_test" },
  });
}

function clientReturning(response: Response | Error) {
  const fetchMock = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit): Promise<Response> => {
      if (response instanceof Error) throw response;
      return response;
    },
  );
  return { client: createApiClient({ baseUrl: BASE, fetch: fetchMock }), fetchMock };
}

const health = {
  status: "ok",
  service: "finpulse-api",
  version: "0.1.0",
  environment: "test",
  timestamp: "2026-10-06T00:00:00Z",
};

describe("unwrap", () => {
  it("returns data for a successful response and calls the right URL", async () => {
    const { client, fetchMock } = clientReturning(jsonResponse(200, health));

    await expect(unwrap(client.GET("/health"))).resolves.toEqual(health);
    expect((fetchMock.mock.calls[0]?.[0] as Request).url).toBe(`${BASE}/health`);
  });

  it("maps problem+json to ApiError", async () => {
    const problem = {
      type: "https://finpulse.dev/errors/subject-not-found",
      title: "Not found",
      status: 404,
      code: "subject_not_found",
      detail: "Subject 42 does not exist.",
      request_id: "req_abc",
      errors: [],
      extra: {},
    };
    const { client } = clientReturning(jsonResponse(404, problem, "application/problem+json"));

    const error = await unwrap(client.GET("/health")).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 404,
      code: "subject_not_found",
      detail: "Subject 42 does not exist.",
      requestId: "req_abc",
    });
  });

  it("maps a non-problem error body to unexpected_response", async () => {
    const { client } = clientReturning(jsonResponse(502, { message: "bad gateway" }));

    await expect(unwrap(client.GET("/health"))).rejects.toMatchObject({
      status: 502,
      code: "unexpected_response",
      requestId: "req_test",
    });
  });

  it("maps a transport failure to a network ApiError", async () => {
    const { client } = clientReturning(new TypeError("fetch failed"));

    const error = await unwrap(client.GET("/health")).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).isNetworkError).toBe(true);
    expect((error as ApiError).code).toBe("network_error");
  });
});

describe("probes", () => {
  it("probeHealth reports success with latency", async () => {
    const { client } = clientReturning(jsonResponse(200, health));

    const probe = await probeHealth(client);

    expect(probe.ok).toBe(true);
    expect(probe.latencyMs).toBeGreaterThanOrEqual(0);
  });

  it("probeHealth reports failure instead of throwing", async () => {
    const { client } = clientReturning(new TypeError("fetch failed"));

    const probe = await probeHealth(client);

    expect(probe.ok).toBe(false);
  });

  it("probeReadiness treats a 503 readiness body as data", async () => {
    const notReady = {
      status: "not_ready",
      checks: [{ name: "database", status: "failed", latency_ms: null, detail: "down" }],
    };
    const { client } = clientReturning(jsonResponse(503, notReady));

    const probe = await probeReadiness(client);

    expect(probe).toMatchObject({ ok: true, data: notReady });
  });
});
