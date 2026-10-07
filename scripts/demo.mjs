#!/usr/bin/env node
// One command for the demo, on Windows, macOS and Linux: `npm run demo`.
//
//   1. checks Node and uv
//   2. creates .env from .env.example if it is missing
//   3. installs dependencies (npm install, uv sync) when they are missing
//   4. prepares PostgreSQL: migrations, starting the Docker database first if needed
//   5. seeds the synthetic entities (deterministic: the exact demo state)
//   6. starts the API and the web app; open http://localhost:3000/demo
//
// Each step is a plain command printed before it runs, so it can be repeated by hand.
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const api = path.join(root, "apps", "api");
const isWindows = process.platform === "win32";

function say(message) {
  console.log(`\n\x1b[1m▶ ${message}\x1b[0m`);
}

function fail(message) {
  console.error(`\n\x1b[31m✗ ${message}\x1b[0m\n`);
  process.exit(1);
}

/** Run a command, streaming its output. Returns true on success. */
function run(cmd, args, cwd = root) {
  console.log(
    `  $ ${[cmd, ...args].join(" ")}${cwd === root ? "" : `   (in ${path.relative(root, cwd)})`}`,
  );
  // A shell is needed on Windows to run npm/uv/docker shims (.cmd/.exe on PATH).
  const result = spawnSync(cmd, args, { cwd, stdio: "inherit", shell: isWindows });
  return result.status === 0;
}

function has(cmd) {
  const result = spawnSync(cmd, ["--version"], { stdio: "ignore", shell: isWindows });
  return result.status === 0;
}

// 1. Prerequisites ---------------------------------------------------------------------------
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 22 || (major === 22 && minor < 12)) {
  fail(
    `Node.js 22.12 or newer is required (found ${process.versions.node}). Get it from https://nodejs.org`,
  );
}
if (!has("uv")) {
  fail(
    "uv (the Python package manager the API uses) is not installed.\n" +
      (isWindows
        ? '  Install it in PowerShell:  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"\n'
        : "  Install it:  curl -LsSf https://astral.sh/uv/install.sh | sh\n") +
      "  then open a new terminal and run `npm run demo` again.",
  );
}

// 2. Configuration ---------------------------------------------------------------------------
if (!existsSync(path.join(root, ".env"))) {
  say("Creating .env from .env.example");
  copyFileSync(path.join(root, ".env.example"), path.join(root, ".env"));
}

// 3. Dependencies ----------------------------------------------------------------------------
if (
  !existsSync(path.join(root, "node_modules", "next")) &&
  !existsSync(path.join(root, "apps", "web", "node_modules", "next"))
) {
  say("Installing JavaScript dependencies");
  if (!run("npm", ["install"])) fail("npm install failed.");
}
say("Installing Python dependencies (first run downloads Python if needed)");
if (!run("uv", ["sync"], api)) fail("uv sync failed.");

// 4. Database --------------------------------------------------------------------------------
say("Preparing the database (migrations)");
if (!run("uv", ["run", "finpulse", "db", "init"], api)) {
  if (!has("docker")) {
    fail(
      "PostgreSQL is not reachable at the DATABASE_URL in .env, and Docker is not installed.\n" +
        "  Either install Docker Desktop (https://www.docker.com/products/docker-desktop) and run\n" +
        "  `npm run demo` again, or point DATABASE_URL in .env at any PostgreSQL 15+ database\n" +
        "  (a local install or a free Supabase project).",
    );
  }
  say("Starting PostgreSQL in Docker");
  if (!run("docker", ["compose", "-f", "infra/docker-compose.yml", "up", "-d", "--wait"])) {
    fail("Could not start the Docker database. Is Docker Desktop running?");
  }
  if (!run("uv", ["run", "finpulse", "db", "init"], api)) {
    fail("The database is running but migrations failed; see the error above.");
  }
}

// 5. Demo data -------------------------------------------------------------------------------
say("Loading the synthetic entities (the exact demo state)");
if (!run("uv", ["run", "finpulse", "db", "seed"], api))
  fail("Seeding failed; see the error above.");

// 6. Start -----------------------------------------------------------------------------------
say("Starting the API and the web app. Open http://localhost:3000/demo  (Ctrl+C stops both)");
await import("./dev.mjs");
