#!/usr/bin/env sh
# Drop every FinPulse table, re-apply migrations and re-seed. Refuses in production.
# Uses DATABASE_URL from the environment or the repository-root .env. Extra arguments are passed
# through, e.g. `scripts/db-reset.sh --help`.
set -eu
cd "$(dirname "$0")/../apps/api"
exec uv run finpulse db reset --yes "$@"
