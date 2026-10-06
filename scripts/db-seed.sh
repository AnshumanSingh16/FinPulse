#!/usr/bin/env sh
# Generate every synthetic scenario and load it (idempotent: replaces existing copies).
# Uses DATABASE_URL from the environment or the repository-root .env. Extra arguments are passed
# through, e.g. `scripts/db-seed.sh --help`.
set -eu
cd "$(dirname "$0")/../apps/api"
exec uv run finpulse db seed "$@"
