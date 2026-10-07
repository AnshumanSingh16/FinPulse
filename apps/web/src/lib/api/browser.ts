import { createApiClient, type ApiClient } from "./client";
import { PROXY_PREFIX } from "./proxy-policy";

/**
 * API client for Client Components. It calls this app's own origin, where a route handler
 * (`app/api/finpulse/[...path]`) forwards an allow-listed set of requests to the API with the
 * server's key. The browser never holds a key and never talks to the API directly.
 */
export function getBrowserApiClient(): ApiClient {
  const origin = typeof window === "undefined" ? "http://localhost" : window.location.origin;
  return createApiClient({ baseUrl: `${origin}${PROXY_PREFIX}`, timeoutMs: 15000 });
}
