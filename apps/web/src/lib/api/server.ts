import "server-only";

import { serverApiBaseUrl, serverApiKey } from "@/lib/env";

import { createApiClient, type ApiClient } from "./client";

/**
 * API client for Server Components and route handlers. Never cached: data is per-request.
 * Sends the server's API key; the key never reaches the browser.
 */
export function getServerApiClient(): ApiClient {
  const key = serverApiKey();
  return createApiClient({
    baseUrl: serverApiBaseUrl(),
    init: { cache: "no-store" },
    headers: key ? { Authorization: `Bearer ${key}` } : undefined,
  });
}
