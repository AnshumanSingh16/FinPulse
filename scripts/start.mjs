#!/usr/bin/env node
// `npm start`: the one command to run FinPulse locally (Windows, macOS, Linux).
//
//   1. checks the Node.js version
//   2. installs dependencies if they are missing
//   3. creates .env from .env.example if there is none (nothing in it is required)
//   4. starts the web app at http://localhost:3000 (or the next free port)
//
// It needs no Python, database or API key: the personal-finance product runs entirely inside the
// web app. (The separate business-risk module needs the Python API: see `npm run demo`.)
import { spawn, spawnSync } from "node:child_process";
import { copyFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";

function fail(message) {
  console.error(`\n✖ ${message}\n`);
  process.exit(1);
}

// 1. Node.js version ---------------------------------------------------------------------------
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 20 || (major === 20 && minor < 9)) {
  fail(
    `FinPulse needs Node.js 22 (you have ${process.versions.node}).\n` +
      "  Download the LTS version from https://nodejs.org, install it, open a NEW terminal and\n" +
      "  run `npm start` again.",
  );
}
if (major < 22) {
  console.warn(`! Node.js ${process.versions.node} works, but Node.js 22 is recommended.`);
}

// npm is a .cmd shim on Windows: run it through the shell there.
function npm(args, opts = {}) {
  return isWindows
    ? spawnSync(["npm", ...args].join(" "), { cwd: root, stdio: "inherit", shell: true, ...opts })
    : spawnSync("npm", args, { cwd: root, stdio: "inherit", ...opts });
}

// 2. Dependencies -------------------------------------------------------------------------------
const nextBin = path.join(root, "node_modules", "next", "package.json");
if (!existsSync(nextBin)) {
  console.log("→ Installing dependencies (first run only, takes a minute or two)…\n");
  const result = npm(["install", "--no-audit", "--no-fund"]);
  if (result.status !== 0) {
    fail(
      "npm install failed. Check your internet connection and try again.\n" +
        "  Behind a company proxy? Ask for its address and run: npm config set proxy <address>",
    );
  }
}

// 3. .env (optional settings) -------------------------------------------------------------------
const envPath = path.join(root, ".env");
if (!existsSync(envPath) && existsSync(path.join(root, ".env.example"))) {
  copyFileSync(path.join(root, ".env.example"), envPath);
  console.log("→ Created .env from .env.example (optional settings; nothing is required).");
}

// 4. Start the web app --------------------------------------------------------------------------
console.log(
  "\n→ Starting FinPulse… open the address printed below (usually http://localhost:3000).\n" +
    "  Press Ctrl+C to stop.\n",
);
const args = ["run", "dev", "-w", "@finpulse/web"];
const child = isWindows
  ? spawn(["npm", ...args].join(" "), { cwd: root, stdio: "inherit", shell: true })
  : spawn("npm", args, { cwd: root, stdio: "inherit" });

const stop = () => {
  if (child.exitCode !== null) return;
  if (isWindows)
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else child.kill("SIGINT");
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
child.on("exit", (code) => process.exit(code ?? 0));
