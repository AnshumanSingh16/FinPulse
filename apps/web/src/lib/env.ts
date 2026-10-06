/**
 * Typed access to the environment variables the web app reads. All of them live in the
 * repository-root `.env` (see `.env.example`); `next.config.ts` loads that file.
 *
 * Reads are lazy so that a missing variable surfaces as a visible configuration error on the page
 * that needs it, rather than crashing the build.
 */

export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigError";
  }
}

export function parseBaseUrl(name: string, value: string | undefined): string {
  if (!value || value.trim() === "") {
    throw new ConfigError(`${name} is not set. Copy .env.example to .env in the repository root.`);
  }
  let url: URL;
  try {
    url = new URL(value.trim());
  } catch {
    throw new ConfigError(`${name} is not a valid URL: "${value}"`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new ConfigError(`${name} must use http or https, got "${url.protocol}"`);
  }
  return url.toString().replace(/\/+$/, "");
}

/** Base URL the Next.js server uses to reach the API (may be an internal address). */
export function serverApiBaseUrl(): string {
  return parseBaseUrl("FINPULSE_API_URL", process.env.FINPULSE_API_URL);
}

/** Base URL code running in the browser uses. Inlined at build time — must be public-safe. */
export function browserApiBaseUrl(): string {
  // Must be written out literally for Next.js to inline it into the client bundle.
  return parseBaseUrl("NEXT_PUBLIC_API_URL", process.env.NEXT_PUBLIC_API_URL);
}
