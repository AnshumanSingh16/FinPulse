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
import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import net from "node:net";
import os from "node:os";
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

/**
 * spawnSync that also works on Windows, where npm/uv/docker are shims that need a shell. The
 * command line is built here (arguments are fixed strings from this script) rather than passing
 * args alongside `shell: true`, which Node deprecates (DEP0190).
 */
function exec(cmd, args, options) {
  if (!isWindows) return spawnSync(cmd, args, options);
  const quote = (a) => (/[\s"&|<>^()]/.test(a) ? `"${a.replace(/"/g, '\\"')}"` : a);
  return spawnSync([cmd, ...args].map(quote).join(" "), { ...options, shell: true });
}

function show(cmd, args, cwd) {
  const where = cwd === root ? "" : `   (in ${path.relative(root, cwd)})`;
  console.log(`  $ ${[cmd, ...args].join(" ")}${where}`);
}

/** Run a command, streaming its output. Returns true on success. */
function run(cmd, args, cwd = root) {
  show(cmd, args, cwd);
  return exec(cmd, args, { cwd, stdio: "inherit" }).status === 0;
}

/** Run a command and capture its output (shown only if it matters). */
function quiet(cmd, args, cwd = root) {
  show(cmd, args, cwd);
  const result = exec(cmd, args, { cwd, encoding: "utf8" });
  return { ok: result.status === 0, output: `${result.stdout ?? ""}${result.stderr ?? ""}` };
}

function has(cmd) {
  return exec(cmd, ["--version"], { stdio: "ignore" }).status === 0;
}

// 1. Prerequisites ---------------------------------------------------------------------------
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 22 || (major === 22 && minor < 12)) {
  fail(
    `Node.js 22.12 or newer is required (found ${process.versions.node}). Get it from https://nodejs.org`,
  );
}
// The uv installer adds its folder to PATH only for new terminals: look there too.
if (!has("uv")) {
  const home = os.homedir();
  for (const dir of [path.join(home, ".local", "bin"), path.join(home, ".cargo", "bin")]) {
    if (existsSync(path.join(dir, isWindows ? "uv.exe" : "uv"))) {
      process.env.PATH = `${dir}${path.delimiter}${process.env.PATH ?? ""}`;
      break;
    }
  }
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
// The default DATABASE_URL points at the Docker database (infra/docker-compose.yml). If nothing
// answers there, start it, on a free port: Windows often reserves 5432 (Hyper-V/WSL port
// ranges) or a local PostgreSQL already uses it.
const envPath = path.join(root, ".env");
const DOCKER_URL =
  /^DATABASE_URL=postgresql:\/\/finpulse:finpulse@(?:localhost|127\.0\.0\.1):(\d+)\/finpulse\s*$/m;

function canListenOn(port, host) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.listen(port, host, () => server.close(() => resolve(true)));
  });
}

/** Free on loopback and on all interfaces (Docker Desktop on Windows binds 0.0.0.0). */
async function canListen(port) {
  return (await canListenOn(port, "127.0.0.1")) && (await canListenOn(port, "0.0.0.0"));
}

// Docker's own errors when a host port is taken or reserved: try the next port.
const PORT_PROBLEM =
  /port is already allocated|ports are not available|address already in use|bind/i;

say("Preparing the database (migrations)");
const firstTry = quiet("uv", ["run", "finpulse", "db", "init"], api);
if (firstTry.ok) {
  process.stdout.write(firstTry.output);
} else {
  const dockerUrl = readFileSync(envPath, "utf8").match(DOCKER_URL);
  if (!dockerUrl || !has("docker")) {
    process.stdout.write(firstTry.output);
    fail(
      "PostgreSQL is not reachable at the DATABASE_URL in .env" +
        (dockerUrl ? ", and Docker is not installed.\n" : ".\n") +
        "  Either install Docker Desktop (https://www.docker.com/products/docker-desktop), start it\n" +
        "  and run `npm run demo` again, or set DATABASE_URL in .env to any PostgreSQL 15+\n" +
        "  database (a local install or a free Supabase project).",
    );
  }
  const current = Number(dockerUrl[1]);
  let port = null;
  const candidates = [current, 5433, 5434, 5442, 15432, 25432, 35432, 45432, 54329, 55432];
  for (const candidate of [...new Set(candidates)]) {
    if (!(await canListen(candidate))) continue;
    say(`Starting PostgreSQL in Docker on port ${candidate} (the first run downloads it)`);
    process.env.FINPULSE_DB_PORT = String(candidate);
    const up = quiet("docker", ["compose", "-f", "infra/docker-compose.yml", "up", "-d", "--wait"]);
    if (up.ok) {
      port = candidate;
      break;
    }
    if (!PORT_PROBLEM.test(up.output)) {
      process.stdout.write(up.output);
      fail("Could not start the Docker database. Is Docker Desktop running?");
    }
    console.log(`  Port ${candidate} is in use or reserved on this machine; trying another.`);
  }
  if (port === null) fail("No free local port for the Docker database; set DATABASE_URL in .env.");
  if (port !== current) {
    const url = `postgresql://finpulse:finpulse@127.0.0.1:${port}/finpulse`;
    writeFileSync(
      envPath,
      readFileSync(envPath, "utf8").replace(DOCKER_URL, `DATABASE_URL=${url}`),
    );
    console.log(`  Port ${current} is not available here; .env now uses DATABASE_URL=${url}`);
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
