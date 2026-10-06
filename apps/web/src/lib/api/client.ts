import type { paths } from "@finpulse/contracts";
import createClient, { type Client } from "openapi-fetch";

import { ApiError, apiErrorFromResponse, networkError } from "./errors";

export type ApiClient = Client<paths>;

export type ApiClientOptions = {
  baseUrl: string;
  /** Per-request timeout. */
  timeoutMs?: number;
  /** Extra `fetch` init merged into every request (e.g. Next.js `cache` options). */
  init?: RequestInit;
  /** Injected in tests. */
  fetch?: typeof globalThis.fetch;
};

/**
 * Typed client for the FinPulse API. Paths, parameters and response bodies are all checked
 * against the types generated from the backend's OpenAPI document (`@finpulse/contracts`).
 */
export function createApiClient({
  baseUrl,
  timeoutMs = 5000,
  init,
  fetch: fetchImpl = globalThis.fetch,
}: ApiClientOptions): ApiClient {
  return createClient<paths>({
    baseUrl,
    fetch: (request: Request) =>
      fetchImpl(request, { ...init, signal: AbortSignal.timeout(timeoutMs) }),
  });
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/**
 * Await an openapi-fetch call and return its data, or throw `ApiError` for any failure —
 * including the backend being unreachable. Use for endpoints whose non-2xx responses are errors.
 */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await call;
  } catch (cause) {
    throw networkError(cause);
  }
  if (result.response.ok && result.data !== undefined) return result.data;
  throw apiErrorFromResponse(result.response, result.error);
}

export { ApiError };
