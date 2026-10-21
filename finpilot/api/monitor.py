"""
The agents keep watching after the owner approves. Every move that depends on someone else gets a checkpoint:
  collect   the customer should have paid within 10 days of the reminder
  defer     the supplier should have agreed within 4 days
  discount  the customer should have taken the offer within 5 days
At each look (every simulated day when fast-forwarding, and whenever the books are opened) the monitor checks them:
success is logged and learned from; a missed checkpoint is logged, learned from, and comes with the next step prepared —
a firmer reminder and Plan B — for the owner to approve. Nothing is sent or paid by the monitor itself.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from finpilot.data import books
from finpilot.engine import autopilot as ap
from finpilot.engine import risk

from .views import day, short


def _l(lang: str, en: str, hi: str, **kw) -> str:
    return (hi if lang == "hi" else en).format(**kw)


def watch_approved(db: Path, book: str, as_of: pd.Timestamp, plan: dict, move: dict, lang: str = "en") -> None:
    """Called when the owner approves a move: remember when it started and, for uncertain moves, set a checkpoint with Plan B."""
    books.set_move_date(db, book, move["id"], str(as_of.date()), {k: move.get(k) for k in ("id", "kind", "party", "amount", "monthly", "items", "due", "from_date", "to_date", "title")})
    if move["kind"] not in ap.CHECKPOINT_DAYS:
        return
    cp = as_of + pd.Timedelta(days=ap.CHECKPOINT_DAYS[move["kind"]])
    pb = next((b for b in plan.get("plan_b", []) if b["if_fails"] == move["id"]), None)
    books.add_watch(db, book, move, str(as_of.date()), str(cp.date()), pb)
    if move["kind"] == "collect":
        books.note_reminder(db, book, move["party"], str(as_of.date()))
        books.log_activity(db, book, str(as_of.date()), "collections", "info",
                           _l(lang, "Reminder sent to {who} for {amt}. I'll check on {d}.", "{who} को {amt} का याद-संदेश भेजा। {d} को जाँचूँगा।",
                              who=move["party"], amt=short(move["amount"]), d=day(cp, lang)))
    elif move["kind"] == "defer":
        books.log_activity(db, book, str(as_of.date()), "payables", "info",
                           _l(lang, "Asked {who} to move a {amt} bill. I'll check on {d}.", "{who} से {amt} का बिल आगे बढ़ाने को कहा। {d} को जाँचूँगा।",
                              who=move["party"], amt=short(move["amount"]), d=day(cp, lang)))
    elif move["kind"] == "discount":
        books.log_activity(db, book, str(as_of.date()), "deals", "info",
                           _l(lang, "Offered {who} an early-payment discount. I'll check on {d}.", "{who} को जल्दी भुगतान पर छूट की पेशकश की। {d} को जाँचूँगा।",
                              who=move["party"], d=day(cp, lang)))


def unwatch(db: Path, book: str, move_id: str) -> None:
    books.drop_watch(db, book, move_id)


def check(db: Path, book: str, obligations: pd.DataFrame | None, as_of: pd.Timestamp, move_states: dict[str, str], lang: str = "en",
          replan=None) -> list[dict]:
    """Look at every open checkpoint. Returns the activity entries it logged (newest last).
    `replan(extra_approved=frozenset())` gives the planner's plan for the books as they are now (as if `extra_approved` were approved too); when a checkpoint is missed, Plan B is what it says
    (the same thing the owner's "Switch to Plan B" approves). Without it, the Plan B stored at approval time is described."""
    logged: list[dict] = []
    today = str(as_of.date())

    def log(agent, tone, text, action=None):
        books.log_activity(db, book, today, agent, tone, text, action)
        logged.append({"book_date": today, "agent": agent, "tone": tone, "text": text, "action": action})

    o = obligations
    paid_ids: set[str] = set()
    if o is not None and len(o):
        paid_ids = set(o.loc[o["status"] == "paid", "item_id"])
    for w in books.watches(db, book):
        started = pd.Timestamp(w["started"])
        due = pd.Timestamp(w["checkpoint"])
        if w["kind"] == "collect":
            done = bool(w["items"]) and any(i in paid_ids for i in w["items"])
        elif w["kind"] == "defer":
            done = move_states.get(w["move_id"]) == "done"
        else:
            done = bool(w["items"]) and w["items"][0] in paid_ids
        if done:
            books.close_watch(db, book, w["id"], "done", today)
            if w["kind"] == "collect":
                before = risk.learned_reminder_p(books.reminder_outcomes(db, book)).get(w["party"], risk.REMINDED_PAY_PROB)
                books.resolve_reminder(db, book, w["party"], "paid", today)
                after = risk.learned_reminder_p(books.reminder_outcomes(db, book))[w["party"]]
                log("collections", "good", _l(lang, "{who} paid {amt} — {n} days after the reminder. Checkpoint met.",
                                              "{who} ने {amt} चुकाए — याद-संदेश के {n} दिन बाद। चेकपॉइंट पूरा।",
                                              who=w["party"], amt=short(w["amount"]), n=(as_of - started).days))
                log("risk", "info", _l(lang, "Learned: {who} pays after a reminder more often than I assumed — {a} → {b}.",
                                       "सीखा: {who} याद दिलाने पर अनुमान से ज़्यादा भुगतान करते हैं — {a} → {b}।",
                                       who=w["party"], a=f"{before:.0%}", b=f"{after:.0%}"))
            elif w["kind"] == "defer":
                log("payables", "good", _l(lang, "{who} agreed to move the bill. Checkpoint met.", "{who} बिल आगे बढ़ाने को मान गए। चेकपॉइंट पूरा।", who=w["party"]))
            else:
                log("deals", "good", _l(lang, "{who} took the early-payment offer.", "{who} ने जल्दी भुगतान की पेशकश मान ली।", who=w["party"]))
            continue
        if as_of < due:
            continue
        books.close_watch(db, book, w["id"], "missed", today)
        if w["kind"] == "collect":
            before = risk.learned_reminder_p(books.reminder_outcomes(db, book)).get(w["party"], risk.REMINDED_PAY_PROB)
            books.resolve_reminder(db, book, w["party"], "no", today)
            after = risk.learned_reminder_p(books.reminder_outcomes(db, book))[w["party"]]
            log("collections", "bad", _l(lang, "{who} hasn't paid {amt} by the {d} checkpoint, {n} days after the reminder. A firmer reminder is ready.",
                                         "{who} ने {d} के चेकपॉइंट तक {amt} नहीं चुकाए — याद-संदेश के {n} दिन बाद। कड़ा याद-संदेश तैयार है।",
                                         who=w["party"], amt=short(w["amount"]), d=day(due, lang), n=(as_of - started).days),
                {"type": "remind", "party": w["party"]})
            log("risk", "caution", _l(lang, "Learned: {who} is less likely to pay after a reminder than I assumed — {a} → {b}. Odds updated.",
                                      "सीखा: {who} याद दिलाने पर अनुमान से कम भुगतान करते हैं — {a} → {b}। संभावनाएँ अपडेट कीं।",
                                      who=w["party"], a=f"{before:.0%}", b=f"{after:.0%}"))
        elif w["kind"] == "defer":
            log("payables", "bad", _l(lang, "{who} hasn't agreed to move the bill by {d}.", "{who} {d} तक बिल आगे बढ़ाने को नहीं माने।", who=w["party"], d=day(due, lang)))
        else:
            log("deals", "caution", _l(lang, "{who} didn't take the early-payment offer by {d}.", "{who} ने {d} तक जल्दी भुगतान की पेशकश नहीं मानी।", who=w["party"], d=day(due, lang)))
        fresh = replan() if replan else None
        if fresh and fresh.get("status") == "ok":
            todo = [m for m in fresh["moves"] if m["suggested"] and m["kind"] != "reserve" and move_states.get(m["id"]) not in ("approved", "done")]
            bk = next((m for m in fresh["moves"] if m["kind"] == "borrow" and move_states.get(m["id"]) not in ("approved", "done")), None)
            what = ", ".join(_pretty(m["id"], lang) for m in todo) or _l(lang, "keep the moves you approved", "मंज़ूर कदम जारी रखें")
            if bk:
                what += _l(lang, " + a {amt} standby overdraft", " + {amt} का स्टैंडबाय ओवरड्राफ़्ट", amt=short(bk["amount"]))
            # the odds with everything that would then be in place: what's approved already plus Plan B
            after = replan(frozenset(m["id"] for m in todo) | ({bk["id"]} if bk else set()))
            p_safe = (after.get("odds", {}).get("approved") or {}).get("p_safe", fresh["odds"]["suggested"]["p_safe"])
            log("planner", "caution", _l(lang, "Re-planned with today's books. Plan B needs your OK: {what}. Chance of staying safe with it: {p}.",
                                         "आज के खातों से दोबारा योजना बनाई। Plan B के लिए आपकी मंज़ूरी चाहिए: {what}। इससे सुरक्षित रहने की संभावना: {p}।",
                                         what=what, p=f"{p_safe:.0%}"), {"type": "plan_b"})
            continue
        pb = w["plan_b"]
        if pb:
            what = ", ".join(_pretty(x, lang) for x in pb["then"]) or _l(lang, "no other moves", "कोई और कदम नहीं")
            if pb.get("backup"):
                what += _l(lang, " + a {amt} standby overdraft", " + {amt} का स्टैंडबाय ओवरड्राफ़्ट", amt=short(pb["backup"]["amount"]))
            p_safe = pb["backup"]["p_safe"] if pb.get("backup") else pb["p_safe"]
            log("planner", "caution", _l(lang, "Switching to Plan B needs your OK: {what}. Chance of staying safe with it: {p}.",
                                         "Plan B पर जाने के लिए आपकी मंज़ूरी चाहिए: {what}। इससे सुरक्षित रहने की संभावना: {p}।",
                                         what=what, p=f"{p_safe:.0%}"), {"type": "plan_b"})
    return logged


def _pretty(move_id: str, lang: str) -> str:
    kind, _, rest = move_id.partition(":")
    if kind == "pause":
        w = {"Owner Drawings": ("pause owner drawings", "मालिक की निकासी रोकें"), "Marketing": ("pause marketing", "मार्केटिंग रोकें")}.get(rest, (f"pause {rest}", f"{rest} रोकें"))
        return w[1 if lang == "hi" else 0]
    if kind == "collect":
        return _l(lang, "collect from {who}", "{who} से वसूली", who=rest)
    if kind == "defer":
        return _l(lang, "move bill {id}", "बिल {id} आगे बढ़ाएँ", id=rest)
    if kind == "discount":
        return _l(lang, "early-payment offer on {id}", "{id} पर जल्दी भुगतान की पेशकश", id=rest)
    return move_id
