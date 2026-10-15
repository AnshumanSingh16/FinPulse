"""Alerts for the Overview page, each derived from an engine result (and pointing to its evidence)."""

from __future__ import annotations

import pandas as pd

from finpilot.engine.cash import cash_position, obligations_status
from finpilot.engine.common import fmt_inr
from finpilot.engine.expenses import unusual_transactions
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow
from finpilot.engine.decision import default_buffer


def build_alerts(ledger: pd.DataFrame, balances, obligations, as_of) -> list[dict]:
    out: list[dict] = []
    pos = cash_position(ledger, balances, as_of)
    if pos["status"] != "ok":
        out.append({"kind": "caution", "title": "Cash position unknown", "detail": pos["message"]})
    else:
        bad = [c for c in pos["reconciliation"] if not c["reconciled"]]
        for c in bad:
            out.append(
                {
                    "kind": "bad",
                    "title": "Ledger doesn't match the bank balance",
                    "detail": f"On {c['as_of']} the statement says {fmt_inr(c['stated_balance'])} but the ledger implies {fmt_inr(c['computed_from_ledger'])} (difference {fmt_inr(c['difference'])}). Transactions may be missing or duplicated.",
                }
            )
    obl = obligations_status(obligations, as_of)
    if obl["status"] == "ok":
        r = obl["receivables"]
        if r["overdue"]:
            parties = sorted({i["counterparty"] for i in r["overdue_items"]})
            out.append(
                {
                    "kind": "bad" if r["overdue"] > 100_000 else "caution",
                    "title": f"{fmt_inr(r['overdue'])} of customer payments overdue",
                    "detail": f"{r['overdue_count']} invoice(s) from {', '.join(parties)}; oldest {max(i['days_overdue'] for i in r['overdue_items'])} days late.",
                }
            )
        p = obl["payables"]
        if p["overdue"]:
            out.append(
                {
                    "kind": "caution",
                    "title": f"{fmt_inr(p['overdue'])} of bills overdue",
                    "detail": ", ".join(f"{i['item_id']} to {i['counterparty']} ({i['days_overdue']} days)" for i in p["overdue_items"][:3]),
                }
            )
    flags = unusual_transactions(ledger, as_of, lookback_days=90)["flags"]
    dups = [f for f in flags if f["type"] == "possible_duplicate"]
    if dups:
        out.append(
            {
                "kind": "caution",
                "title": f"{len(dups)} possible duplicate payment(s)",
                "detail": "; ".join(f"{f['category']} {fmt_inr(f['amount'])} on {f['date']} ({', '.join(f['txn_ids'])})" for f in dups[:3]),
            }
        )
    big = [f for f in flags if f["type"] in ("outlier", "rare_large_payment")]
    if big:
        top = sorted(big, key=lambda f: -(f["excess"] or f["amount"]))[:3]
        out.append(
            {
                "kind": "info",
                "title": f"{len(big)} unusual payment(s) in the last 90 days",
                "detail": "; ".join(f"{f['category']} {fmt_inr(f['amount'])} on {f['date']}" for f in top),
            }
        )
    if pos["status"] == "ok":
        buffer = default_buffer(ledger, as_of)
        f = forecast_cash_flow(ledger, balances, obligations, as_of, ForecastOptions(include_run_rate=True, min_buffer=buffer))
        if f["status"] == "ok" and f["first_date_below_buffer"]:
            out.append(
                {
                    "kind": "bad" if f["first_negative_date"] else "caution",
                    "title": "Cash may fall below one month of expenses",
                    "detail": f"With scheduled items and typical flows, cash first drops below {fmt_inr(buffer)} on {f['first_date_below_buffer']} (lowest {fmt_inr(f['lowest_balance'])}). An assumption-based projection, not a prediction.",
                }
            )
    return out
