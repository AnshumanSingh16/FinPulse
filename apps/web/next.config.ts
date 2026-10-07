import path from "node:path";
import { fileURLToPath } from "node:url";

import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

// One .env for the whole repo: load the root file so the web app and the API share config.
// Next.js has already loaded env files from apps/web and caches the result, so force a reload
// from the repository root. Real environment variables still take precedence over the file.
loadEnvConfig(repoRoot, process.env.NODE_ENV !== "production", console, true);

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Don't write AGENTS.md / CLAUDE.md into the app directory during development.
  agentRules: false,
  poweredByHeader: false,
  // The contracts package ships TypeScript source.
  transpilePackages: ["@finpulse/contracts"],
  turbopack: { root: repoRoot },
  async headers() {
    // Financial pages: never framed, sniffed or leaked through the Referer (SECURITY.md).
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          {
            key: "Content-Security-Policy",
            value: "frame-ancestors 'none'; object-src 'none'; base-uri 'self'",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
