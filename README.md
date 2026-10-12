# FinPulse

**Your Financial Life. On Autopilot.**

FinPulse is an agentic AI financial copilot for people in India. Ask *"Can I afford a ₹75 lakh
house?"* and an orchestrator plans the question, then hands it to specialised agents that research
financing, calculate the loan and cash flow, stress-test the plan, verify the inputs, recommend,
and prepare next steps — which you review and approve. Every number comes from tested,
deterministic financial code; the AI never invents figures.

## Run it

```bash
npm start     # installs on first run, then open http://localhost:3000
```

Needs only **Node.js 22**. No database, no Python, no API key. New to this? Step-by-step for
Windows, macOS and Linux: **[RUN_LOCALLY.md](RUN_LOCALLY.md)**. On Windows you can also
double-click `start-finpulse.cmd`.

Optional: set `ANTHROPIC_API_KEY` in `.env` to turn on live rate research, AI explanations, the AI
copilot and PDF reading. Without it, everything else works in a clearly labelled deterministic
mode.

## What it does

- **Can I afford this?** — describe a purchase in plain English (house, car, education, business,
  anything). FinPulse asks only for what's missing, then shows the answer, the numbers, what
  happens if things go wrong, why, your alternatives, and a next-step checklist.
- **Agents you can watch** — Planner, Research, Analysis, Risk, Verification and Action agents
  run a real, recorded workflow; each stage is marked done only when it actually finishes.
- **Trust and control** — every assumption is labelled, every tool call and source is inspectable,
  and nothing happens without your approval (enforced on the server). FinPulse never submits
  applications or moves money.
- **Also**: what-if scenarios, a financial profile with the source of every value, document checks
  (salary slips, bank statements, loan quotes), an AI copilot, and a full activity log.

## How it's built

Next.js + TypeScript + Tailwind + Recharts, in `apps/web`:

```
src/lib/personal/finance/   deterministic financial engine (EMI, amortization, affordability rules,
                            stress scenarios) — unit-tested against independent calculations
src/lib/personal/agents/    orchestrator, agents, typed tool registry, AI provider (optional)
src/lib/personal/documents/ document extraction (rule-based; AI for PDFs when configured)
src/app/api/personal/       API routes (validated, same-origin, rate-limited)
src/app/(personal)/         the pages
src/components/personal/    UI and design system
```

Architecture, demo script, tests and limits: **[docs/PERSONAL.md](docs/PERSONAL.md)**.

## Development

```bash
npm run dev          # dev server (same as npm start, without the setup checks)
npm test             # unit tests
npm run lint         # ESLint
npm run typecheck    # TypeScript
npm run build        # production build
```

Decision support, not financial advice. Demo data is fictional.
