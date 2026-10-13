# FinPulse — "Can I afford this, and what should I do next?"

An agentic financial copilot for individuals in India. It runs entirely inside one Next.js app
(`apps/web`) — **no Python, database or API key needed**.

## Run it

```bash
npm start                # installs on first run; http://localhost:3000
```

Step-by-step setup (Windows, macOS, Linux): [RUN_LOCALLY.md](../RUN_LOCALLY.md).

Optional: put `ANTHROPIC_API_KEY=…` in the repository-root `.env` to enable the AI parts (live
web research, AI explanations, the AI copilot, PDF reading). Without it every other part works
and the UI says which mode is active. See `.env.example` for `PERSONAL_LLM_EFFORT`,
`FINPULSE_AI=off` and `FINPULSE_LIVE_RESEARCH=off`.

## Design

A light, consumer-fintech interface (Groww was a reference for clarity; FinPulse has its own
identity): warm-white canvas, charcoal type, FinPulse green as an accent for primary actions and
good outcomes, amber for caution and red only for serious problems. An ink-teal accent marks
agent work. Mobile-first: a top bar plus a bottom tab bar (Home, Afford, Ask, Steps, More) with
safe-area padding on phones; a compact, grouped sidebar (Plan · Assistant · Track · Your data) on
desktop.

- **Tokens** live in `src/app/globals.css` (`--brand-*`, `--ink-*`, `--line`, `--canvas`,
  `--surface*`, `--caution-*`, `--danger-*`, `--agent-*`, shadows, easing). Display type is Plus
  Jakarta Sans, body type Inter. Motion is short and respects `prefers-reduced-motion`.
- **Home**: greeting, "What do you want to plan today?", the goal box, four starting points
  (house, car, emergency fund, stress test), a money snapshot, one top insight, recent analyses and
  the latest agent activity.
