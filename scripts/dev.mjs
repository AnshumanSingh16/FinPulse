#!/usr/bin/env node
// Start the API and the web app together; Ctrl+C stops both.
// Equivalent to running `npm run dev:api` and `npm run dev:web` in two terminals.
import { spawn, spawnSync } from "node:child_process";

// On Windows, npm is a .cmd shim: it needs a shell, and stopping it means stopping its tree.
const isWindows = process.platform === "win32";

const procs = [
  ["api", "npm", ["run", "dev:api"]],
  ["web", "npm", ["run", "dev:web"]],
].map(([name, cmd, args]) => {
  const options = { stdio: ["inherit", "pipe", "pipe"], env: process.env };
  // On Windows pass one command line to the shell (args with `shell: true` is DEP0190).
  const child = isWindows
    ? spawn([cmd, ...args].join(" "), { ...options, shell: true })
    : spawn(cmd, args, options);
  const prefix = (line) => `[${name}] ${line}`;
  for (const stream of [child.stdout, child.stderr]) {
    let buffered = "";
    stream.on("data", (chunk) => {
      buffered += chunk;
      const lines = buffered.split(/\r?\n/);
      buffered = lines.pop() ?? "";
      for (const line of lines) process.stdout.write(prefix(line) + "\n");
    });
  }
  child.on("exit", (code) => {
    console.log(prefix(`exited with code ${code}`));
    shutdown(code ?? 1);
  });
  return child;
});

let stopping = false;
function shutdown(code) {
  if (stopping) return;
  stopping = true;
  for (const child of procs) {
    if (child.exitCode !== null) continue;
    if (isWindows)
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    else child.kill("SIGTERM");
  }
  setTimeout(() => process.exit(code), 500);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
