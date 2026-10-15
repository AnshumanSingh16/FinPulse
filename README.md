# FinPilot AI

A money copilot for small business owners in India. In plain words it tells you:

- **How you're doing.** How much cash you have, how long it lasts, and whether it's about to get tight.
- **What needs doing.** Customers to chase (with a ready-to-send WhatsApp reminder), late bills, and possible double payments.
- **Answers to your questions.** Ask about your sales, costs or cash and get answers checked against your records.
- **Whether you can afford something.** Three quick questions, then "Yes", "Yes — but it's tight" or "Not right now", with sliders to try other numbers.

All financial figures are calculated by tested Python code, never by the AI. Every number has a **"How do we know?"** link showing the method, the assumptions and the exact records behind it.

> Decision support, not financial advice. FinPilot never makes payments, sends messages or files returns. Suggested actions go to your to-do list, and reminders are drafts you send yourself.

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

### Turn on the AI (optional)

Without an API key, Ask uses built-in answers and nothing leaves your computer. To turn on the AI agent:

```bash
cp .env.example .env      # Windows: copy .env.example .env
# then set ANTHROPIC_API_KEY=sk-ant-... in .env and restart
```

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | (unset) | Turns on the AI agent. Without it, built-in answers are used. |
| `FINPILOT_MODEL` | `claude-opus-5-5` | Model used by the agent. |
| `FINPILOT_MAX_STEPS` | `8` | Maximum rounds of tool calls per question. |
| `FINPILOT_DB` | `finpilot.db` | Local SQLite file holding your uploads and to-dos. |
| `FINPILOT_AI` | (unset) | Set to `off` to force built-in answers. |

**What is sent to the AI.** In AI mode, your question and the relevant tool outputs are sent to Anthropic's API so it can write the answer. Tool outputs are totals plus at most 25 record ids per result. Your files are never sent. If the main model is unavailable or declines, a server-side fallback model may answer. The Ask page tells you which mode is on.

---

## A 3-minute tour (demo shop)

1. **Home.** It opens with "Your business is in good shape — ₹14.85 L in the bank, about 2.2 months of running costs", plus the cash chart (actual and expected).
   - Under *Needs your attention*, tap **Draft a reminder** on Metro Foods (₹2.94 L overdue) to get an editable WhatsApp message.
   - Tap **Review payments** on the possible double payment to see both transactions.
   - September shows a loss. Tap **Ask FinPilot why**.
2. **Ask.** Try *"Who owes me money?"* or *"Can I buy a ₹8 lakh van on a loan?"*. For the van, it asks for the loan terms instead of guessing them. Every answer shows a badge confirming its figures were checked, and *How I worked this out* lists the steps.
3. **Plan → Can I afford it?** Pick *Packing machine · ₹12 L*, then choose **Loan**, 11% and 3 years, and enter ₹45,000 a month in savings. The verdict is "Yes — but it's tight if business slows". Switch between Tough months, Most likely and Goes well, and drag the price slider.
4. **Plan → Cash ahead.** Slide "Customers pay late" to 30 days and watch the 30/60/90-day balances change.
5. **Your data.** Upload `data/demo/ledger.csv`, or any bank statement. Check the matched columns, import, then add today's balance.

---

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
web/                        Next.js + Tailwind source for the web app (Home, Money, Ask, Plan, Your data)
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

1. **Plan and call tools.** The model gets the question, a description of the available data and the rules. It chooses from ten approved tools:
   - `get_financial_summary`, `analyze_expense_changes`, `find_unusual_transactions`
   - `get_cash_position`, `get_receivables_and_payables`, `get_upcoming_payments`
   - `forecast_cash_flow`, `simulate_purchase`
   - `get_supporting_records`, `propose_action`

   It can call several tools in one round and keep going across rounds. A hard limit of `FINPILOT_MAX_STEPS` rounds applies.
2. **Validate arguments.** Every argument is checked in Python before a tool runs: types, ranges, real dates, no unknown fields, and no "as of" dates in the future. Invalid calls go back to the model as errors. A loan simulation with no rate or tenure returns `needs_input`, and the agent asks the user.
3. **Re-check every tool result independently.** For example:
   - revenue and cash are re-summed from the raw rows
   - the forecast checkpoints are checked as start + in − out
   - the EMI is recomputed from the formula

   A failed check is shown to the user and the model is told about it.
4. **Verify the answer.** Every ₹ amount, percentage, ISO date and record id in the final answer must match a tool output or the user's own message. Lakh and crore rounding is allowed. If anything doesn't match, the model gets one repair turn. Anything still unmatched is shown as a warning, so the answer is never presented as verified.
5. **Show the evidence.** The UI shows the tool timeline, the check results and an evidence panel per tool with the supporting records.
6. **Queue actions, never execute them.** `propose_action` only adds an item to the approval queue. Approving it records the decision; no integration executes anything.

The rule-based mode uses the same tools, validation and verification. If the API call fails, the app falls back to rule-based mode and says so.

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
pytest            # 139 tests, about 25 s
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

  These use a scripted fake model, so no network or API key is needed.

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
