#!/usr/bin/env sh
# Restore the exact Sharma Electricals demo state: re-seed every synthetic entity (deterministic)
# and clear the running API's investigations. Refuses in production. See docs/DEMO.md.
# Extra arguments are passed through, e.g. `scripts/demo-reset.sh --api http://127.0.0.1:8000`.
set -eu
cd "$(dirname "$0")/../apps/api"
exec uv run finpulse demo reset "$@"
