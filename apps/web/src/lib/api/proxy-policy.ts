/**
 * What the browser may ask the API to do, through the same-origin proxy
 * (`app/api/finpulse/[...path]/route.ts`). Everything else the UI needs is fetched by Server
 * Components with the server's key. Anything not listed here is refused before it reaches the
 * API, whatever role the server's key has.
 */

export const PROXY_PREFIX = "/api/finpulse";
export const MAX_PROXY_BODY_BYTES = 64 * 1024;

const UUID = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";

const ALLOWED: ReadonlyArray<{ method: "GET" | "POST"; path: RegExp }> = [
  { method: "GET", path: /^health$/ },
  { method: "POST", path: new RegExp(`^api/v1/entities/${UUID}/stress-test$`) },
  { method: "POST", path: new RegExp(`^api/v1/entities/${UUID}/investigations$`) },
  { method: "GET", path: new RegExp(`^api/v1/investigations/${UUID}/progress$`) },
  { method: "POST", path: /^api\/v1\/demo\/reset$/ },
];

export function isAllowed(method: string, path: string): boolean {
  return ALLOWED.some((rule) => rule.method === method && rule.path.test(path));
}

/**
 * Only this app's own pages may use the proxy: a cross-site page cannot make the server spend
 * its key (CSRF). Browsers send Sec-Fetch-Site on every request; Origin is checked as well for
 * state-changing requests.
 */
export function isSameOrigin(method: string, headers: Headers, appOrigin: string): boolean {
  const site = headers.get("sec-fetch-site");
  if (site !== null && site !== "same-origin") return false;
  const origin = headers.get("origin");
  if (method !== "GET" && origin !== appOrigin) return false;
  if (origin !== null && origin !== appOrigin) return false;
  return site !== null || origin !== null;
}
