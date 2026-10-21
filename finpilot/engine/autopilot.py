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
from itertools import product

import numpy as np
import pandas as pd

from finpilot.data.schema import Evidence
from finpilot.engine.common import fmt_inr, money, ts
from finpilot.engine.decision import default_buffer
from finpilot.engine.forecast import ForecastOptions, forecast_cash_flow, run_rate
from finpilot.engine import risk

SAFETY_SHARE = 0.5  # default safety level: about two weeks of running costs
DEFERRABLE = {"raw materials", "packaging", "logistics", "purchases", "professional fees", "marketing", "office supplies", "repairs & maintenance", "travel"}
PAUSABLE = {"Owner Drawings": "Pause owner drawings", "Marketing": "Pause marketing spend"}
AGENT = {"collect": "collections", "defer": "payables", "pause": "spending", "reserve": "tax", "borrow": "financing", "discount": "deals"}
DISCOUNT = 0.02          # early-payment discount the deals agent may offer
DISCOUNT_PAY_IN_DAYS = 7
DISCOUNT_MIN = 50_000    # only invoices worth a phone call
CHECKPOINT_DAYS = {"collect": 10, "defer": 4, "discount": 5}  # when to decide a move has not worked
BACKUP_RATE = 0.14   # assumed yearly interest on a standby overdraft, to show what the backup would cost if fully used
BACKUP_STEP = 25_000
# How much a move asks of the owner: collecting money already owed is easiest; cutting their own drawings is hardest.
EFFORT = {"collect": 1, "defer": 2, "discount": 2, "pause:Marketing": 2, "pause:Owner Drawings": 3, "borrow": 4}
TARGET_ODDS = 0.8      # the planner aims for cash to stay above safety in at least this share of simulated futures
ODDS_TOLERANCE = 0.03  # plans within this many points of the best odds count as equally safe; the easier one wins
MAX_SEARCH_MOVES = 12
STRESS_TESTED = 8


@dataclass(frozen=True)
class Settings:
    horizon_days: int = 90
    collect_in_days: int = 7
    defer_days: int = 21
    pause_days: int = 60
    backup_days: int = 90


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


def stuck_parties(obligations: pd.DataFrame | None, as_of, days: int = AT_RISK_DAYS) -> set[str]:
    """Customers more than `days` late on an unpaid invoice."""
    if obligations is None or not len(obligations):
        return set()
    a = ts(as_of)
    o = obligations[(obligations["kind"] == "receivable") & (obligations["status"] == "pending")]
    late = pd.to_datetime(o["due_date"]).groupby(o["counterparty"]).min()
    return {c for c, d in late.items() if (a - d).days > days}


def effort(m: dict) -> int:
    return EFFORT.get(m["id"], EFFORT.get(m["kind"], 2))


def delta(flows: list[dict], as_of, horizon: int) -> np.ndarray:
    """The change these extra flows make to each day's balance (index 0 = today) — exactly as the forecast adds them."""
    a = ts(as_of)
    v = np.zeros(horizon + 1)
    for f in flows:
        i = max(int((ts(f["date"]) - a).days), 1)
        if i <= horizon:
            v[i] += f["amount"]
    return np.cumsum(v)


def default_safety(ledger: pd.DataFrame, as_of) -> float:
    return float(round(default_buffer(ledger, as_of) * SAFETY_SHARE, -3))


