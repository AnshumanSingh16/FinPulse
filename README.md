# FinPilot AI

An agentic financial copilot for small businesses in India. Upload your bank transactions, invoices and bills, then:

- **Overview**: revenue, recorded expenses, estimated operating profit, cash in bank, what customers owe you and what you owe, with charts and alerts.
- **Ask FinPilot**: ask questions in plain English. An AI agent picks from approved analysis tools, runs them, checks the results and answers with evidence.
- **Decision Lab**: simulate a purchase (cash or loan) under base, optimistic and downside scenarios, and explore 30/60/90-day cash-flow forecasts.

All financial figures are calculated by tested Python code, never by the language model. Every answer shows the tools that ran, the independent checks they passed, and the evidence behind them: method, assumptions, limitations and the supporting records.

> Decision support, not financial advice. FinPilot never makes payments, sends messages or files returns. Suggested actions go to an approval queue and nothing executes them.

---

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. The app starts with the **demo business**, so no setup or API key is needed.

### Enable the AI agent (optional)

Without an API key, Ask FinPilot runs in **rule-based mode**. It sends common questions to the same tools and answers from templates, and nothing leaves your machine. To turn on the AI agent:

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

You can also export the variable in your shell. Real environment variables override `.env`. The key is read at runtime and is never stored in code or in the database.

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | (unset) | Enables the AI agent. If unset, rule-based mode is used. |
| `FINPILOT_MODEL` | `claude-opus-5-5` | The model used by the agent. |
| `FINPILOT_MAX_STEPS` | `8` | Maximum rounds of tool calls per question. |
| `FINPILOT_DB` | `finpilot.db` | SQLite file for uploaded data, the activity log and the approval queue. |
| `FINPILOT_AI` | (unset) | Set to `off` to force rule-based mode even when a key is set. |

**What is sent to the AI.** In AI mode, your question and the tool outputs are sent to Anthropic's API so the model can write the answer. Tool outputs include totals and the specific records the tools return, capped at 25 record ids per result. Uploaded files are never sent as a whole. The Ask page shows this notice whenever AI mode is on. Requests use server-side model fallback: if the primary model is unavailable or declines, a fallback model may answer.

---

## Demo script (about 5 minutes)

The demo business is **Annapurna Masala Works (fictional)**, a spice processor in Pune. Its data covers 1 Oct 2025 to 30 Sep 2026. The data is fixed and seeded, so every run shows the same numbers. Built into it:

- raw-material costs rise in the last quarter
- an electricity bill spikes
- one logistics payment is recorded twice
- a one-off consultancy fee
- one customer's invoices go overdue
- a ₹5 lakh loan pays for a ₹4.2 lakh machine, which shows that cash is not profit

1. **Overview.** Revenue ₹91.6 lakh, estimated operating profit ₹20.6 lakh (labelled as an estimate), and cash ₹14.85 lakh, reconciled to a bank statement. The alerts show the overdue invoices, the duplicate logistics payment and the electricity spike. Open *Evidence* to see the method and the supporting transactions.
2. **Ask FinPilot.** Click the suggested questions:
   - *Why did expenses go up last month?* compares categories, names the transactions behind each change and flags unusual payments.
   - *Can we afford a ₹12 lakh packing machine on a loan at 11% for 3 years?* checks cash, upcoming bills and the purchase simulation.
   - *Can we buy a ₹8 lakh van on a loan?* asks for the interest rate and tenure instead of assuming them.

   Expand *Tool activity* to see each call, its arguments and the independent checks.
3. **Decision Lab.** Enter the interest rate and tenure. The verdict, EMI, downside low point and scenario chart update. The *Cash-flow scenarios* tab lets you delay customer payments or lower the collection rate and see the effect at 30, 60 and 90 days.
4. **Data & uploads.** Upload the files in `data/demo/` (or your own). Map the columns, review the validation report (dates, amounts, duplicates, missing values) and save. Pick *My uploaded data* in the sidebar.

---

## Your own data

Upload CSV or Excel (`.xlsx`) files on the **Data & uploads** page. Columns are matched automatically where possible and can be changed by hand.

| Table | Needed for | Required columns | Optional |
|---|---|---|---|
| **Transactions** (bank ledger) | Everything | date, amount, and one of: a direction column, signed amounts, or separate debit/credit columns | description, counterparty, category, payment mode, reference, currency |
| **Invoices & bills** | Receivables, payables, forecasts | kind (receivable/payable), amount, due date, status (paid/pending) | id, counterparty, description, category, issue date, paid date |
| **Bank balances** | Cash position, forecasts, Decision Lab | date, balance | account |

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
app.py                      Streamlit entry: navigation, sidebar, dataset choice
finpilot/
  config.py                 Settings from environment / .env (no secrets in code)
  data/
    schema.py               Canonical tables, category → class map (revenue, operating, capex, financing, …), Evidence
    loader.py               CSV/XLSX reading, column mapping, parsing, validation reports
    demo.py                 Seeded fictional business → data/demo/*.csv
    store.py                SQLite: uploaded dataset, activity log, approval queue
  engine/                   Pure Python + pandas. All financial calculations live here.
    summary.py              Revenue, recorded opex, estimated operating profit, net cash movement
    expenses.py             Period comparison, duplicates, outliers, rare large payments
    cash.py                 Cash from dated balance + later rows, reconciliation, paid/pending/overdue
    forecast.py             30/60/90-day cash forecast from scheduled items + optional run-rate
    decision.py             Purchase simulation: EMI, three scenarios, verdict, payback
    alerts.py               Overview alerts
  agent/
    tools.py                The approved tools: JSON schemas, Python argument validation, engine calls
    orchestrator.py         Agent loop, step limit, verification, repair turn, fallback to rule-based
    verify.py               Independent re-checks of tool results + figure-by-figure answer check
    offline.py              Rule-based question router (no-key mode)
  ui/                       Overview, Ask FinPilot, Decision Lab, Data pages; theme and components
tests/                      pytest suite (engine, loader, store, agent)
data/demo/                  The fixed synthetic dataset (also usable as sample uploads)
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
pytest            # 118 tests, about 10 s
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
