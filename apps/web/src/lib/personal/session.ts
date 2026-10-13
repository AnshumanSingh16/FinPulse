import "server-only";

import { cookies } from "next/headers";

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
      maxAge: 60 * 60 * 24 * 180,
    });
  }
  return loadSession(id);
}
