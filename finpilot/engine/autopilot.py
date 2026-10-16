"""
Cash autopilot: find where cash dips below the owner's safety level in the next 90 days, and the moves that
fix it — each move's effect measured by re-running the same tested forecast with the move applied.

Agents and their moves:
  collections  "Collect ₹X from <customer>"   overdue money owed, assumed received `collect_in_days` from today
  payables     "Ask <supplier> to move <bill>" a supplier bill falling before the low point, moved `defer_days` later
  spending     "Pause owner drawings / marketing" the typical monthly amount, not spent for `pause_days`
  tax          "Set aside ₹X for GST"          keeps the typical GST payment ready; changes no cash, only free cash

Nothing here is a prediction: it is the forecast's arithmetic with each stated assumption applied.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.common import fmt_inr, money, ts
from finpilot.engine.decision import default_buffer
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow, run_rate

SAFETY_SHARE = 0.5  # default safety level: about two weeks of running costs
DEFERRABLE = {"raw materials", "packaging", "logistics", "purchases", "professional fees", "marketing", "office supplies", "repairs & maintenance", "travel"}
PAUSABLE = {"Owner Drawings": "Pause owner drawings", "Marketing": "Pause marketing spend"}
AGENT = {"collect": "collections", "defer": "payables", "pause": "spending", "reserve": "tax"}


@dataclass(frozen=True)
class Settings:
    horizon_days: int = 90
    collect_in_days: int = 7
    defer_days: int = 21
    pause_days: int = 60


AT_RISK_DAYS = 30  # a customer this late on an older invoice probably won't pay the next one on time either


def at_risk(obligations: pd.DataFrame | None, as_of, days: int = AT_RISK_DAYS) -> tuple[pd.DataFrame | None, list[dict]]:
    """Upcoming invoices from customers who are already more than `days` late are not counted on their due date.
    Returns the obligations as the forecast should see them, and what was set aside."""
    if obligations is None or not len(obligations):
        return obligations, []
    a = ts(as_of)
    o = obligations.copy()
    o["due_date"] = pd.to_datetime(o["due_date"])
    pend = (o["status"] == "pending") & (o["kind"] == "receivable")
    late = o[pend & (o["due_date"] < a)].groupby("counterparty")["due_date"].min()
    risky = {c for c, d in late.items() if (a - d).days > days}
    mask = pend & (o["due_date"] >= a) & o["counterparty"].isin(risky)
    out = [{"party": c, "amount": money(g["amount"].sum()), "items": g["item_id"].tolist(), "next_due": str(g["due_date"].min().date()),
            "oldest_late_days": int((a - late[c]).days)} for c, g in o[mask].groupby("counterparty")]
    o.loc[mask, "status"] = "at_risk"
    return o, out


def default_safety(ledger: pd.DataFrame, as_of) -> float:
    return float(round(default_buffer(ledger, as_of) * SAFETY_SHARE, -3))


def _forecast(ledger, balances, obligations, as_of, horizon, safety, extra=None, obl=None):
    return forecast_cash_flow(ledger, balances, obligations if obl is None else obl, as_of,
                              ForecastOptions(horizon_days=horizon, include_run_rate=True, min_buffer=safety, extra_flows=extra or []))


def candidates(ledger, balances, obligations, as_of, base: dict, s: Settings) -> list[dict]:
    a = ts(as_of)
    out: list[dict] = []
    o = pd.DataFrame() if obligations is None else obligations.copy()
    if len(o):
        for c in ("due_date", "issue_date"):
            o[c] = pd.to_datetime(o[c])
        pend = o[o["status"] == "pending"]
        od = pend[(pend["kind"] == "receivable") & (pend["due_date"] < a)]
        for name, g in od.groupby("counterparty"):
            amt = money(g["amount"].sum())
            out.append({"id": f"collect:{name}", "kind": "collect", "party": name, "amount": amt, "items": g["item_id"].tolist(),
                        "days_late": int((a - g["due_date"].min()).days),
                        "title": f"Collect {fmt_inr(amt)} from {name}",
                        "detail": f"{len(g)} invoice(s) overdue, oldest {int((a - g['due_date'].min()).days)} days. Assumes they pay within {s.collect_in_days} days of a reminder."})
        low_day = pd.Timestamp(base["lowest_balance_date"])
        bills = pend[(pend["kind"] == "payable") & (pend["due_date"] > a) & (pend["due_date"] <= low_day)
                     & pend["category"].astype(str).str.lower().isin(DEFERRABLE)]
        for r in bills.sort_values("amount", ascending=False).head(4).itertuples():
            new = r.due_date + pd.Timedelta(days=s.defer_days)
            out.append({"id": f"defer:{r.item_id}", "kind": "defer", "party": r.counterparty, "amount": money(r.amount), "items": [r.item_id],
                        "from_date": str(r.due_date.date()), "to_date": str(new.date()),
                        "title": f"Ask {r.counterparty} to move {r.item_id} to {new:%d %b}",
                        "detail": f"{fmt_inr(r.amount)} due {r.due_date:%d %b}. Assumes they agree to {s.defer_days} more days."})
    rr = run_rate(ledger, a)
    for cat, title in PAUSABLE.items():
        row = rr[rr["category"] == cat]
        monthly = float(-row["monthly"].sum()) if len(row) else 0.0
        if monthly >= 1000:
            saved = money(monthly * 12 / 365 * min(s.pause_days, s.horizon_days))
            out.append({"id": f"pause:{cat}", "kind": "pause", "party": cat, "amount": saved, "monthly": money(monthly), "items": [],
                        "title": f"{title} for {s.pause_days} days", "detail": f"About {fmt_inr(monthly)} a month on average; pausing keeps {fmt_inr(saved)} in the bank."})
    gst = rr[rr["category"] == "GST Payment"]
    if len(gst) and -float(gst["monthly"].sum()) >= 1000:
        due = (a + pd.Timedelta(days=1)).replace(day=20) if a.day < 20 else (a + pd.offsets.MonthBegin(1)).replace(day=20)
        amt = money(-float(gst["monthly"].sum()))
        out.append({"id": f"reserve:gst:{due:%Y-%m}", "kind": "reserve", "party": "GST", "amount": amt, "items": [], "due": str(due.date()),
                    "title": f"Set aside {fmt_inr(amt)} for GST due {due:%d %b}",
                    "detail": "Your typical monthly GST payment, kept aside so it isn't spent by mistake. Already in the forecast; it lowers free cash, not the balance."})
    return out


def apply(moves: list[dict], obligations: pd.DataFrame | None, as_of, s: Settings) -> tuple[list[dict], None]:
    """The forecast inputs with these moves made, as extra flows on top of the unchanged records."""
    a = ts(as_of)
    extra: list[dict] = []
    obl = None
    for m in moves:
        if m["kind"] == "collect":
            extra.append({"date": a + pd.Timedelta(days=s.collect_in_days), "amount": m["amount"], "label": m["title"], "source": m["id"], "category": "Collections"})
        elif m["kind"] == "defer":
            # Move exactly this payment: undo it on its due date, pay it on the new date. (Editing the bill's due date instead
            # would also shift where the forecast starts counting typical spend in that category — an effect that isn't real.)
            was = max(pd.Timestamp(m["from_date"]), a + pd.Timedelta(days=1))
            extra.append({"date": was, "amount": m["amount"], "label": f"{m['items'][0]} moved out", "source": m["id"], "category": "Moved bill"})
            extra.append({"date": pd.Timestamp(m["to_date"]), "amount": -m["amount"], "label": f"{m['items'][0]} paid later", "source": m["id"], "category": "Moved bill"})
        elif m["kind"] == "pause":
            per_day = m["monthly"] * 12 / 365
            for k in range(1, min(s.pause_days, s.horizon_days) + 1):
                extra.append({"date": a + pd.Timedelta(days=k), "amount": per_day, "label": m["title"], "source": m["id"], "category": m["party"]})
    return extra, obl


def _summary(f: dict, safety: float, reserves: float = 0.0) -> dict:
    return {"lowest": f["lowest_balance"], "lowest_date": f["lowest_balance_date"], "end": f["checkpoints"][-1]["balance"],
            "below_safety_from": f["first_date_below_buffer"], "runs_out": f["first_negative_date"], "safe": f["lowest_balance"] >= safety,
            "free_cash_today": money(f["starting_cash"] - reserves)}


def _series(f: dict, step: int = 1) -> list[dict]:
    return [{"date": d["date"], "balance": d["balance"]} for i, d in enumerate(f["daily"]) if i % step == 0 or i == len(f["daily"]) - 1]


def plan(ledger, balances, obligations, as_of, safety: float | None = None, approved: set[str] | frozenset = frozenset(), settings: Settings | None = None) -> dict:
    s = settings or Settings()
    safety = default_safety(ledger, as_of) if safety is None else float(safety)
    obligations, risky = at_risk(obligations, as_of)
    base = _forecast(ledger, balances, obligations, as_of, s.horizon_days, safety)
    if base["status"] != "ok":
        return {"status": base["status"], "message": base.get("message", ""), "missing": base.get("missing", []), "safety": safety}

    moves = candidates(ledger, balances, obligations, as_of, base, s)
    for m in moves:
        if m["kind"] == "reserve":
            m["impact"], m["new_lowest"] = 0.0, base["lowest_balance"]
            continue
        extra, obl = apply([m], obligations, as_of, s)
        f = _forecast(ledger, balances, obligations, as_of, s.horizon_days, safety, extra, obl)
        m["new_lowest"] = f["lowest_balance"]
        m["impact"] = money(f["lowest_balance"] - base["lowest_balance"])
    # Only show what would make a difference: anything that lifts the low point, plus overdue money (always worth collecting) and the tax reserve.
    moves = [m for m in moves if m["impact"] > 0 or m["kind"] in ("collect", "reserve")]
    moves.sort(key=lambda m: (m["kind"] == "reserve", -m["impact"]))

    # The agents' suggestion: the fewest moves (biggest first) that lift the low point to the safety level, plus the tax reserve.
    suggested, low = [], base["lowest_balance"]
    for m in moves:
        if m["kind"] == "reserve":
            suggested.append(m["id"])
        elif low < safety and m["impact"] > 0:
            suggested.append(m["id"])
            extra, obl = apply([x for x in moves if x["id"] in suggested and x["kind"] != "reserve"], obligations, as_of, s)
            low = _forecast(ledger, balances, obligations, as_of, s.horizon_days, safety, extra, obl)["lowest_balance"]
    for m in moves:
        m["agent"] = AGENT[m["kind"]]
        m["suggested"] = m["id"] in suggested
        m["approved"] = m["id"] in approved
    moves.sort(key=lambda m: (not m["suggested"], m["kind"] == "reserve", -m["impact"]))

    def scenario(ids) -> dict:
        chosen = [m for m in moves if m["id"] in ids]
        extra, obl = apply([m for m in chosen if m["kind"] != "reserve"], obligations, as_of, s)
        f = _forecast(ledger, balances, obligations, as_of, s.horizon_days, safety, extra) if extra else base
        return {"forecast": f, "summary": _summary(f, safety, sum(m["amount"] for m in chosen if m["kind"] == "reserve"))}

    sug = scenario(set(suggested))
    mine = scenario(set(approved)) if approved else {"forecast": base, "summary": _summary(base, safety)}
    # The bills behind the first problem: running out, else dropping below safety, else the low point.
    low_day = pd.Timestamp(base["first_negative_date"] or base["first_date_below_buffer"] or base["lowest_balance_date"])
    window = [i for i in base["scheduled_items"] if i["amount"] < 0 and low_day - pd.Timedelta(days=14) <= pd.Timestamp(i["date"]) <= low_day]
    causes = sorted(window, key=lambda i: i["amount"])[:3]
    return {
        "status": "ok",
        "as_of": base["as_of"],
        "today": base["starting_cash"],
        "safety": safety,
        "horizon_days": s.horizon_days,
        "baseline": _summary(base, safety),
        "with_suggested": sug["summary"],
        "with_approved": mine["summary"],
        "series": {"baseline": _series(base), "plan": _series(mine["forecast"] if approved else sug["forecast"])},
        "plan_basis": "approved" if approved else "suggested",
        "causes": [{"date": c["date"], "label": c["label"], "amount": -c["amount"], "category": c["category"]} for c in causes],
        "moves": moves,
        "excluded_overdue": money(sum(e["amount"] for e in base["excluded_items"])),
        "at_risk": risky,
        "evidence": Evidence(
            method="Each move is applied to the same 90-day forecast and the forecast is run again; the move's effect is the change in the lowest balance. "
                   "The suggested plan adds moves, biggest effect first, until the lowest balance reaches the safety level.",
            assumptions=tuple(base["evidence"]["assumptions"]) + (
                f"Safety level: {fmt_inr(safety)}" + (" (about two weeks of running costs)." if safety == default_safety(ledger, as_of) else "."),
                *([f"Not counted: upcoming invoices from customers already more than {AT_RISK_DAYS} days late ("
                   + ", ".join(f"{r['party']} {fmt_inr(r['amount'])}" for r in risky) + ")."] if risky else []),
                f"A reminded customer pays within {s.collect_in_days} days; a supplier agrees to {s.defer_days} more days; a paused spend stops for {s.pause_days} days.",
            ),
            limitations=tuple(base["evidence"]["limitations"]) + ("Whether a customer pays or a supplier agrees is up to them — moves are options, not promises.",),
            record_ids=tuple(i for m in moves for i in m["items"]),
            period=(base["as_of"], str((ts(as_of) + pd.Timedelta(days=s.horizon_days)).date())),
        ).to_dict(),
    }


def weekly(f: dict, weeks: int = 13) -> list[dict]:
    """Week-by-week money in, money out and closing balance, with the known items in each week."""
    daily = pd.DataFrame(f["daily"])
    daily["date"] = pd.to_datetime(daily["date"])
    start = daily["date"].iloc[0]
    items = pd.DataFrame(f["scheduled_items"]) if f["scheduled_items"] else pd.DataFrame(columns=["date", "amount", "label", "source", "category", "kind"])
    if len(items):
        items["date"] = pd.to_datetime(items["date"])
    out = []
    for w in range(weeks):
        a, b = start + pd.Timedelta(days=7 * w + 1), start + pd.Timedelta(days=7 * w + 7)
        part = daily[(daily["date"] >= a) & (daily["date"] <= b)]
        if not len(part):
            break
        its = items[(items["date"] >= a) & (items["date"] <= b)] if len(items) else items
        known_in = float(its.loc[its["amount"] > 0, "amount"].sum()) if len(its) else 0.0
        known_out = float(-its.loc[its["amount"] < 0, "amount"].sum()) if len(its) else 0.0
        inflow, outflow = float(part["inflow"].sum()), float(part["outflow"].sum())
        out.append({
            "start": str(a.date()), "end": str(b.date()),
            "money_in": money(inflow), "money_out": money(outflow), "closing": money(part["balance"].iloc[-1]),
            "typical_in": money(inflow - known_in), "typical_out": money(outflow - known_out),
            "items": _week_items(its),
        })
    return out


def _week_items(its: pd.DataFrame) -> list[dict]:
    """The week's known items; a paused category (one small flow per day) shows as one line for the week."""
    if not len(its):
        return []
    rows, paused = [], {}
    for r in its.sort_values("date").itertuples():
        if str(r.source).startswith("pause:"):
            p = paused.setdefault(r.source, {"date": str(r.date.date()), "label": r.label, "amount": 0.0, "source": r.source, "kind": r.kind})
            p["amount"] += r.amount
            continue
        rows.append({"date": str(r.date.date()), "label": r.label, "amount": money(r.amount), "source": r.source, "kind": r.kind})
    rows += [{**p, "amount": money(p["amount"])} for p in paused.values()]
    return sorted(rows, key=lambda x: x["date"])
