import { browserApiBaseUrl } from "@/lib/env";

import { createApiClient, type ApiClient } from "./client";

/** API client for Client Components (runs in the browser; subject to CORS). */
export function getBrowserApiClient(): ApiClient {
  return createApiClient({ baseUrl: browserApiBaseUrl() });
}
