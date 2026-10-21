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

## The 3-minute demo (laptop)

The home screen is a **CFO desk**. On the left is one conversation with your CFO. On the right is a dark **cockpit** with the live numbers: safe to spend today, days of runway, the 90-day cash line, the chance you stay safe, and what the agents are watching.

1. Open **Pixel Pundit Studio**. The CFO opens with one sentence: *"You'll run out of money in 32 days — on 1 Nov."* It has found a fix that takes the odds from 0% to 41%, and to 90% with a safety net.
2. Click **Show me the fix**. The agents work live: Forecaster, Risk analyst (1,000 futures), Collections, Payables, Spending, Tax, Deals, Planner (scores every combination), Financing and Auditor. Their findings collapse into **The fix**: numbered steps, 0% → 90%, and a safety-net checkbox.
3. Click **Approve the fix**. The cockpit flips to *"Watching: Kaveri by 10 Oct"*. The bank letter is copied, and the WhatsApp reminder is ready for you to send.
4. Click **Fast-forward 2 weeks**, then *"Kaveri Hospitals never pays"*. Days roll by. On 10 Oct the Collections agent flags the missed checkpoint, the Risk analyst learns (60% → 48%), and the Planner re-plans with today's books.
5. Click **Approve Plan B**. The odds go back to 90%.
6. Ask **How sure are you?** The CFO shows its track record on the business's own past weeks.
7. Type any question, for example *"Who pays me late?"*. The tool-using agent answers, with every figure checked.
8. Bonus:
   - Switch to हिं: the whole desk speaks Hindi.
   - Add a free Gemini key: the AI Strategist proposes and tests its own ideas.

## How it's built

- Python and FastAPI do every calculation, deterministically and under test (313 tests).
- An LLM (Claude or Gemini, optional) plans, calls 32 approved tools, and writes in plain words. A verifier checks every number it writes.
- Next.js front end, works on phones, English and Hindi.
- Runs offline: with no AI key, the crew, planner, monitor and track record all still work.

## Questions judges ask (also in the app: **Q&A** in the header)

| Question | Answer, and where to see it |
|---|---|
| Isn't this just a chatbot? | 11 agents, each with one job, that plan, act within limits, keep watching after approval, learn and check each other. The chat is just the interface. *Desk → Show me the fix* |
| Why did it pick this plan? | **Why this plan?** on the fix lists every alternative the planner compared: moves, effort, tightest day and odds, with the chosen one highlighted. |
| What about things the data can't know (Diwali, a big order, a purchase)? | **Tell me what's coming** adds the event to every forecast, plan and affordability check. It is shown in the cockpit and logged. |
| What if the customer still doesn't pay? | Checkpoints and Plan B. Use *Fast-forward 2 weeks → "never pays"* to see it. |
| How do we know it's accurate? | **Track record**: weekly backtests on the business's own past, with weaknesses shown. |
| Can the AI invent numbers? | Every figure in an AI answer must match a tool result, or the answer is corrected or flagged. The Strategist's ideas must pass `test_move` before they're mentioned. |
| Will it move money or message customers by itself? | Never. It drafts and you send. Every agent action and owner decision is in the **audit log** (Settings → Download, CSV). |
| Does it actually get money in faster? | Reminders include the business's **UPI pay link** (`upi://pay…`), so the customer can pay with one tap. |
| Can a shopkeeper who doesn't type use it? | Yes: Hindi throughout, **voice input**, a **read-aloud** briefing, and WhatsApp-ready messages. |
| What's the measurable impact? | The cockpit shows **Your agents' impact**: what the approved plan adds to the tightest day, and the change in odds. |
| Where does the data live / DPDP? | Locally. AI is off until the owner consents, and then only the figures for that answer are sent. Deletion is one tap. This is a design choice, not a legal certification. |
| Market size? | About 6.3 crore MSMEs (Ministry of MSME Annual Report 2020–21). Delayed payments to MSMEs were estimated at about ₹10.7 lakh crore (GAME & FISME, 2022). |
| Business model? | Proposed: free for one business, paid for accountants and multi-branch owners, and consented lender referrals for the backup (overdraft, invoice discounting via TReDS). Not live. |
| Competition? | Khatabook, Vyapar, Tally and Zoho record the past. Float and Fathom forecast for accountants. FinPilot looks ahead and acts, for the owner, in Hindi. |
| Limits? | Simulated demo histories; no pilot yet; no live bank feed or WhatsApp API; the simulated range is too narrow on some businesses; AI paths tested only with a scripted model. |
