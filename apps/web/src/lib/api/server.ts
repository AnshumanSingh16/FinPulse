import "server-only";

import { serverApiBaseUrl } from "@/lib/env";

import { createApiClient, type ApiClient } from "./client";

/** API client for Server Components and route handlers. Never cached: data is per-request. */
export function getServerApiClient(): ApiClient {
  return createApiClient({ baseUrl: serverApiBaseUrl(), init: { cache: "no-store" } });
}
