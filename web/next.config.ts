import type { NextConfig } from "next";

// Static export: the Python server (finpilot/api/server.py) serves the built files, so users only need Python.
const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  devIndicators: false,
};

export default config;
