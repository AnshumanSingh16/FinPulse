# FinPulse — every money decision, checked against your whole plan

An agentic financial planner for households in India. It runs entirely inside one Next.js app
(`apps/web`) — **no Python, database or API key needed**.

## The idea

A single-purchase affordability check answers the wrong question, in the wrong way. The wrong
question, because goals compete for the same money; the wrong way, because it plays out one
future where every assumption comes true. FinPulse fixes both.

The question is answered across **possible futures**, not one: "Every goal lands on time in 97% of
1,000 simulated futures; buying this flat now drops that to 0%; moving it 12 months later brings
it back to 94%." A **Strategist agent** searches for that kind of fix itself.

 "Can I afford a ₹75 lakh flat?"
depends on what else the same salary and savings must pay for: the car due in 18 months, a child's
education in 12 years, next year's trip. FinPulse is built around **one plan per household**:

1. **The plan** (`finance/plan.ts`) — every goal with its price in today's money, target month,
   priority, inflation and funding (cash or loan). A month-by-month projection grows income and
   costs, earns returns on balances, keeps an emergency reserve first, funds goals in priority
   order with the contribution each needs to land on time, buys them when funded, starts their
   EMIs, and reports which land on time, which are late (and by how much) and which are out of
   reach.
2. **Decisions are checked against the plan.** The affordability workflow's Analysis agent runs
   `check_plan_impact`: the plan with and without the purchase. "Buying this now pushes *Family
   trip to Japan* from Aug 2027 to Aug 2029." Those become verification findings and the first
   item of the action checklist; one click adds the purchase to the plan.
3. **The plan is kept honest monthly.** Check-ins record actual take-home and spending; the pulse
   compares them with the plan and re-projects with the recent trend ("if this continues…").
4. **The recurring decisions** — rent vs buy, prepay vs invest — are simulations with explicit
   assumptions and a tipping point, not rules of thumb.
5. **Probability, not a single path** (`finance/montecarlo.ts`). The same engine runs along 1,000
   seeded random futures: yearly market returns around the assumed return (15-point volatility on
   long-term money), living-cost inflation (±1.5 points) with each goal's price following it,
   uneven raises, a 3% yearly chance of a 3–9 month gap in income (7% plus monthly swings for
   variable earners), and a 10% yearly chance of an emergency cost of ~1.5 months of spending.
   It reports each goal's chance of landing on time and within a year, the chance money never
   runs out, the range of savings over time, **which risk costs the plan most** (each switched
   off in turn, same futures) and **room to spend** (the most extra monthly spending that keeps
   every goal on time in 80% of futures — or the cut needed to get there). With every risk off it
   reproduces the single-path projection exactly; that is tested.
