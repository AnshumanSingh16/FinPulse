import type { FieldError, ProblemDetails } from "@finpulse/contracts";

/**
 * The one error type API callers handle. Backend errors arrive as RFC 7807 problem+json and are
 * mapped field-for-field; transport failures (backend down, CORS, timeout) get `status: 0`.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly detail: string | null;
  readonly requestId: string | null;
  readonly fieldErrors: FieldError[];

  constructor(init: {
    status: number;
    code: string;
    title: string;
    detail?: string | null;
    requestId?: string | null;
    fieldErrors?: FieldError[];
    cause?: unknown;
  }) {
    super(init.detail ?? init.title, { cause: init.cause });
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.title = init.title;
    this.detail = init.detail ?? null;
    this.requestId = init.requestId ?? null;
    this.fieldErrors = init.fieldErrors ?? [];
  }

  get isNetworkError(): boolean {
    return this.status === 0;
  }
}

export function isProblemDetails(value: unknown): value is ProblemDetails {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.status === "number" && typeof v.code === "string" && typeof v.title === "string";
}

export function apiErrorFromResponse(response: Response, body: unknown): ApiError {
  const requestId = response.headers.get("x-request-id");
  if (isProblemDetails(body)) {
    return new ApiError({
      status: body.status,
      code: body.code,
      title: body.title,
      detail: body.detail ?? null,
      requestId: body.request_id ?? requestId,
      fieldErrors: body.errors ?? [],
    });
  }
  // A non-problem error body means something between us and the API answered (proxy, gateway).
  return new ApiError({
    status: response.status,
    code: "unexpected_response",
    title: response.statusText || "Unexpected response",
    detail: `The server answered ${response.status} without a problem+json body.`,
    requestId,
  });
}

export function networkError(cause: unknown): ApiError {
  const timedOut = cause instanceof DOMException && cause.name === "TimeoutError";
  return new ApiError({
    status: 0,
    code: timedOut ? "timeout" : "network_error",
    title: timedOut ? "The API did not respond in time" : "Could not reach the API",
    detail: cause instanceof Error ? cause.message : null,
    cause,
  });
}
