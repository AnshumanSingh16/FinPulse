# FinPulse

AI-powered financial intelligence for individuals and small businesses with thin or no credit
history.

> Can we understand whether a financially thin-file person or business is financially
> trustworthy, and detect if their financial health is deteriorating before a traditional credit
> system would?

**Status: architecture and planning only. No application code has been written yet.**

## Core principle

Python performs deterministic financial calculations. AI agents investigate, reason, challenge and
explain those calculations. The LLM never invents financial metrics and is never the source of
truth — every number an agent states is checked against persisted, versioned engine output by a
deterministic verifier.

## Design documents

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design: frontend, backend, analytics, scoring, early warning, stress testing, agents, orchestration, errors, logging, testing |
| [DATA_MODEL.md](DATA_MODEL.md) | PostgreSQL schema (Supabase-compatible), lineage, versioning |
| [API_SPEC.md](API_SPEC.md) | REST API contract and agent tool contract |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Monorepo layout and module boundaries |
| [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) | Phased build plan with exit criteria |

## Planned stack

Next.js · TypeScript · Tailwind CSS · shadcn/ui · Recharts — Python · FastAPI · Pydantic —
PostgreSQL (Supabase-compatible) — LLM API with a custom Python orchestration layer.
