"""
Recommendations with follow-through: for every move the owner approved, was it done, and what happened afterwards?

Read from the books (did the invoice get paid, did the paused spend actually stop, was the GST paid) and from the
agents' own watches (checkpoint met or missed). Nothing is assumed done because it was approved.
"""

from __future__ import annotations

import pandas as pd

from finpilot.engine.common import fmt_inr, money, prepare_ledger, ts


def _l(lang: str, en: str, hi: str, **kw) -> str:
    return (hi if lang == "hi" else en).format(**kw)


def _d(x) -> str:
    return f"{pd.Timestamp(x).day} {pd.Timestamp(x):%b}" if x else ""  # no %-d: it isn't available on Windows


def follow_through(moves: list[dict], approved_on: dict[str, str], watches: list[dict], ledger, obligations, as_of, lang: str = "en") -> list[dict]:
    a = ts(as_of)
    df = prepare_ledger(ledger) if ledger is not None and len(ledger) else None
    o = obligations if obligations is not None and len(obligations) else None
    wmap = {}
    for w in watches:
        wmap.setdefault(w["move_id"], []).append(w)
    out = []
    for m in moves:
        if m.get("state") not in ("approved", "done"):
            continue
        since = ts(approved_on.get(m["id"]) or a)
        status, result, records = "waiting", "", []
        w = (wmap.get(m["id"]) or [None])[-1]
        if m["kind"] == "collect" and o is not None:
            rows = o[o["item_id"].isin(m["items"])]
            paid = rows[rows["status"] == "paid"]
            records = list(rows["item_id"])
            got = money(paid["amount"].sum())
            if len(rows) and len(paid) == len(rows):
                last = pd.to_datetime(paid["paid_date"]).max()
                status = "done"
                result = _l(lang, "{who} paid {amt} on {d} — {n} days after you approved.", "{who} ने {d} को {amt} दिया — मंज़ूरी के {n} दिन बाद।",
                            who=m["party"], amt=fmt_inr(got), d=_d(last), n=max(0, int((last - since).days)))
            elif got:
                status = "partial"
                result = _l(lang, "{amt} of {tot} received so far.", "अब तक {tot} में से {amt} मिले।", amt=fmt_inr(got), tot=fmt_inr(rows["amount"].sum()))
            elif w and w.get("status") == "missed":
                status = "missed"
                result = _l(lang, "Not paid by the {d} checkpoint — Plan B is ready.", "{d} तक भुगतान नहीं — प्लान B तैयार है।", d=_d(w["checkpoint"]))
            else:
                cp = _d(w["checkpoint"] if w else since + pd.Timedelta(days=10))
                result = _l(lang, "Not paid yet. I'll check by {d}.", "अभी नहीं मिला। मैं {d} तक देखूँगा।", d=cp)
        elif m["kind"] == "pause" and df is not None:
            spent = df[(df["category"] == m["party"]) & (df["direction"] == "out") & (df["date"] > since) & (df["date"] <= a)]
            records = list(spent["txn_id"])
            days = int((a - since).days)
            if spent.empty and days == 0:
                result = _l(lang, "Starts today — I'll check that nothing more is spent on it.", "आज से — मैं देखूँगा कि इस पर और खर्च न हो।")
            elif spent.empty:
                status = "done" if days >= 7 else "waiting"
                result = _l(lang, "Nothing spent on it in the {n} days since you approved — {kept} kept so far.", "मंज़ूरी के बाद {n} दिन में इस पर कुछ खर्च नहीं — अब तक {kept} बचे।",
                            n=days, kept=fmt_inr((m.get("monthly") or 0) * days / 30.4167))
            else:
                status = "slipped"
                result = _l(lang, "{amt} was still spent on it after you approved ({k} payment(s)).", "मंज़ूरी के बाद भी इस पर {amt} खर्च हुआ ({k} भुगतान)।",
                            amt=fmt_inr(spent["amount"].sum()), k=len(spent))
        elif m["kind"] == "reserve" and df is not None:
            gst = df[(df["cls"] == "tax_remittance") & (df["direction"] == "out") & (df["date"] > since) & (df["date"] <= a)
                     & df["category"].astype(str).str.contains("GST", case=False)]
            records = list(gst["txn_id"])
            if len(gst):
                status = "done"
                result = _l(lang, "GST of {amt} paid on {d}.", "{d} को {amt} GST भरा।", amt=fmt_inr(gst["amount"].sum()), d=_d(gst["date"].max()))
            else:
                result = _l(lang, "{amt} is set aside for GST due {d}.", "{d} के GST के लिए {amt} अलग रखे हैं।", amt=fmt_inr(m["amount"]), d=_d(m.get("due")))
        elif m["kind"] in ("defer", "discount") and o is not None:
            rows = o[o["item_id"].isin(m["items"])]
            records = list(rows["item_id"])
            if len(rows) and (rows["status"] == "paid").all():
                status = "done"
                result = _l(lang, "Settled on {d}.", "{d} को निपटा।", d=_d(pd.to_datetime(rows["paid_date"]).max()))
            else:
                result = _l(lang, "Waiting for {who}'s answer — tell me when they agree.", "{who} के जवाब का इंतज़ार — हाँ कहें तो मुझे बताएँ।", who=m["party"])
        elif m["kind"] == "borrow":
            result = _l(lang, "Letter to your bank drafted — the overdraft is a backup, used only if needed.", "बैंक को पत्र तैयार — ओवरड्राफ़्ट सिर्फ़ ज़रूरत पड़ने पर।")
        if m.get("state") == "done" and status == "waiting":
            status = "done"
        out.append({"move_id": m["id"], "kind": m["kind"], "party": m["party"], "approved_on": str(since.date()), "status": status, "result": result,
                    "record_ids": records})
    order = {"missed": 0, "slipped": 1, "partial": 2, "waiting": 3, "done": 4}
    return sorted(out, key=lambda x: order.get(x["status"], 5))
