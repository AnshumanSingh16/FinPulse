# FinPilot — your cash autopilot

**Never be surprised by cash again.**

## The problem
Most small businesses that fail are not unprofitable — they **run out of cash**. A big client pays late, salaries and rent land in the same week, a deposit or an annual renewal comes due, GST is payable on the 20th. The owner finds out when a payment bounces.

It doesn't matter whether the business is a spice factory, a design agency, a café, a clinic or an online seller: the question every owner carries is the same — *will I have enough money on the day I need it?* Accounting software answers a different question (what happened last month) and expects the owner to work out the rest.

## The product
FinPilot looks 90 days ahead, every day, and does the work an experienced finance person would.

1. **Predict.** It builds the next 90 days of the bank balance from the owner's own records:
   - invoices due
   - bills and salaries
   - rent and EMIs
   - GST
   - the typical day-to-day sales and costs of the last three months

   It does not count money from customers who are already badly late.
2. **Warn early.** One sentence at the top: *"You'll run out of cash on 1 Nov"*, *"Cash drops below your safety level on 1 Dec"*, or *"You're covered for the next 90 days."* It names the bills that cause the dip.
3. **Fix it with agents.** Small, specialised agents each prepare a move:
   - **Collections agent:** collect overdue money, with a WhatsApp reminder ready.
   - **Payables agent:** ask a supplier to move a bill, with the message ready.
   - **Spending agent:** pause owner drawings or marketing for a while.
   - **Tax agent:** set GST money aside so it isn't spent by mistake.

   Every move shows exactly how much it lifts the lowest point. That figure comes from re-running the whole forecast, not from a guess. The agents then put together the smallest plan that keeps cash above the safety level.
4. **The owner approves.** One tap approves the plan, or a single move. The chart then shows the new path, and the timeline shows each week with the approved moves included.
5. **Ask anything.** *"Can I afford a ₹12 lakh machine?"*, *"What if Kaveri never pays?"*, *"Kaun der se deta hai?"* Every answer is calculated in Python and every figure is checked against the records.

## Why it's agentic, not a dashboard
A dashboard shows a chart and leaves the thinking to the owner. In FinPilot a crew of agents does the thinking, and the owner only decides:
- **Each agent has one job:** forecaster, risk analyst, collections, payables, spending, tax, planner, financing and auditor.
- **They reason about uncertainty, not one line on a chart.** 1,000 futures are built from how each customer has actually paid. A plan that only works if a late customer pays is called out, and the Financing agent prepares a backup.
- **They search, they don't guess.** Every combination of moves is scored exactly, the best are stress-tested, and the easiest plan that is about as safe wins.
- **They check each other.** The auditor re-runs the forecast. When an AI writes the summary, every figure is verified against the tools' results.
- **They act within limits.** They prepare the WhatsApp reminders, the supplier message and the letter to the bank, but the owner sends them. Nothing moves money by itself.
- **They notice change.** When a customer pays, the picture updates: *"You no longer run out of cash."*

The language is for owners:
- *"safe to spend today"*
- *"money runs out in 32 days"*
- *"14% chance you stay safe"*
- *"Can I afford it?"*

## Any business
The engine works on money in and money out, so it is the same for every business type. Only the words change: clients, guests, patients, buyers or marketplaces. The app ships with three demos, each with a different cash problem:

| Demo | Business | Story |
|---|---|---|
| Annapurna Masala Works | Manufacturer, Pune | Healthy. One big customer is late. |
| Pixel Pundit Studio | Design agency, Bengaluru | A hospital client stopped paying, so cash runs out on 1 Nov. Collecting from them and pausing drawings fixes it. |
| Brew & Bun Café | Café, Mumbai | Diwali stock and a kitchen fit-out push cash below safety in early December. |

## Principles
1. **One promise.** Every screen serves "never be surprised by cash". Anything that doesn't is left out.
2. **Never invent a number.** All calculations are tested Python. The language model explains them but never computes them, and every figure it says is checked.
3. **Honest assumptions.** Late customers are not counted. Typical flows are labelled as typical. A move's effect is measured, not estimated. This is arithmetic, not a prediction.
4. **Prepare, never act alone.** FinPilot drafts reminders and messages; the owner sends them. It never pays, moves money or files anything.
5. **Works offline.** The built-in answers need no AI key. A Gemini or Claude key makes it understand anything.
6. **The owner's data stays on their machine**, unless they turn AI on. Even then, only the figures needed to answer are sent.

## Next
1. Bank feeds and UPI import that run by themselves, so the forecast is always fresh.
2. Alerts on WhatsApp the moment the 90-day picture changes.
3. More agents:
   - a financing agent that compares lenders (invoice discounting vs. overdraft, on cost)
   - a pricing agent
4. Multi-user (owner + accountant), with the books under the owner's control.