def _forecast(ledger, balances, obligations, as_of, horizon, safety, extra=None, obl=None):
    return forecast_cash_flow(ledger, balances, obligations if obl is None else obl, as_of,
                              ForecastOptions(horizon_days=horizon, include_run_rate=True, min_buffer=safety, extra_flows=extra or [],
                                              customer_delays=True, billing_cycles=True, recurring=True))


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
        # Deals agent: a reliable customer's invoice due after the tight days, paid early for a small discount.
        trouble = pd.Timestamp(base["first_negative_date"] or base["first_date_below_buffer"] or base["lowest_balance_date"])
        late_now = set(pend[(pend["kind"] == "receivable") & (pend["due_date"] < a)]["counterparty"])
        later = pend[(pend["kind"] == "receivable") & (pend["due_date"] > trouble) & (pend["due_date"] <= a + pd.Timedelta(days=s.horizon_days))
                     & (pend["due_date"] > a + pd.Timedelta(days=DISCOUNT_PAY_IN_DAYS + 3)) & (pend["amount"] >= DISCOUNT_MIN) & ~pend["counterparty"].isin(late_now)]
        for r in later.sort_values("amount", ascending=False).head(3).itertuples():
            by = a + pd.Timedelta(days=DISCOUNT_PAY_IN_DAYS)
            out.append({"id": f"discount:{r.item_id}", "kind": "discount", "party": r.counterparty, "amount": money(r.amount * (1 - DISCOUNT)), "items": [r.item_id],
                        "invoice": money(r.amount), "cost": money(r.amount * DISCOUNT), "from_date": str(r.due_date.date()), "to_date": str(by.date()),
                        "title": f"Offer {r.counterparty} {DISCOUNT:.0%} off to pay {r.item_id} by {by:%d %b}",
                        "detail": f"{fmt_inr(r.amount)} due {r.due_date:%d %b}. Costs {fmt_inr(r.amount * DISCOUNT)}; assumes they accept."})
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
        elif m["kind"] == "discount":
            extra.append({"date": pd.Timestamp(m["to_date"]), "amount": m["amount"], "label": f"{m['items'][0]} paid early", "source": m["id"], "category": "Early payment"})
            extra.append({"date": pd.Timestamp(m["from_date"]), "amount": -m["invoice"], "label": f"{m['items'][0]} not due any more", "source": m["id"], "category": "Early payment"})
        elif m["kind"] == "borrow":
            extra.append({"date": a + pd.Timedelta(days=1), "amount": m["amount"], "label": m["title"], "source": m["id"], "category": "Overdraft"})
        elif m["kind"] == "pause":
            per_day = m["monthly"] * 12 / 365
            for k in range(1, min(s.pause_days, s.horizon_days) + 1):
                extra.append({"date": a + pd.Timedelta(days=k), "amount": per_day, "label": m["title"], "source": m["id"], "category": m["party"]})
    return extra, obl


def _summary(f: dict, safety: float, reserves: float = 0.0) -> dict:
    trouble = f["first_negative_date"] or f["first_date_below_buffer"]
    return {"lowest": f["lowest_balance"], "lowest_date": f["lowest_balance_date"], "end": f["checkpoints"][-1]["balance"],
            "below_safety_from": f["first_date_below_buffer"], "runs_out": f["first_negative_date"], "safe": f["lowest_balance"] >= safety,
            "free_cash_today": money(f["starting_cash"] - reserves),
            # what could be spent today without going below the safety level on any day ahead
            "spendable_today": money(max(0.0, min(f["lowest_balance"] - safety, f["starting_cash"] - reserves - safety))),
            "days_to_trouble": int((ts(trouble) - ts(f["as_of"])).days) if trouble else None}


def _odds(o: dict) -> dict:
    return {k: v for k, v in o.items() if k != "_paths"}


def _series(f: dict, step: int = 1) -> list[dict]:
    return [{"date": d["date"], "balance": d["balance"]} for i, d in enumerate(f["daily"]) if i % step == 0 or i == len(f["daily"]) - 1]


