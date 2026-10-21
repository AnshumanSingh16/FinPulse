# FinPilot — an agentic CFO that keeps small businesses from running out of cash

**The problem.** Most small businesses that die are not unprofitable — they run out of cash. A client pays late, salaries and rent
land together, a deposit comes due. India has 6+ crore small businesses; almost none can afford a finance person to see it coming.

**The product.** FinPilot is a crew of AI agents that does a finance manager's job every day. The owner sees four things:
- *"Money runs out in 32 days"*
- *"Safe to spend today: ₹0"*
- *"Chance you stay safe: 2%"*
- **Fix it for me**

It works for any business type: a shop, a factory, an agency, a café.

## What makes it agentic (and not a dashboard)

| Capability | What happens | Where |
|---|---|---|
| **Specialised agents** | 11 agents, each with one job: Forecaster, Risk analyst, Collections, Payables, Spending, Tax, Deals, Planner, Financing, Auditor, AI Strategist | `api/crew.py` |
| **Reasoning under uncertainty** | 1,000 simulated futures, built from *each customer's own payment history* | `engine/risk.py` |
| **Search, not guesswork** | The Planner scores **every** combination of moves exactly, stress-tests the best ones, and picks the plan with the best odds. Among plans about as safe, it picks the one that asks least of the owner. | `engine/autopilot.py` |
| **Contingency plans** | Every move that depends on someone else gets a checkpoint and a Plan B: *"If Kaveri hasn't paid by 10 Oct → collect from Zenith + ₹4.5 L standby overdraft (90%)"* | `plan_b` |
| **Autonomy over time** | After approval, the agents keep watching. They notice a missed checkpoint, prepare a firmer reminder, re-plan with today's books, draw the standby overdraft when needed, and log everything. | `api/monitor.py`, `engine/live.py` |
| **Learning** | The agents learn per customer from how each one responds to reminders, and the odds update: *"Kaveri: 60% → 48%"* | `risk.learned_reminder_p` |
| **Creativity, verified** | With AI on, the Strategist (an LLM) suggests ideas outside the standard list. It must test each one with `test_move` against the real forecast before mentioning it. | `test_move` tool |
| **Self-checking** | The Auditor re-runs the forecast on the chosen plan. Every figure the LLM writes must match a tool result, or the answer is not shown. | `agent/verify.py` |
| **Human in the loop** | Agents draft the WhatsApp reminders, supplier messages and bank letter. The owner approves. Nothing pays, sends or files by itself. | — |
| **Proof** | A **Track record**: every past week, the books are rewound and forecast, and the forecast is compared with what really happened | `engine/backtest.py`, `/proof/` |

## Track record (on the demo businesses' own past; 30-day forecasts, weekly)

| | Café | Agency | Manufacturer |
|---|---|---|---|
| Tightest-day error vs "balance stays flat" | **82% smaller** | 36% smaller | 50% smaller |
| Whole-month error vs flat | **76% smaller** | 17% smaller | 25% smaller |
| Real dips flagged in advance | **22 of 22** | 1 of 4 (the misses were ≤ ₹32k below the cushion) | no dips |
| Odds score (Brier; 0 perfect, 0.25 coin flip) | **0.06** | 0.14 | 0.00 |
| Real outcome inside the 10–90% range (aim 80%) | 94% | 38% | 35% |

Building the backtest **found four bugs in our own forecast**, now fixed:
1. Regular salaries were treated as one-off payments in young books.
2. Invoiced income was counted twice.
3. Customers' habitual lateness was ignored.
4. Monthly rent and salaries were smeared evenly across the month.

Each fix is tested. The demo histories are simulated, so the page says so. It also says plainly where the simulated range is too narrow.

## The 3-minute demo

1. Open **Pixel Pundit Studio** (an agency). The top reads *"Money runs out in 32 days"*, with a 2% chance of staying safe.
2. Tap **Fix it for me** and watch 11 agents report live. The Planner tests 8 combinations. The Financing agent sees the plan depends on a hospital client that is 61 days late, so it sizes a ₹5.5 L standby overdraft, which takes the odds to 90%. The Auditor confirms the numbers.
3. Tap **Approve the plan**. *"Your agents are watching: Kaveri should pay by 10 Oct."*
4. Under **Watch your agents over time**, pick *"The late customer never pays"* and tap **+2 weeks**. Days roll by. On 10 Oct the Collections agent flags the missed checkpoint, the Risk analyst lowers Kaveri's odds (60% → 48%), and the Planner re-plans with today's books and asks to switch to Plan B.
5. Tap **Approve Plan B**. Then try **+1 month**: on salary day the Financing agent draws on the overdraft to stay above the cushion.
6. Open **How accurate is this?** to see the Track record.
7. Bonus:
   - Switch to Hindi: the whole crew speaks Hindi.
   - Turn on a free Gemini key: the AI Strategist proposes and tests its own ideas.

## How it's built

- Python and FastAPI do every calculation, deterministically and under test (313 tests).
- An LLM (Claude or Gemini, optional) plans, calls 32 approved tools, and writes in plain words. A verifier checks every number it writes.
- Next.js front end, works on phones, English and Hindi.
- Runs offline: with no AI key, the crew, planner, monitor and track record all still work.
