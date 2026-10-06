#!/usr/bin/env node
// Start the API and the web app together; Ctrl+C stops both.
// Equivalent to running `npm run dev:api` and `npm run dev:web` in two terminals.
import { spawn } from "node:child_process";

const procs = [
  ["api", "npm", ["run", "dev:api"]],
  ["web", "npm", ["run", "dev:web"]],
].map(([name, cmd, args]) => {
  const child = spawn(cmd, args, { stdio: ["inherit", "pipe", "pipe"], env: process.env });
  const prefix = (line) => `[${name}] ${line}`;
  for (const stream of [child.stdout, child.stderr]) {
    let buffered = "";
    stream.on("data", (chunk) => {
      buffered += chunk;
      const lines = buffered.split("\n");
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
  for (const child of procs) if (child.exitCode === null) child.kill("SIGTERM");
  setTimeout(() => process.exit(code), 500);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