def plan(ledger, balances, obligations, as_of, safety: float | None = None, approved: set[str] | frozenset = frozenset(), settings: Settings | None = None,
         commitments: list[dict] | tuple = (), outcomes: dict[str, tuple[int, int]] | None = None, contingencies: bool = True) -> dict:
    """`commitments` are extra flows the owner is considering (e.g. a purchase): included in every forecast, simulation and plan.
    `outcomes`: per customer (reminders sent, paid after a reminder) — what the agents have learned so far."""
    commitments = list(commitments)
    s = settings or Settings()
    safety = default_safety(ledger, as_of) if safety is None else float(safety)
    obligations, risky = at_risk(obligations, as_of)
    base = _forecast(ledger, balances, obligations, as_of, s.horizon_days, safety, commitments)
    if base["status"] != "ok":
        return {"status": base["status"], "message": base.get("message", ""), "missing": base.get("missing", []), "safety": safety}

    moves = candidates(ledger, balances, obligations, as_of, base, s)
    H = len(base["daily"]) - 1
    B = np.array([d["balance"] for d in base["daily"]], dtype=float)
    for m in moves:
        if m["kind"] == "reserve":
            m["impact"], m["new_lowest"], m["_delta"] = 0.0, base["lowest_balance"], np.zeros(H + 1)
            continue
        m["_delta"] = delta(apply([m], obligations, as_of, s)[0], as_of, H)
        m["new_lowest"] = money(float((B + m["_delta"]).min()))
        m["impact"] = money(m["new_lowest"] - base["lowest_balance"])
    # Only show what would make a difference: anything that lifts the low point, plus overdue money (always worth collecting) and the tax reserve.
    moves = [m for m in moves if m["impact"] > 0 or m["kind"] in ("collect", "reserve")]
    moves.sort(key=lambda m: (m["kind"] == "reserve", -m["impact"]))

    # The planner: every combination of moves is scored exactly (moves add up day by day), then the most promising plans are
    # stress-tested in the same simulated futures. It picks the plan with the best odds of staying above safety, and among
    # plans about as safe, the one that asks least of the owner.
    model = risk.build(ledger, obligations, as_of, base, stuck_parties(obligations, as_of), outcomes)
    pool = [m for m in moves if m["kind"] != "reserve"][:MAX_SEARCH_MOVES]

    def odds_for(ids: set[str], extra_moves: list[dict] = (), fails: frozenset = frozenset()) -> dict:
        chosen = [m for m in [*moves, *extra_moves] if m["id"] in ids and m["kind"] != "reserve"]
        extra = sum((m["_delta"] for m in chosen if m["kind"] not in ("collect", "discount")), np.zeros(H + 1))
        pulled = {m["items"][0]: (DISCOUNT_PAY_IN_DAYS, 1 - DISCOUNT) for m in chosen if m["kind"] == "discount"}
        return risk.simulate(model, safety, extra, frozenset(m["party"] for m in chosen if m["kind"] == "collect"), fails=fails, pulled=pulled)

    def search(pool: list[dict], fails: frozenset = frozenset(), limit: int = STRESS_TESTED) -> tuple[list[dict], dict, int]:
        masks = np.array(list(product((0, 1), repeat=len(pool))), dtype=float) if pool else np.zeros((1, 0))
        D = np.array([m["_delta"] for m in pool]) if pool else np.zeros((0, H + 1))
        lows = (B[None, :] + masks @ D).min(axis=1)
        costs = masks @ np.array([effort(m) for m in pool], dtype=float) if pool else np.zeros(1)
        feasible = np.where(lows >= safety)[0]
        order = feasible[np.lexsort((-lows[feasible], costs[feasible]))] if len(feasible) else np.argsort(-lows)
        picks = list(range(len(masks))) if len(masks) <= 2 * limit else list(dict.fromkeys([0, *order[:limit - 1].tolist(), len(masks) - 1]))
        tested = []
        for i in picks:
            ids = {pool[k]["id"] for k in range(len(pool)) if masks[i][k]}
            o = odds_for(ids, fails=fails)
            tested.append({"moves": [pool[k]["id"] for k in range(len(pool)) if masks[i][k]], "cost": int(costs[i]), "lowest": money(lows[i]),
                           "reaches_safety": bool(lows[i] >= safety), "p_safe": o["p_safe"], "p_short": o["p_short"], "_odds": o})
        good = [t for t in tested if t["reaches_safety"]] or tested
        best = max(t["p_safe"] for t in good)
        close = [t for t in good if t["p_safe"] >= TARGET_ODDS] if best >= TARGET_ODDS else [t for t in good if t["p_safe"] >= best - ODDS_TOLERANCE]
        if any(t["reaches_safety"] for t in tested):
            pick = min(close, key=lambda t: (t["cost"], -t["p_safe"], -t["lowest"]))
        else:  # nothing gets there: take the most protection available
            pick = max(close, key=lambda t: (t["lowest"], -t["cost"]))
        return tested, pick, int(len(masks))

    def backup_for(pick: dict, fails: frozenset = frozenset()) -> dict:
        need = max(2 * BACKUP_STEP, float(np.ceil(max(safety - pick["_odds"]["bad_case_lowest"], 0) / BACKUP_STEP) * BACKUP_STEP))
        b = {"id": "borrow:standby", "kind": "borrow", "party": "Bank", "amount": money(need), "items": [], "backup": True,
             "interest_if_used": money(need * BACKUP_RATE * s.backup_days / 365),
             "title": f"Keep a {fmt_inr(need)} overdraft ready as a backup",
             "detail": f"Only if the plan falls short. At about {BACKUP_RATE:.0%} a year, using all of it for {s.backup_days} days would cost about "
                       f"{fmt_inr(need * BACKUP_RATE * s.backup_days / 365)} in interest."}
        b["_delta"] = delta(apply([b], obligations, as_of, s)[0], as_of, H)
        b["new_lowest"] = money(float((B + b["_delta"]).min()))
        b["impact"] = money(b["new_lowest"] - base["lowest_balance"])
        b["odds_with_plan"] = odds_for({*pick["moves"], b["id"]}, extra_moves=[b], fails=fails)["p_safe"]
        return b

    tested, chosen, n_combos = search(pool)
    suggested = [*chosen["moves"], *[m["id"] for m in moves if m["kind"] == "reserve"]]
    # The financing agent: if even the best plan leaves real risk, size a standby overdraft from the bad futures (1 in 10),
    # so the owner can arrange it now rather than in a hurry. It is a backup, never part of the suggested plan.
    if chosen["p_safe"] < TARGET_ODDS:
        moves.append(backup_for(chosen))

    # Plan B: for every move in the plan that depends on someone else (a customer paying, a supplier agreeing), what to do
    # if it hasn't worked by its checkpoint — the best plan without it, plus a backup if that still leaves real risk.
    plan_b = []
    by_id = {m["id"]: m for m in moves}
    for mid in (chosen["moves"] if contingencies else []):
        m = by_id[mid]
        if m["kind"] not in CHECKPOINT_DAYS:
            continue
        fails = frozenset({m["party"]}) if m["kind"] == "collect" else frozenset()
        rest = [x for x in pool if x["id"] != mid and not (m["kind"] == "collect" and x["kind"] == "discount" and x["party"] == m["party"])]
        _, alt, _ = search(rest, fails, limit=4)
        bk = backup_for(alt, fails) if alt["p_safe"] < TARGET_ODDS else None
        plan_b.append({"if_fails": mid, "checkpoint": str((ts(as_of) + pd.Timedelta(days=CHECKPOINT_DAYS[m["kind"]])).date()),
                       "then": alt["moves"], "lowest": alt["lowest"], "p_safe": alt["p_safe"], "reaches_safety": alt["reaches_safety"],
                       "backup": {"amount": bk["amount"], "p_safe": bk["odds_with_plan"], "interest_if_used": bk["interest_if_used"]} if bk else None})
    for m in moves:
        m["agent"] = AGENT[m["kind"]]
        m["suggested"] = m["id"] in suggested
        m["approved"] = m["id"] in approved
        m["effort"] = effort(m)
    moves.sort(key=lambda m: (m.get("backup", False), not m["suggested"], m["kind"] == "reserve", -m["impact"]))
    base_odds = next(t["_odds"] for t in tested if not t["moves"])
    learned = {k: round(v, 3) for k, v in model.reminder_p.items()}

    def scenario(ids) -> dict:
        chosen = [m for m in moves if m["id"] in ids]
        extra, obl = apply([m for m in chosen if m["kind"] != "reserve"], obligations, as_of, s)
        f = _forecast(ledger, balances, obligations, as_of, s.horizon_days, safety, extra + commitments) if extra else base
        return {"forecast": f, "summary": _summary(f, safety, sum(m["amount"] for m in chosen if m["kind"] == "reserve"))}

    sug = scenario(set(suggested))
    mine = scenario(set(approved)) if approved else {"forecast": base, "summary": _summary(base, safety)}
    mine_odds = odds_for(set(approved)) if approved else base_odds
    # The auditor: the chosen plan is run through the real forecast again; it must match the planner's arithmetic.
    audit = {"planned_lowest": chosen["lowest"], "rerun_lowest": sug["summary"]["lowest"],
             "matches": abs(chosen["lowest"] - sug["summary"]["lowest"]) < 1}
    for m in moves:
        m.pop("_delta", None)
    # The bills behind the first problem: running out, else dropping below safety, else the low point.
    low_day = pd.Timestamp(base["first_negative_date"] or base["first_date_below_buffer"] or base["lowest_balance_date"])
    window = [i for i in base["scheduled_items"] if i["amount"] < 0 and low_day - pd.Timedelta(days=14) <= pd.Timestamp(i["date"]) <= low_day]
    causes = sorted(window, key=lambda i: i["amount"])[:3]
    return {
        "status": "ok",
        "as_of": base["as_of"],
        "today": base["starting_cash"],
        "known_items": len(base["scheduled_items"]),
        "safety": safety,
        "horizon_days": s.horizon_days,
        "baseline": _summary(base, safety),
        "with_suggested": sug["summary"],
        "with_approved": mine["summary"],
        "series": {"baseline": _series(base), "plan": _series(mine["forecast"] if approved else sug["forecast"])},
        "plan_basis": "approved" if approved else "suggested",
        "odds": {"baseline": _odds(base_odds), "suggested": _odds(chosen["_odds"]), "approved": _odds(mine_odds) if approved else None,
                 "target": TARGET_ODDS, "assumptions": risk.assumptions(model)},
        "plan_b": plan_b,
        "learned": learned,
        "search": {"moves_considered": len(pool), "combinations": n_combos, "stress_tested": len(tested), "sims_each": risk.N_SIMS,
                   "plans": [{k: v for k, v in t.items() if k != "_odds"} for t in sorted(tested, key=lambda t: (-t["p_safe"], t["cost"]))]},
        "audit": audit,
        "causes": [{"date": c["date"], "label": c["label"], "amount": -c["amount"], "category": c["category"]} for c in causes],
        "moves": moves,
        "excluded_overdue": money(sum(e["amount"] for e in base["excluded_items"])),
        "at_risk": risky,
        "evidence": Evidence(
            method="Each move is applied to the same 90-day forecast; its effect is the change in the lowest balance. Every combination of moves is scored, "
                   f"the most promising {STRESS_TESTED} are stress-tested in {risk.N_SIMS:,} simulated futures (customer payment dates drawn from their own history), "
                   f"and the plan with the best odds of staying above safety — the easiest one among plans about as safe — is suggested. "
                   "The suggested plan is then run through the forecast again to check the arithmetic.",
            assumptions=tuple(base["evidence"]["assumptions"]) + tuple(risk.assumptions(model)) + (
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


def afford(ledger, balances, obligations, as_of, amount: float, when=None, label: str = "Purchase", safety: float | None = None,
           approved: set[str] | frozenset = frozenset(), settings: Settings | None = None, commitments: list[dict] | tuple = ()) -> dict:
    """Can the business pay `amount` on `when` (default tomorrow) and stay above safety? If not, which moves make it work,
    and what is the earliest day it could be paid without any moves."""
    s = settings or Settings()
    a = ts(as_of)
    day = max(ts(when) if when is not None else a + pd.Timedelta(days=1), a + pd.Timedelta(days=1))
    if day > a + pd.Timedelta(days=s.horizon_days):
        return {"status": "out_of_range", "message": f"Pick a date within the next {s.horizon_days} days."}
    buy = [{"date": day, "amount": -float(amount), "label": label, "source": "purchase", "category": "Purchase"}]
    now = plan(ledger, balances, obligations, as_of, safety, approved, s, commitments=list(commitments), contingencies=False)
    if now["status"] != "ok":
        return now
    p = plan(ledger, balances, obligations, as_of, now["safety"], approved, s, commitments=list(commitments) + buy, contingencies=False)
    safety = p["safety"]
    without = {**p["baseline"], "p_safe": p["odds"]["baseline"]["p_safe"], "p_short": p["odds"]["baseline"]["p_short"]}
    plan_moves = [m for m in p["moves"] if m["suggested"] and m["kind"] != "reserve"]
    with_plan = {**p["with_suggested"], "p_safe": p["odds"]["suggested"]["p_safe"], "p_short": p["odds"]["suggested"]["p_short"],
                 "moves": [{"id": m["id"], "title": m["title"], "agent": m["agent"]} for m in plan_moves]}
    # Earliest day it can be paid with no moves: before the purchase nothing changes, after it every day is `amount` lower.
    B = np.array([d["balance"] for d in now["series"]["baseline"]], dtype=float)
    earliest = None
    for k in range(1, len(B)):
        if min(B[:k].min(), (B[k:] - amount).min()) >= safety:
            earliest = str((a + pd.Timedelta(days=k)).date())
            break
    if without["safe"] and without["p_safe"] >= TARGET_ODDS:
        verdict = "yes"
    elif with_plan["safe"] and with_plan["p_safe"] >= TARGET_ODDS:
        verdict = "yes_if"
    elif without["safe"] or with_plan["safe"]:
        verdict = "risky"
    else:
        verdict = "not_now"
    return {
        "status": "ok", "verdict": verdict, "amount": money(amount), "date": str(day.date()), "label": label, "safety": safety,
        "today": now["today"], "before": {**now["baseline"], "p_safe": now["odds"]["baseline"]["p_safe"]},
        "without_moves": without, "with_plan": with_plan, "earliest_safe_date_without_moves": earliest,
        "evidence": p["evidence"],
    }


def evaluate_flows(ledger, balances, obligations, as_of, flows: list[dict], label: str = "Idea", safety: float | None = None,
                   approved: set[str] | frozenset = frozenset(), outcomes=None, settings: Settings | None = None) -> dict:
    """Test an idea that isn't one of the standard moves (e.g. an AI strategist's proposal), given as dated cash flows:
    the lowest balance and odds without and with it, on its own and alongside the planner's best plan."""
    s = settings or Settings()
    tagged = [{"date": ts(f["date"]), "amount": float(f["amount"]), "label": f.get("label") or label, "source": "idea", "category": "Idea"} for f in flows]
    before = plan(ledger, balances, obligations, as_of, safety, approved, s, outcomes=outcomes, contingencies=False)
    if before["status"] != "ok":
        return before
    after = plan(ledger, balances, obligations, as_of, before["safety"], approved, s, commitments=tagged, outcomes=outcomes, contingencies=False)
    change = money(after["baseline"]["lowest"] - before["baseline"]["lowest"])
    return {
        "status": "ok", "label": label, "flows": [{"date": str(f["date"].date()), "amount": money(f["amount"])} for f in tagged],
        "net_cash": money(sum(f["amount"] for f in tagged)), "safety_level": before["safety"],
        "lowest_without": before["baseline"]["lowest"], "lowest_with": after["baseline"]["lowest"], "change_in_lowest": change,
        "odds_without": before["odds"]["baseline"]["p_safe"], "odds_with": after["odds"]["baseline"]["p_safe"],
        "odds_best_plan_without": before["odds"]["suggested"]["p_safe"], "odds_best_plan_with": after["odds"]["suggested"]["p_safe"],
        "best_plan_with_it": [m["id"] for m in after["moves"] if m["suggested"] and m["kind"] != "reserve"],
        "verdict": "helps" if change > 1 or after["odds"]["suggested"]["p_safe"] > before["odds"]["suggested"]["p_safe"] + 0.01
                   else "hurts" if change < -1 else "no effect",
    }
