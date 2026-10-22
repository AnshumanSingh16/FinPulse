# FinPilot — your cash autopilot

**Never be surprised by cash again.** FinPilot looks 90 days ahead at your bank balance, tells you in plain words when money gets tight, and a crew of AI agents works out how to fix it. You approve with one tap. It works for any small business: a shop, a factory, an agency, a café, a clinic, an online seller.

**Today screen** — built for owners, not accountants:
- *"Money runs out in 32 days"*, *"Money gets tight in 62 days"* or *"You're all set"*.
- **Safe to spend today:** what you could spend now without dipping below your cushion on any day ahead.
- **Chance you stay safe:** the share of 1,000 simulated futures where you stay above your cushion. The futures are built from how each of your customers has actually paid in the past.
- A 13-week colour strip (comfortable / below cushion / out of money). The numbers and the chart sit behind **See the numbers**.

**Fix it for me** — the agent crew, live, one after another:

| Agent | What it does |
|---|---|
| Forecaster | Reads every upcoming bill and invoice plus your usual sales and costs, and finds the first bad day. It doesn't count customers who are already badly late. |
| Risk analyst | Plays out 1,000 futures: payment dates are drawn from each customer's own history, overdue money may or may not arrive, and sales and costs vary as they have. |
| Collections | Overdue money, with WhatsApp reminders ready. |
| Payables | Supplier bills that could move a few weeks. |
| Spending | Owner drawings and marketing that could wait. |
| Tax | Sets the next GST payment aside. |
| Planner | Scores **every combination** of moves exactly, stress-tests the best ones in the same futures, and picks the plan with the best odds. Among plans that are about as safe, it picks the one that asks least of you. |
| Financing | If the plan still leaves real risk, it sizes a standby overdraft from the bad futures (1 in 10) and prepares the letter to your bank. |
| Deals | Offers a reliable customer a small discount to pay an invoice early, but only when the tightest day falls before its due date. |
| Auditor | Re-runs the full forecast with the chosen plan and confirms it matches the planner. |
| Strategist (AI) | With an AI key, suggests ideas beyond these moves and **tests each one with `test_move`** before mentioning it. |

Then FinPilot sums it up in plain words. With an AI key, the AI writes this summary from the tools' results, and every figure is checked; if one doesn't match, you get the built-in summary instead. You can approve the whole plan with one tap.

**Plan B and autonomy over time.** Every move that depends on someone else gets a checkpoint and a Plan B, for example: *"If Kaveri hasn't paid by 10 Oct → …"*. After you approve, the agents keep watching:
- They notice a missed checkpoint and prepare a firmer reminder.
- They learn from how each customer responds to reminders, and the odds update.
- They re-plan with today's books and ask you to approve Plan B.
- If you approved a standby overdraft, they draw on it on the day cash would dip below your cushion.

Everything is logged in **What your agents did**. On the demos, **Watch your agents over time** lives the next 1–4 weeks with simulated payments, so you can see all of this happen.

**Track record** (`/proof/`): for every past week, FinPilot rewinds the books, forecasts 30 days exactly as it does today, and compares with what really happened. It reports:
- error against a "balance stays flat" guess
- real dips flagged in advance
- the odds score (Brier)
- how often reality fell inside the simulated range

See **[PITCH.md](PITCH.md)** for the numbers.

**Can I afford it?** Type an amount and pick a date. The answer is **Yes**, **Yes, if you approve the plan**, **Risky** or **Not now**, with your odds and the earliest safe day to pay without changing anything.