6. **The Strategist agent** (`finance/optimize.ts`, `agents/strategist.ts`) changes plans instead
   of only judging them. It searches concrete, human-sized changes — move a goal 6/12/24 months,
   trim a budget 10/20%, change a down payment or loan tenure, reorder priorities, spend 5/10% less
   — scoring each on the same futures (common random numbers, so a change wins on merit, not
   luck). Each change carries a disruption cost, so it prefers fewer, smaller changes; each round
   screens every candidate on a small sample and re-scores the best few on a larger one; the
   final proposal is re-checked on **fresh futures** it never saw. Proposals wait for the person:
   applying is a user action, refused if the plan or finances changed since the search.
   It runs on its own ("Find a better plan"), inside every affordability analysis ("best way to
   fit it in"), and from the copilot ("Find me a better plan").

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

1. **Home → Try the demo.** A fictional household loads: Riya, ₹2,00,000 take-home, ₹25 lakh
   savings, ₹70,000 expenses, ₹15,000 EMIs (30 left), one dependent — plus three goals (daughter's
   education in 12 years, a ₹14 lakh car in 18 months on a loan, a ₹4.5 lakh trip in 10 months)
   and three monthly check-ins.
2. **Home** shows the plan — **97% chance all 3 goals land on time** — and the top insight from
   the check-ins: saving ₹17,667 a month less than planned.
3. **My plan**: the odds headline, the range of outcomes (median and the band 80% of futures fall
   in), each goal's chance of landing on time, what could knock it off course, and room to spend
   (about ₹36,000 a month at 80% confidence). Edit a date: the odds re-simulate as you type. **Find a
   better plan** → the Strategist runs live and finds nothing worth changing (the plan already
   works).
4. **Can I afford this?** → "I want to buy a ₹75 lakh house" → **Check if I can afford it**. Ten
   stages run, including **Checking your other goals** and **Finding the best way to fit it in**.
   Results: EMI ₹52,069, ₹5,50,000 left in savings → *limited buffer* — and **chance every goal
   lands on time 97% → 0%** (the trip 98% → 0%, the car 99% → 72%). **Best way to fit it in**,
   found by the Strategist in 71 simulations: *move the house 12 months later* → about 93–94% on
   fresh futures. **Add to my plan**, then on My plan **Find a better plan** → the same proposal, with
   its five recorded steps → **Apply to my plan** → about 93%.
5. **Next steps**: the first checklist item is "Re-plan the goals this purchase moves". Approve —
   the server refuses shortcuts (no ticking before approval; "Submit the loan application" can
   never be executed).
6. **Rent, buy or prepay?** Rent vs buy for ₹75 lakh against ₹25,000 rent: renting and investing
   is ahead by ₹46.8 lakh after 15 years unless prices grow faster than 6.93% a year. Prepay vs
   invest ₹5 lakh on a ₹40 lakh loan at 8.5%: prepaying saves ₹10.5 lakh of interest; investing
   wins only above 9.41% a year after tax.
7. **Ask FinPulse**: "Am I on track for my goals?" (answers with probabilities), "Find me a better
   plan" (runs the Strategist in the chat), "Rent or buy: ₹75 lakh flat, rent ₹25,000".
8. **Documents**: upload `salary-slip-demo.txt` — the ₹1,85,000 net pay mismatch and the hidden
   "ignore previous instructions" line are both flagged.
9. **Activity log**: every goal, agent step, plan change, check-in and approval, as recorded.
10. Restart the server: the plan, analyses and check-ins are still there.

Probabilities are reproducible for a given plan (seeded), but each load of the demo creates new
goal ids, which seed each goal's price stream — so figures can differ by a point or two between
demo loads.

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
    plan.ts         the multi-goal plan: month-by-month projection across every goal,
                    priority funding, inflation, returns, goal loans; plan impact of a new goal
    decisions.ts    rent vs buy and prepay vs invest simulations with break-even solving
    montecarlo.ts   the probabilistic model: seeded random futures, odds per goal, outcome
                    range, risk drivers, room to spend
    optimize.ts     the plan search: levers, disruption costs, racing, fresh-futures check
    parse-inr.ts    "₹75 lakh", "1.2 crore", "15,00,000"
  agents/
    orchestrator.ts the workflow: plan → collect → research → analyse → stress → plan impact
                    → verify → synthesise → act → request approval → audit
    plan-tools.ts   project_goal_plan, check_plan_impact, simulate_plan, rank_risks,
                    find_spending_room, search_better_plan, compare_rent_vs_buy,
                    compare_prepay_vs_invest
    strategist.ts   the Strategist agent: measure → explain → search → check → propose;
                    applying a proposal (decideStrategy) is the person's action
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
  plan-model.ts   profile + goals + check-ins → the engine's inputs; the monthly pulse
                  (shared by the server and the plan page, so both compute the same thing)
  store.ts        per-session store (memory + one JSON file per session); approval state machine
src/app/api/personal/*   route handlers (validated, same-origin only, rate-limited)
src/app/(personal)/*     the ten sections
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
- Storage: each browser session (httpOnly cookie, 180 days) is kept in memory and written to
  its own JSON file under `FINPULSE_DATA_DIR` (default `.finpulse-data`, git-ignored; directory
  0700, files 0600), debounced and atomic (temp file + rename). Visits that change nothing write
  nothing. `FINPULSE_STORAGE=memory` keeps everything in memory only (tests use this).

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
- `finance/plan.test.ts` — the plan projection on hand-checkable cases (no growth or returns):
  level contributions, delays and their length, inflation and one-time costs, earmarking savings
  by priority, the reserve before goals, goal loans starting EMIs, deficits and shortfalls, plan
  impact of a new goal.
- `finance/decisions.test.ts` — prepay vs invest (0% return → prepay; break-even ≈ loan rate when
  untaxed; tax raises it) and rent vs buy (extremes, break-even appreciation levels the two).
- `plan-model.test.ts` — the monthly pulse (gaps, streaks, trend, "if this continues").
- `finance/montecarlo.test.ts` — with every risk off, random futures reproduce the projection;
  seeds reproduce; each goal's random stream is independent of the others; more risk never
  helps; bigger goals are less likely; risk ranking and room to spend.
- `finance/optimize.test.ts` — the search improves odds (confirmed on fresh futures), never
  touches locked goals, leaves a working plan alone, and applies what it reports.
- `agents/strategist.test.ts` — the five recorded steps and tool calls, and that a proposal is
  applied only once and only to the plan it was made for.

## Limits and honest caveats

- The AI paths were tested with a scripted model, not against the live API (no key in the build
  environment). Run once with a key before demoing live research.
- Thresholds (35%/50% debt-to-income, 3/6 months of cover, 10% buffer) are heuristics, shown with
  their reasoning; they are not lender criteria.
- A rate rise is modelled by recalculating the EMI for the same tenure; many Indian lenders extend
  the tenure instead.
- The plan's growth, inflation and return figures (6% income growth, 6% inflation, 6.5% / 10%
  returns, 10% education inflation, 7% stamp duty and registration on homes) are round,
  editable assumptions — not forecasts or product rates. The plan does not model taxes on
  returns, salary jumps or one-off windfalls; check-ins are how it stays honest.
- The risk model's parameters (return volatility, job-loss and emergency chances, their sizes) are
  round, disclosed assumptions, not calibrated forecasts; the probabilities are "under these
  assumptions". Returns are drawn independently each year (no market regimes); job loss does not
  change pay afterwards; taxes on returns are not modelled.
- The Strategist's search is greedy (up to three changes) over a fixed set of levers; it can miss
  combinations that only help together. Every proposal is checked on fresh futures before it is
  shown.
- Rent vs buy ignores home-loan tax benefits and selling costs; prepay vs invest ignores lost tax
  deductions and prepayment charges. Both say so on the page.
- File storage assumes a single server process. For several instances, replace `store.ts` with a
  database-backed store.
- FinPulse is decision support, not financial advice, and cannot guarantee loan approval.
