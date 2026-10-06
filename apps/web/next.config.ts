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
  poweredByHeader: false,
  // The contracts package ships TypeScript source.
  transpilePackages: ["@finpulse/contracts"],
  turbopack: { root: repoRoot },
};

export default nextConfig;
