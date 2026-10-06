# finpulse-api

FastAPI backend for FinPulse. See the repository [README](../../README.md) for setup and
[ARCHITECTURE.md](../../ARCHITECTURE.md) for design.

```bash
uv sync                       # install (creates .venv)
uv run python -m finpulse     # run the API on API_HOST:API_PORT (reload in development)
uv run pytest                 # tests (set TEST_DATABASE_URL to include database tests)
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run alembic upgrade head   # apply migrations (none exist yet)
```
