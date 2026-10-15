"use client";

import { useCallback, useContext, useEffect, useState } from "react";
import { DataVersion } from "@/components/data-version";

// Same origin in production (the Python server serves this app). For `npm run dev`, point at the API.
export const API = process.env.NEXT_PUBLIC_API ?? "";

export class ApiError extends Error {}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `Something went wrong (${res.status}).`;
    try {
      const body = await res.json();
      if (body?.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(msg);
  }
  return res.json() as Promise<T>;
}

export function get<T>(path: string): Promise<T> {
  return fetch(API + path, { cache: "no-store" }).then((r) => handle<T>(r));
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => handle<T>(r));
}

export function postForm<T>(path: string, form: FormData): Promise<T> {
  return fetch(API + path, { method: "POST", body: form }).then((r) => handle<T>(r));
}

export function del<T>(path: string): Promise<T> {
  return fetch(API + path, { method: "DELETE" }).then((r) => handle<T>(r));
}

/** Fetch JSON and re-fetch whenever the active dataset changes. */
export function useApi<T>(path: string | null) {
  const { version } = useContext(DataVersion);
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    if (!path) return;
    setLoading(true);
    get<T>(path)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [path]);

  useEffect(() => {
    load();
  }, [load, version]);

  return { data, error, loading, reload: load };
}
