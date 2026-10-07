import { type NextRequest, NextResponse } from "next/server";

import { isAllowed, isSameOrigin, MAX_PROXY_BODY_BYTES } from "@/lib/api/proxy-policy";
import { ConfigError, serverApiBaseUrl, serverApiKey } from "@/lib/env";

/**
 * Same-origin proxy from the browser to the FinPulse API (SECURITY.md). Adds the server's API
 * key, forwards only allow-listed requests from this app's own pages, and caps the body size.
 */

export const dynamic = "force-dynamic";

type Context = { params: Promise<{ path: string[] }> };

function problem(status: number, code: string, detail: string): NextResponse {
  return NextResponse.json(
    { type: "about:blank", title: detail, status, code, detail, errors: [], extra: {} },
    {
      status,
      headers: { "content-type": "application/problem+json", "cache-control": "no-store" },
    },
  );
}

async function forward(request: NextRequest, { params }: Context): Promise<NextResponse> {
  const path = (await params).path.join("/");
  const method = request.method;
  if (!isSameOrigin(method, request.headers, request.nextUrl.origin)) {
    return problem(403, "cross_origin_refused", "Requests must come from this application.");
  }
  if (!isAllowed(method, path)) {
    return problem(404, "not_proxied", "This request is not available from the browser.");
  }

  let body: string | undefined;
  if (method === "POST") {
    body = await request.text();
    if (new TextEncoder().encode(body).length > MAX_PROXY_BODY_BYTES) {
      return problem(413, "request_too_large", "The request body is too large.");
    }
  }

  let base: string;
  try {
    base = serverApiBaseUrl();
  } catch (error) {
    if (error instanceof ConfigError) return problem(500, "proxy_not_configured", error.message);
    throw error;
  }
  const headers: Record<string, string> = { accept: "application/json" };
  const key = serverApiKey();
  if (key) headers.authorization = `Bearer ${key}`;
  if (body !== undefined) headers["content-type"] = "application/json";
  const requestId = request.headers.get("x-request-id");
  if (requestId && /^[A-Za-z0-9._-]{1,128}$/.test(requestId)) headers["x-request-id"] = requestId;

  let upstream: Response;
  try {
    upstream = await fetch(`${base}/${path}`, {
      method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    return problem(502, "api_unreachable", "The FinPulse API could not be reached.");
  }
  const out = new Headers({ "cache-control": "no-store" });
  for (const name of ["content-type", "x-request-id", "retry-after"]) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new NextResponse(await upstream.arrayBuffer(), { status: upstream.status, headers: out });
}

export const GET = forward;
export const POST = forward;
