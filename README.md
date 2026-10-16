# Munshi — the AI bookkeeper that lives in a chat

*(code name FinPilot)*

Munshi is for small shop and business owners in India. Instead of forms and dashboards there is **one chat**, like WhatsApp:

- **Tell Munshi what happened** — *“Ravi ko 2500 udhaar”*, *“Metro ne 50k diye”*, *“bijli bill 3200”* — typed or spoken, in Hindi, English or Hinglish. Munshi prepares the entry; one tap saves it.
- **The chat is the khata.** Every entry lands in the thread as a line you can undo — scroll up and you're reading your account book.
- **Munshi speaks first.** Each morning it goes through your books by itself and posts what needs you today, with the reminders and fixes already prepared.
- **Lena / Dena, always on top:** bank balance, money to collect, money to pay.
- **Ask anything:** *“kaun der se deta hai?”*, *“is mahine kaisa raha?”*, *“help me collect my money”*, *“₹12 lakh ki machine le sakta hoon?”*
- **Khata screen:** every customer and supplier, what they owe, and a WhatsApp reminder in one tap.

Every figure comes from tested Python calculations over your own records and is checked before you see it. Munshi **prepares, you approve** — it never pays, sends or files anything itself. Works offline with built-in answers; add a free Gemini key (or a Claude key) to let it understand anything.

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

1. Pick **Google Gemini (free)** and get a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (sign in with Google → *Create API key*; it starts with `AIza`). Or pick **Anthropic Claude** and use a key from the Anthropic Console.
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

## A 3-minute tour (demo shop)

1. Open the app — Munshi is already going through the demo shop's books. Watch its plan tick off, then read the morning message: who to collect from, which bills are due, anything odd — with WhatsApp reminders ready.
2. Type *“Ravi ko 2500 udhaar”* → **Confirm**. A khata line appears in the chat and **Lena** goes up. Tap **Undo** on the line to take it back.
3. Ask *“kaun der se deta hai?”* or *“help me collect my money”*. Then tell it *“never remind Metro Foods”* and ask again — it remembers.
4. Tap **Paisa aaya** above the message box to record a payment with the form instead.
5. Open **Khata** → Metro Foods: what they owe, their history, **Remind on WhatsApp**.
6. **Settings** (⚙) → turn the AI on with a free Gemini key, switch to Hindi, use your own books, or print the monthly report for your CA.

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
  data/                     Canonical tables, CSV/XLSX loader + validation, demo generator, SQLite store
  engine/                   Pure Python + pandas. ALL financial calculations live here (tested)
    summary.py  expenses.py  cash.py  forecast.py  decision.py  alerts.py
  agent/                    tools.py (approved tools + validation), orchestrator.py (agent loop),
                            verify.py (independent checks), offline.py (built-in answers)
  api/
    server.py               FastAPI: JSON API under /api, and serves the built web app
    views.py                Plain-language views (status, attention items, reminders…) over the engine
    dataset.py              Demo vs. your uploaded data
  web/                      The built web app (generated — do not edit)
web/                        Next.js + Tailwind source for the web app (Munshi chat, Khata, Settings, Your data, Reports)
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

1. **Plan and call tools.** The model gets the question, a description of the available data and the rules. Before each round it writes one short line of what it will check — shown live in Ask, with each tool step, over a server-sent-event stream (`POST /api/ask/stream`). It chooses from 28 approved tools:
   - money: `get_financial_summary`, `analyze_expense_changes`, `find_unusual_transactions`, `get_cash_position`, `forecast_cash_flow`
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
pytest            # 265 tests, about a minute
```

The tests cover:

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
