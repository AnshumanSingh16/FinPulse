#!/usr/bin/env sh
# Create the database if it is missing and apply all migrations.
# Uses DATABASE_URL from the environment or the repository-root .env. Extra arguments are passed
# through, e.g. `scripts/db-init.sh --help`.
set -eu
cd "$(dirname "$0")/../apps/api"
exec uv run finpulse db init "$@"
