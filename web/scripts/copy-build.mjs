// Copy the static export into the Python package so `python run.py` can serve it.
import { cpSync, rmSync } from "node:fs";
import { resolve } from "node:path";

const out = resolve(import.meta.dirname, "..", "out");
const dest = resolve(import.meta.dirname, "..", "..", "finpilot", "web");
rmSync(dest, { recursive: true, force: true });
cpSync(out, dest, { recursive: true });
console.log("Copied build to", dest);