**Ask → investigate → show the evidence → simulate → recommend → track.** The signature loop:
- **Proactive alerts.** Before you ask, the desk lists what it noticed — bills next week that may exceed the cash you'll have, overdue money, sales down, a cost that jumped — each with its evidence and a next step.
- **"Why are my sales less this month?"** is investigated, not just totalled. The change is split by customer (stopped, paid less, paid more, new) and counter/app takings — the parts add up exactly — plus fewer payments vs smaller payments. Invoices that are due but unpaid are flagged as *late money, not lost business*. It says what it can't tell (which products, prices, seasonality without last year's data) and what to upload to check.
- **Show me why** sits beside every recommendation, alert and answer. It opens the proof in four parts: 1 the records used, 2 the calculation line by line, 3 what was assumed, 4 what couldn't be verified.
- **Cash in 2 weeks** is a scenario you can change: untick a collection you doubt, tick an overdue customer you trust, hold a bill, set sales to 80%, add a purchase. The breakdown always adds up to the end balance.
- **What you approved — and what happened**: each approved move shows whether it was done and what followed — paid, part-paid, missed the checkpoint, or spend that slipped after a pause. On the agency demo, after approving and fast-forwarding two weeks: *"Kaveri Hospitals paid ₹5,25,600 on 5 Oct — 5 days after you approved."*
- **Cash is not profit.** Sales received minus running costs paid is labelled *net operating cash difference*, with what it leaves out (unpaid invoices, unpaid bills, other months' costs, depreciation).

**What changed:** when a customer pays or the books change, the agents compare against the last picture: *"Kaveri Hospitals paid ₹5.26 L"*, *"You no longer run out of cash"*.

Also:
- **Timeline:** week by week, every bill and invoice.
- **Ask:** chat in English, Hindi or Hinglish.
- **People:** who owes you, with WhatsApp reminders.

Every figure comes from tested Python calculations over your own records. FinPilot **prepares, you approve**: it never pays, sends or files anything itself. It works offline with built-in answers; add a free Gemini key (or a Claude key) to let it understand anything.

Why it looks like this: see **[VISION.md](VISION.md)**.

> Decision support, not financial advice.

---

## Run it

You need Python 3.11 or newer. Node is **not** needed, because the web app ships pre-built.

```bash
git clone https://github.com/AnshumanSingh16/finpulse.git
cd finpulse
python -m venv .venv
```

Activate the environment:

- Windows (cmd): `.venv\Scripts\activate.bat`
- Windows (PowerShell): `.venv\Scripts\Activate.ps1`
- macOS or Linux: `source .venv/bin/activate`

Then install and start:

```bash
pip install -r requirements.txt
python run.py
```

Your browser opens at http://localhost:8000 on a **demo shop** with made-up numbers. To use your own data, open **Your data** and upload a bank statement (Excel or CSV).

**Using it on your phone.** Run `python run.py --host 0.0.0.0` and open `http://<your-computer's-IP>:8000` on the phone while it's on the same Wi-Fi.

**If something goes wrong:**
- **"Python was not found" on Windows:** install Python from python.org and tick **"Add python.exe to PATH"**.
- **Port 8000 is busy:** use `python run.py --port 8010`.

### Turn on the AI agent (optional)

Without a key, Ask answers with **built-in rules**: they work offline, cover the everyday questions (today's to-dos, khata, profit, costs, cash ahead, health score, the week, GST, what-ifs, adding entries, reminders, goals, budgets — including two-part questions), and use the same tools and figure-checking as the AI. Nothing leaves your computer.

For questions in your own words, turn on the AI agent with **Google Gemini (free key)** or **Anthropic Claude** — **in the app:** *Ask → Set up AI* (or *Your data → AI agent*):

1. Pick **Google Gemini (free)** and get a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (sign in with Google → *Create API key*; it starts with `AIza` or `AQ.`). Or pick **Anthropic Claude** and use a key from the Anthropic Console.
2. Paste the key, read what is sent, tick the box. FinPilot checks the key by listing the models it can use (nothing about your business is sent), picks a Gemini *flash* model, and saves the key in the local `.env` file — never in code, never committed. You can pause the AI or remove the key there too.

> **Gemini free tier and privacy:** Google's terms let it use what you send on the free tier to improve its products, and people may review it. Fine for the demo shop; for your real books consider a paid (billing-enabled) key. The free tier also has per-minute limits — if one is hit, Ask answers with built-in rules and says so.

Or set it by hand in `.env` and restart:

```bash
GEMINI_API_KEY=AIza...          # or ANTHROPIC_API_KEY=sk-ant-...
FINPILOT_PROVIDER=gemini        # optional when only one key is set
```

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | (unset) | Turns on the AI agent with Google Gemini (`GOOGLE_API_KEY` also works). |
| `FINPILOT_GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model (set automatically to one your key can use). |
| `ANTHROPIC_API_KEY` | (unset) | Turns on the AI agent with Anthropic Claude. |
| `FINPILOT_MODEL` | `claude-opus-5-5` | Claude model used by the agent. |
| `FINPILOT_PROVIDER` | (auto) | `gemini` or `anthropic` when both keys are set. |
| `FINPILOT_MAX_STEPS` | `8` | Maximum rounds of tool calls per question. |
| `FINPILOT_DB` | `finpilot.db` | Local SQLite file holding your uploads and to-dos. |
| `FINPILOT_AI` | (unset) | Set to `off` to force built-in answers (the in-app *Pause* sets this). |

**What is sent to the AI.** In AI mode, your question and the outputs of the tools the agent runs (totals, dates, customer/supplier names, at most 25 record ids per result) are sent to the provider you chose (Google or Anthropic) so it can write the answer. Your files and full records are never sent. With Claude, if the main model is unavailable or declines, a server-side fallback model may answer; if the API can't be reached at all, the app answers with built-in rules and says why. Ask always shows which mode is on.

---

## A 3-minute tour (three demo businesses)

The home screen is a **CFO desk**:
- **On the left:** a conversation with your CFO. It opens with a three-line briefing and one clear next step.
- **On the right:** the **cockpit**. It shows safe to spend today, days of runway, the 90-day cash line, the chance you stay safe, and what the agents are watching. On a phone it folds into a strip at the top.

1. You're in **Pixel Pundit Studio**, a design agency. The CFO says *"You'll run out of money in 32 days — on 1 Nov"* and that it has a fix.
2. Click **Show me the fix**. The agent crew works live, then hands you **The fix**: numbered steps, the odds going from 0% to 90%, and a safety-net checkbox for the standby overdraft.
3. Click **Approve the fix**. The cockpit now shows what the agents are watching.
4. Click **Fast-forward 2 weeks**, then choose *"Kaveri Hospitals never pays"*. You'll see the missed checkpoint, the learning (60% → 48%) and the re-plan. Click **Approve Plan B**.
5. Ask **Why?** to see the bills behind the dip, the chart and how it's worked out. Ask **Can I afford something?** for a yes, yes-if, risky or not-now verdict, and **How sure are you?** for the track record.
6. Type anything, in English, Hindi or Hinglish. The tool-using agent answers, checks every figure, and can draft entries and reminders for you to confirm.
7. The header gives you **Timeline**, **People**, **Track record**, the business switcher (the café and the masala maker are other demos), हिं, and **Settings**.

## Your own data

Upload CSV or Excel (`.xlsx`) files on the **Your data** page. Columns are matched automatically where possible and can be changed by hand.

| Table | Needed for | Required columns | Optional |
|---|---|---|---|
| **Transactions** (bank ledger) | Everything | date, amount, and one of: a direction column, signed amounts, or separate debit/credit columns | description, counterparty, category, payment mode, reference, currency |
| **Invoices & bills** | Receivables, payables, forecasts | kind (receivable/payable), amount, due date, status (paid/pending) | id, counterparty, description, category, issue date, paid date |
| **Bank balances** | Cash position, forecasts, affordability | date, balance | account |

The loader handles:

- **Amounts:** ₹, Rs and INR prefixes, `1,20,000`-style grouping, `(5,000)` and `5,000-` negatives, Dr/Cr suffixes, and `lakh`/`crore`/`k`.
- **Dates:** day-first dates (`05/04/2026` is 5 April), ISO dates and Excel serial dates.
- **Bad rows:** missing descriptions and categories are filled in, and rows with an unreadable date or amount are reported, not guessed.
- **Currencies:** rows in a currency other than INR are rejected.
- **Duplicates:** possible duplicates are flagged and kept unless you choose to drop exact repeats.

You can enter a bank balance by hand if you don't have a statement file.

**If data is missing, FinPilot says so rather than guessing.**

- Without a dated bank balance, cash is shown as *unknown*. It is never derived from revenue minus expenses.
- Without invoices and bills, forecasts are labelled as incomplete.
- Unrecognised categories are treated as operating costs and listed as a limitation.

---

## Architecture

```
run.py                      Starts the local server and opens the browser
finpilot/
  config.py                 Settings from environment / .env (no secrets in code)
  data/                     Canonical tables, CSV/XLSX loader + validation, demo generators (manufacturer, agency, café), SQLite store
  engine/                   Pure Python + pandas. ALL financial calculations live here (tested)
    summary.py  expenses.py  cash.py  forecast.py  decision.py  alerts.py
    autopilot.py            The cash autopilot: candidate moves, exhaustive plan search, financing backup, auditor, afford, weekly view
    risk.py                 1,000 simulated futures from each customer's payment history; learned reminder odds (numpy)
    live.py                 Fast-forward for demos: lives the next days with simulated payments
    backtest.py             Track record: rewinds the books week by week and scores forecasts and odds
  agent/                    tools.py (approved tools + validation), orchestrator.py (agent loop),
                            verify.py (independent checks), offline.py (built-in answers)
  api/
    server.py               FastAPI: JSON API under /api, and serves the built web app
    views.py                Plain-language views (status, attention items, reminders…) over the engine
    dataset.py              Demo vs. your uploaded data
    crew.py                 The agent crew's findings in English/Hindi, and the "what changed" feed
    monitor.py              Checkpoints, Plan B, learning and the agents' activity log
  web/                      The built web app (generated — do not edit)
web/                        Next.js + Tailwind source for the web app (Cash, Timeline, Ask, People, Settings, Your data, Reports)
tests/                      pytest: engine, loader, store, agent, API
data/demo/                  The fixed synthetic dataset (also usable as sample uploads)
```

**Changing the web app.** Install Node 20 or newer, then:

```bash
cd web
npm install
NEXT_PUBLIC_API=http://localhost:8000 npm run dev    # live reload on :3000 (run python run.py alongside)
npm run build                                       # rebuilds finpilot/web for python run.py
```

### How the agent works

1. **Plan and call tools.** The model gets the question, a description of the available data and the rules. Before each round it writes one short line of what it will check — shown live in Ask, with each tool step, over a server-sent-event stream (`POST /api/ask/stream`). It chooses from 33 approved tools:
   - cash autopilot: `get_cash_autopilot` (the 90-day look-ahead, safety level, odds from 1,000 simulated futures, the planner's search, the backup and the audit) `plan_purchase` (can I pay this on that date: verdict, odds with and without the agents' moves, earliest safe day), `test_move` (test any idea given as dated cash flows) and `get_track_record` (how accurate the forecast and odds would have been on this business's past). The agent is told to start here for anything about running short.
   - money: `get_financial_summary`, `investigate_sales_change` (why sales went up or down, customer by customer, with late money told apart from lost business), `analyze_expense_changes`, `find_unusual_transactions`, `get_cash_position`, `forecast_cash_flow`
   - khata: `get_receivables_and_payables`, `get_upcoming_payments`, `get_customers_and_suppliers`, `get_person_details`
   - insight: `get_health_score`, `get_weekly_story`, `get_budgets_and_goals`, `get_tax_calendar_and_gst`
   - decisions: `simulate_purchase`, `run_what_if` (price, discount, hire, loan)
   - records & actions: `get_supporting_records`, `get_review_queue`, `propose_action`, and the **draft tools** `draft_entry`, `draft_reminder`, `draft_promise`, `draft_recategorise`, `draft_goal`, `draft_budget`
   - working memory: `update_plan` (the live checklist the owner sees), `remember`, `recall_memory`, `forget` (facts and preferences the owner states — shown in the prompt as the owner's words, never as financial data)

   For a goal or the daily check-up the agent is told to plan first (`update_plan`), mark steps done as it goes, and finish by preparing actions rather than stopping at advice. The **daily check-up** (`POST /api/agent/checkup/stream`) is started by the app itself once a day per book; its briefing and cards are stored, and drafts from an older check-up expire when a new one runs. All drafted cards are kept in the local database (`agent_actions`) until the owner confirms, cancels or they expire; **Approve all** confirms every card except WhatsApp reminders, which the owner opens one by one.

   It can call several tools in one round and keep going across rounds. A hard limit of `FINPILOT_MAX_STEPS` rounds applies.
2. **Validate arguments.** Every argument is checked in Python before a tool runs: types, ranges, real dates, no unknown fields, and no "as of" dates in the future. Invalid calls go back to the model as errors. A loan simulation with no rate or tenure returns `needs_input`, and the agent asks the user.
3. **Re-check every tool result independently.** For example:
   - revenue and cash are re-summed from the raw rows
   - the forecast checkpoints are checked as start + in − out
   - the EMI is recomputed from the formula

   A failed check is shown to the user and the model is told about it.
4. **Verify the answer.** Every ₹ amount, percentage, ISO date and record id in the final answer must match a tool output or the user's own message. Lakh and crore rounding is allowed. If anything doesn't match, the model gets one repair turn. Anything still unmatched is shown as a warning, so the answer is never presented as verified.
5. **Show the evidence.** The UI shows the tool timeline, the check results and an evidence panel per tool with the supporting records.
6. **Draft, never act.** Draft tools validate the request (an entry is dry-run through the same code that saves it, so the card shows exactly which invoices a payment would clear) and return a card with **Confirm / Not now**. Only the owner's tap — handled by the server, not the model — saves the entry, goal or budget, or opens WhatsApp with the reminder for the owner to send. Confirmed actions are passed back to the agent as a note on the next question. `propose_action` puts anything outside the app (a payment, a filing) on the to-do list; nothing executes it.

The rule-based mode uses the same tools, validation and verification, with a small planner that picks up to three tools per question (or one action/simulation). If the API call fails, the app falls back to rule-based mode and says why in plain words.

### Financial rules the engine enforces

- **Revenue is cash received from sales.** Invoices are tracked separately as receivables, so a paid invoice is never counted twice.
- **Profit is an estimate.** Estimated operating profit is revenue minus recorded operating costs, and it is always labelled as an estimate: it excludes depreciation, accruals and unpaid bills.
- **Some flows are shown but are not operating costs:** asset purchases, loans received and repaid, owner drawings, and GST/TDS remitted.
- **Cash comes only from a dated balance** plus later transactions, and it is reconciled against any later statement balances.
- **Obligations are split** into paid, pending (not yet due) and overdue, with ageing.
- **Forecasts state their assumptions:**
  - Overdue receivables are excluded by default.
  - The optional "typical flows" are an average of recent full months that leaves out one-offs, asset purchases and loans. They start after each category's last scheduled item, so nothing is counted twice.
  - Forecasts make no claim of predictive accuracy.
- **Purchase scenarios show their settings.** The base, optimistic and downside settings are listed, and the verdict is judged on the downside case against a cash buffer. The default buffer is one month of typical operating costs.

---

## Tests

```bash
pytest            # 337 tests, about three minutes
```

The tests cover:

- **Plan B, autonomy and proof:**
  - Plan B and its checkpoints
  - fast-forward with a missed checkpoint: learning 60% → 48%, Plan B, the overdraft drawn only when needed
  - a good-news run: learning 60% → 68%
  - fast-forwarded books stay consistent
  - the Deals agent helps only when the tightest day is before the due date
  - `test_move`
  - the AI Strategist tests ideas before suggesting them (scripted model)
  - track record numbers, and rewinding that hides the future
- **The agent crew and risk engine:**
  - the simulation exactly reproduces the forecast when nothing varies
  - payment dates come from each customer's own history
  - reminders raise the odds, and runs are repeatable
  - the auditor's rerun matches the planner for every demo
  - the planner picks the easiest plan that reaches the target
  - the financing backup appears only when risk remains, with its interest cost
  - afford verdicts, and an earliest safe day checked by real forecasts
  - the crew stream in order and in Hindi
  - an AI brief accepted only when its figures check out (scripted model)
  - "what changed" after a customer pays
- **The cash autopilot:**
  - the three demo stories
  - late customers not counted
  - each move's effect equal to a fresh forecast run
  - a moved bill shifting only that payment
  - weekly totals adding up
  - approve, undo, dismiss and approve-plan, plus "supplier agreed" changing the bill's due date
  - the safety level setting
  - books kept apart per demo
  - the offline "will I run short?" answer
- **Financial calculations:** checked against hand-worked examples on a small fixture, plus independent re-sums of the demo data.
- **Expense comparisons and unusual-transaction detection:** including the anomalies planted in the demo data.
- **Duplicate detection:** in the ledger and in uploaded files.
- **Cash position:** with and without a dated balance, including reconciliation gaps.
- **Cash forecasts:** the 30/60/90-day checkpoints, delays, overdue handling and the run-rate excluding one-offs.
- **Purchase simulations:** cash and loan purchases, EMI, an unaffordable purchase, invalid inputs, and a purchase made today.
- **Missing data:** no balance, no invoices, an empty period, and a loan with no terms.
- **Upload parsing:** Indian amounts, dates, column mapping, debit/credit columns, currency checks and an XLSX round trip.
- **The agent:**
  - argument validation
  - catching tampered tool results
  - catching invented figures, dates and ids
  - the repair turn, the step limit, refusal and truncation handling, and the API-failure fallback

- **The proactive agent:** the daily check-up (plan ticks to done, actions saved, runs once a day, older drafts expire), approve-all across a restart, memory that changes what is drafted, promises and category fixes, and an AI check-up with a scripted model.
- **The agentic layer:** the khata/health/GST/what-if tools against independent sums, drafts that never save, confirm/cancel/expiry of action cards, the rule-based planner on everyday English/Hinglish/Hindi questions, the live-progress stream, and in-app key setup (consent required, key never echoed back).

  These use a scripted fake model, so no network or API key is needed. Gemini runs through the same loop with a scripted fake of its REST API (tool declarations, thought-signature round trip, repair turn, step limit, key setup). The live AI agent (either provider) has not been tested against the real APIs in this repository's test suite.

To regenerate the demo dataset (deterministic, so this should produce no diff):

```bash
python -c "from finpilot.data.demo import write_demo_files; write_demo_files()"
```

## Limits of this MVP

- **Single user, local data.** It is not a multi-tenant service.
- **One currency.** Only INR is accepted.
- **Cash-basis view only.** There is no accrual accounting, depreciation schedule or GST computation.
- **Forecasts and scenarios are arithmetic on stated assumptions**, not statistical predictions. Their accuracy has not been measured.
- **No external actions.** There are no payment, messaging or filing integrations, by design.
