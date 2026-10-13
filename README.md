# FinPulse

**Every money decision, checked against your whole plan.**

Most "can I afford it?" tools check one purchase in isolation. Real life doesn't work that way: the
house, the car upgrade, your child's education and next year's holiday all draw on the same salary
and the same savings. FinPulse keeps **one plan** for a household in India — every goal, projected
month by month with inflation, income growth and loan EMIs — and checks every new decision
against all of it: *"Buying this flat now pushes the Japan trip back 24 months."*

Specialised agents (Planner, Research, Analysis, Risk, Verification, Action) do the work through
tested, deterministic financial tools; the AI never invents a figure. Nothing is submitted or moved
without your approval, enforced on the server.

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

- **My plan** — your goals in priority order (home, car, education, wedding, travel, business…).
  FinPulse projects them together: when each one is reached, what it needs each month, what's
  spare after them, and whether your emergency reserve holds. Change a date, a price or the order
  and the projection updates instantly.
- **Can I afford this?** — describe a purchase in plain English. The agents research financing,
  calculate the loan and cash flow, stress-test it, verify the inputs, and **check what it does to
  every other goal in your plan**. Then one click adds it to the plan.
- **Monthly check-in** — record what actually came in and went out. FinPulse compares it with the
  plan and tells you what happens if the trend continues ("spare money after goals falls from
  ₹41,635 to ₹22,752 a month").
- **Decide** — rent or buy a home, and prepay a loan or invest a lump sum: month-by-month
  simulations with the tipping point ("buying wins only if prices grow faster than 6.9% a year";
  "investing wins only above 9.4% after tax").
- **Ask FinPulse** — a copilot that answers with the same tools ("Am I on track for my goals?").
- **Trust and control** — every assumption labelled, every tool call and source inspectable, an
  activity log recorded by the server, documents treated as untrusted data, and approvals
  enforced on the backend. FinPulse never submits applications or moves money.
- **Your data stays** — saved on the server per browser session (a private file each), so your
  plan is still there tomorrow.

## How it's built

Next.js + TypeScript + Tailwind + Recharts, in `apps/web`:

```
src/lib/personal/finance/   deterministic financial engine (EMI, amortization, affordability rules,
                            stress scenarios, the multi-goal plan projection, rent-vs-buy,
                            prepay-vs-invest) — unit-tested against hand-checkable cases
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
