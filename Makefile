# Thin wrappers so common tasks are one word. Each target is a plain command you can run yourself.
.PHONY: help setup env db-up db-down dev dev-api dev-web migrate contracts format lint typecheck test build check

API := apps/api

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

setup: env ## Install all dependencies (Python via uv, JS via npm)
	cd $(API) && uv sync
	npm install

env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

db-up: ## Start local PostgreSQL (Docker)
	docker compose -f infra/docker-compose.yml up -d --wait

db-down: ## Stop local PostgreSQL (data is kept in a volume)
	docker compose -f infra/docker-compose.yml down

dev: ## Run API and web together
	npm run dev

dev-api: ## Run only the API (http://127.0.0.1:8000, docs at /docs)
	npm run dev:api

dev-web: ## Run only the web app (http://localhost:3000)
	npm run dev:web

migrate: ## Apply database migrations
	cd $(API) && uv run alembic upgrade head

contracts: ## Regenerate OpenAPI + TypeScript types after changing backend schemas
	npm run contracts:generate

format: ## Format all code
	cd $(API) && uv run ruff format . && uv run ruff check --fix .
	npm run format

lint: ## Lint all code
	cd $(API) && uv run ruff check . && uv run ruff format --check .
	npm run lint && npm run format:check

typecheck: ## Type-check all code
	cd $(API) && uv run mypy
	npm run typecheck

test: ## Run all tests
	cd $(API) && uv run pytest
	npm test

build: ## Production build of the web app
	npm run build

check: lint typecheck test build ## Everything CI runs except the contract drift check
