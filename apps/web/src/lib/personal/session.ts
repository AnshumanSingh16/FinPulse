import "server-only";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { loadSession, type SessionState } from "./store";

const COOKIE = "fp_sid";
const ID_RE = /^[a-f0-9]{32}$/;

/** The caller's session, creating one (and its httpOnly cookie) on first use. */
export async function getSession(): Promise<SessionState> {
  const jar = await cookies();
  let id = jar.get(COOKIE)?.value;
  if (!id || !ID_RE.test(id)) {
    id = crypto.randomUUID().replace(/-/g, "");
    jar.set(COOKIE, id, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 24 * 7,
    });
  }
  return loadSession(id);
}

export function jsonError(status: number, message: string, details?: unknown) {
  return NextResponse.json({ error: message, ...(details ? { details } : {}) }, { status });
}

/** Read a JSON body with a size cap. Returns undefined when it is missing, too big or invalid. */
export async function readJson(request: Request, maxBytes = 64_000): Promise<unknown> {
  const length = Number(request.headers.get("content-length") ?? "0");
  if (length > maxBytes) return undefined;
  const text = await request.text();
  if (text.length > maxBytes) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}