- **Results**: a compact goal header; a verdict panel with the limiting factor, how many inputs are
  your own figures versus estimates (counted from the inputs' recorded sources), and a savings
  runway against the safety rules; three headline metrics; tabs for *Numbers*, *What if* (preset
  situations plus your own scenario, re-run on the server), *Why this result* and *Next steps*. A
  side rail shows how the agents worked (stages, tool calls, warnings — all from the run's real
  events), the proposed next action, and a follow-up box that asks the copilot about this run.
- **Ask FinPulse** can be pointed at a specific analysis; replies show which tools were used and,
  for full analyses, the live agent timeline.
- **What-if scenarios**, **Next steps**, **Activity log** and **Documents** share the same page
  header, filter chips with counts, empty states and cards. The activity log shows each event with
  its recorded actor (agent icon or you) and links back to the run.
- Shared pieces: `ui.tsx` (notices, sections, disclosure, dialogs, badges, empty states) and
  `kit.tsx` (agent identity, pulse mark, tabs, chips, deltas, meters).

## Five-minute demo

1. Open **Home** → **Try the demo profile**. A fictional profile loads (₹2,00,000 take-home,
   ₹25 lakh savings, ₹70,000 expenses, ₹15,000 EMIs, one dependent).
2. Type **"I want to buy a ₹75 lakh house"** in the goal box → the details screen shows what was
   understood and uses the saved figures → **Check if I can afford it**.
3. Watch the stages ("Understanding your goal" … "Preparing your next steps") tick off as the
   server finishes each one.
4. Results: EMI **₹52,069**, ₹4,50,000 of illustrative stamp duty/registration, **₹5,50,000** left
   in savings (4.0 months of cover) → *Potentially manageable, but with limited buffer*. The
   *Income stops for 6 months* scenario runs out of savings in month 5.
5. Show **Alternatives** (comfortable price ≈ ₹65.9 lakh, save ~5 months first, 25-year tenure)
   and the **Evidence** panel (every assumption with its source, every tool call with input and
   output).
6. **Approve these steps** (a confirmation dialog explains what approval does and doesn't do) — then show the server refusing shortcuts: items can't be ticked before
   approval, "Submit the loan application" can never be executed (no integration).
7. **Copilot**: "What if my income drops by 20%?", "Compare a ₹15 lakh car with a ₹20 lakh car."
8. **Documents**: upload `salary-slip-demo.txt` (download link on the page). Net pay ₹1,85,000
   differs from the profile's ₹2,00,000 and the slip hides an "ignore previous instructions" line:
   both are flagged; the next analysis's Verification Agent raises the mismatch.
9. **Audit Trail**: every goal, step, flag and approval, as recorded by the server.

To rehearse without AI even when a key is configured: set `FINPULSE_AI=off` in `.env` and restart.

## Architecture

```
src/lib/personal/
  finance/        deterministic engine (pure TypeScript, unit-tested)
    loan.ts         calculateEMI, calculateTotalRepayment, calculateTotalInterest,
                    generateAmortizationSchedule, calculateDownPayment, calculateLoanAmount
    health.ts       cash flow, debt-to-income, emergency cover, savings targets
    affordability.ts  rules (configurable thresholds) → comfortable / limited buffer / high strain
    scenarios.ts    month-by-month stress simulation, baseline comparison
    parse-inr.ts    "₹75 lakh", "1.2 crore", "15,00,000"
  agents/
    orchestrator.ts the workflow: plan → collect → research → analyse → stress → verify
                    → synthesise → act → request approval → audit
    runtime.ts      RunContext: validates every tool call (Zod), enforces limits
                    (40 tool calls, 120 s, 3 model calls per run), records calls and events
    tools.ts        the typed tool registry
    planner.ts      Financial Planner: required inputs, disclosed assumptions, the task plan
    research.ts     Research Agent: provider interface; illustrative + live (Anthropic web search)
    verification.ts Verification & Risk: consistency, document cross-checks, assumption challenges
    action.ts       Action Agent: checklist, documents, draft answers (prepare only)
    synthesis.ts    recommendation, alternatives, optional AI narrative + figure verifier
    copilot.ts      AI tool-use loop (max 6 turns) with a rule-based fallback
    llm.ts          the AI provider behind a small abstraction
  documents/      rule-based text/CSV extraction; AI PDF extraction when configured
  store.ts        per-session server memory; the approval state machine
src/app/api/personal/*   route handlers (validated, same-origin only, rate-limited)
src/app/(personal)/*     the eight sections
src/components/personal/ the UI
```

### How the orchestrator and tools work together

The orchestrator never computes anything itself. For each plan step it asks that step's agent to
call tools through `RunContext.callTool`, which (1) checks the run's limits, (2) validates the
input against the tool's Zod schema, (3) runs the pure function, and (4) records the call and
emits a `tool_call`/`tool_result` event. The browser's agent-activity panel is just those events,
streamed as NDJSON — there are no client-side animations pretending to be agents.

If the profile lacks income, expenses, savings or existing EMIs, the Planner stops the run with
status `needs_input` and asks for them. Smaller gaps (stamp duty, tenure, running costs) are
filled with **disclosed** assumptions that appear in the Evidence panel and as verification
findings.

### Where AI is (and is not) used

| Used for | Not used for |
|---|---|
| Live financing research (web search; a rate is kept only if its cited URL was actually retrieved) | Any financial figure: EMIs, savings, ratios, scenarios |
| A plain-English explanation (rejected if any ₹ or % figure doesn't match a tool output) | The affordability label (deterministic rules) |
| The copilot's tool choice and reply (unmatched figures are flagged) | Approvals or state changes |
| Reading PDFs (structured output; untrusted-data wrapper) | Reading .txt/.csv documents |

### Trust and safety

- **Approvals** are enforced in `store.ts` (`transitionActionPlan`): draft → awaiting review →
  approved/rejected → completed. Only a user request can approve, reject or complete; items can
  only be ticked after approval; items needing an external integration can never be executed.
- **Documents** are untrusted: text/CSV are parsed by rules, instruction-like text is flagged,
  and extracted values change the profile only after the user confirms them.
- **No fabricated market data**: without live research, rates are labelled illustrative
  everywhere they appear.
- Mutating routes require same-origin requests; bodies are size-capped and validated; uploads are
  limited to .txt/.csv/.pdf ≤ 2 MB; each session is rate-limited (30 expensive calls/min).
- Storage is server memory per browser session (httpOnly cookie). It resets on restart and is
  not shared between serverless instances — fine for a demo; swap `store.ts` for a database to
  persist.

## Tests

`npm test -w @finpulse/web` runs, among others:

- `finance/finance.test.ts` — EMI, amortization, health and scenario maths against values
  computed independently with closed-form formulas (e.g. ₹60 lakh at 8.5% for 240 months =
  ₹52,069.39), boundary cases (0% interest, zero principal, one-month loans, invalid inputs).
- `agents/orchestrator.test.ts` — the full workflow without AI: asks for missing inputs, runs
  every step on the demo profile, records every tool call, enforces the approval state machine.
- `agents/copilot.test.ts` — the AI tool-use loop with a scripted model: tool results go back to
  the model, invalid tool input is rejected, invented figures are flagged, provider failure falls
  back to rules.
- `documents/extract.test.ts` — the sample documents, prompt-injection flagging.

## Limits and honest caveats

- The AI paths were tested with a scripted model, not against the live API (no key in the build
  environment). Run once with a key before demoing live research.
- Thresholds (35%/50% debt-to-income, 3/6 months of cover, 10% buffer) are heuristics, shown with
  their reasoning; they are not lender criteria.
- A rate rise is modelled by recalculating the EMI for the same tenure; many Indian lenders extend
  the tenure instead.
- FinPulse is decision support, not financial advice, and cannot guarantee loan approval.
