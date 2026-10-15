"""
Rule-based mode, used when no AI key is configured (or the AI call fails).

It recognises the common questions, runs the same approved tools through the same validation and
recording as the AI agent, and writes the answer from templates using only figures the tools
returned. It is labelled as rule-based everywhere it appears — never presented as AI output.
"""

from __future__ import annotations

import re
from typing import Callable

import pandas as pd

from finpilot.data.loader import parse_amount
from finpilot.engine.common import fmt_inr

ToolCaller = Callable[[str, dict], tuple[bool, dict]]

AMOUNT = re.compile(r"(?:₹|rs\.?\s?|inr\s?)?\s?(\d[\d,]*(?:\.\d+)?)\s*(लाख|करोड़|करोड|हज़ार|हजार|lakh|lakhs|lac|crore|cr|k)?", re.I)
UNIT = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "cr": 1e7, "k": 1e3, "लाख": 1e5, "करोड़": 1e7, "करोड": 1e7, "हज़ार": 1e3, "हजार": 1e3}
IDS = re.compile(r"\b(T\d{4}|U\d{5}|E\d{5}|INV-\d{3,}|BILL-[A-Z0-9-]+|SCH-\d{3,}|K-\d{4}(?:-P\d+)?)\b")


def _money(text: str) -> list[float]:
    """₹ amounts in a sentence (₹12 lakh, 12,00,000, 45k). Ignores bare small numbers and percentages."""
    out = []
    for m in AMOUNT.finditer(text):
        raw, unit = m.group(1), (m.group(2) or "").lower()
        tail = text[m.end(): m.end() + 2]
        if "%" in tail:
            continue
        v, _ = parse_amount(raw)
        if v is None:
            continue
        v *= UNIT.get(unit, 1)
        has_symbol = bool(re.match(r"(₹|rs|inr)", m.group(0).strip(), re.I))
        if v >= 1000 or has_symbol or unit:
            out.append(v)
    return out


def _pct(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s?%", text)
    return float(m.group(1)) if m else None


def _months(text: str) -> int | None:
    m = re.search(r"(\d+)\s*(years?|yrs?|saal|sal|साल|वर्ष)", text, re.I)
    if m:
        return int(m.group(1)) * 12
    m = re.search(r"(\d+)\s*(months?|mo\b|mahine|महीने)", text, re.I)
    return int(m.group(1)) if m else None


def _inr(x) -> str:
    return "—" if x is None else fmt_inr(x)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items)


# ---------------------------------------------------------------- phrasebook (English / Hindi)

_LANG = {"v": "en"}

P = {
    "need_price": ("To simulate a purchase I need its price — for example *“Can I afford a ₹12 lakh packing machine on a loan at 11% for 3 years?”*",
                   "ख़रीद जाँचने के लिए उसकी कीमत बताइए — जैसे *“क्या मैं ₹12 लाख की पैकिंग मशीन 11% पर 3 साल के लोन पर ले सकता हूँ?”*"),
    "no_afford": ("**I can't assess affordability yet.** {msg}", "**अभी जाँच नहीं हो सकती।** {msg}"),
    "sim_fail": ("I couldn't run the simulation: {msg}", "सिमुलेशन नहीं चल सका: {msg}"),
    "need_loan": ("**I need a bit more detail to check this loan.** Tell me the interest rate and how many years, from your lender's quote — FinPilot doesn't guess loan terms.",
                  "**इस लोन को जाँचने के लिए थोड़ी और जानकारी चाहिए।** लोन देने वाले से मिली ब्याज दर और कितने साल का लोन है, बताइए — FinPilot लोन की शर्तें अंदाज़े से नहीं लगाता।"),
    "verdict.good": ("Affordable — cash stays above your buffer even in the downside case.", "ख़रीद सकते हैं — मुश्किल हालत में भी कैश सुरक्षित सीमा से ऊपर रहेगा।"),
    "verdict.caution": ("Possible, but it gets tight — check the downside case.", "हो सकता है, पर तंगी होगी — मुश्किल वाली हालत देखें।"),
    "verdict.bad": ("Not affordable on current numbers — cash goes negative in the base case.", "मौजूदा आंकड़ों पर नहीं — सामान्य हालत में भी कैश शून्य से नीचे जाएगा।"),
    "buy.loan": ("Buying **{name}** for {cost} with {dp}% down and an EMI of {emi}, over the next {days} days:",
                 "**{name}** {cost} में, {dp}% डाउन पेमेंट और {emi} की EMI पर — अगले {days} दिन:"),
    "buy.cash": ("Buying **{name}** for {cost} in cash, over the next {days} days:", "**{name}** {cost} नकद में — अगले {days} दिन:"),
    "sc.line": ("**{label}** — lowest bank balance {low} on {date} (without the purchase: {without})", "**{label}** — सबसे कम बैलेंस {low}, {date} को (बिना ख़रीद: {without})"),
    "sc.base": ("Most likely", "सबसे संभावित"), "sc.downside": ("Tough months", "मुश्किल महीने"), "sc.optimistic": ("Goes well", "अच्छा रहा तो"),
    "buffer": ("- Cash buffer used: {buf} (about one month of running costs).", "- सुरक्षित सीमा: {buf} (लगभग एक महीने का खर्च)।"),
    "today_cash": ("- Today's cash: {cash}.", "- आज का कैश: {cash}।"),
    "payback": ("- Simple payback: {m:g} months, based on your expected benefit (not verified by FinPilot).", "- लागत लगभग {m:g} महीने में निकलेगी — आपके बताए फ़ायदे के आधार पर (FinPilot ने इसे जाँचा नहीं)।"),
    "no_benefit": ("- No monthly benefit was given, so the simulation counts only the cost. Tell me what it would save or earn each month to include it.",
                   "- हर महीने का फ़ायदा नहीं बताया, इसलिए सिर्फ़ लागत गिनी गई। जोड़ना हो तो बताइए कि इससे हर महीने कितनी बचत या कमाई होगी।"),
    "interest": ("- Total loan interest over the tenure: {amt}.", "- पूरे लोन पर कुल ब्याज: {amt}।"),
    "sc.note": ("\nScenarios are illustrations under the stated settings, not predictions. Try different numbers on the Plan tab.",
                "\nये अनुमान बताई गई शर्तों पर हैं, भविष्यवाणी नहीं। अलग आंकड़े Plan टैब पर आज़माएँ।"),
    "no_fc": ("**I can't forecast cash yet.** {msg}", "**अभी कैश का अनुमान नहीं लग सकता।** {msg}"),
    "fc.fail": ("The forecast could not run.", "अनुमान नहीं बन सका।"),
    "fc.head": ("**Starting from {cash} in the bank on {date}**, with scheduled invoices and bills plus typical recent flows:",
                "**{date} को बैंक में {cash} से शुरू करके** — तय बिल, उधारी और आपके आम खर्च/बिक्री के साथ:"),
    "fc.cp": ("{d} days ({date}): {bal}", "{d} दिन ({date}): {bal}"),
    "fc.low": ("- Lowest point: {low} on {date}.", "- सबसे कम: {low}, {date} को।"),
    "fc.neg": ("- ⚠ Cash goes negative on {date}.", "- ⚠ {date} को कैश शून्य से नीचे जाएगा।"),
    "fc.sched": ("\nCounting **only scheduled items** (no typical costs or sales), the {d}-day balance would be {bal} — the gap shows how much the answer depends on the typical-flows assumption.",
                 "\n**सिर्फ़ तय बिल और उधारी** गिनें (आम खर्च/बिक्री नहीं), तो {d} दिन बाद बैलेंस {bal} होगा — यह अंतर बताता है कि अनुमान आम खर्च वाली धारणा पर कितना टिका है।"),
    "fc.excl": ("\nOverdue customer payments of {amt} are **not** counted as incoming.", "\nग्राहकों की {amt} की बकाया उधारी आने वाले पैसे में **नहीं** गिनी गई।"),
    "fc.note": ("\nThis is arithmetic on known items and stated assumptions, not a prediction.", "\nयह ज्ञात आंकड़ों और बताई गई धारणाओं का हिसाब है, भविष्यवाणी नहीं।"),
    "exp.fail": ("I couldn't compare expenses.", "खर्च की तुलना नहीं हो सकी।"),
    "exp.head": ("**Running costs were {b} from {pb}, {dir} {chg}{pct} compared with {pa} ({a}).**", "**{pb} में खर्च {b} रहा — {pa} ({a}) के मुकाबले {chg}{pct} {dir}।**"),
    "up": ("up", "ज़्यादा"), "down": ("down", "कम"),
    "exp.big": ("Biggest changes:", "सबसे बड़े बदलाव:"),
    "exp.new": (" (new)", " (नया)"),
    "exp.largest": ("; largest: {what} {amt} on {date} ({id})", "; सबसे बड़ा: {what} {amt}, {date} ({id})"),
    "exp.check": ("\nWorth checking (last 90 days):", "\nजाँचने लायक (पिछले 90 दिन):"),
    "flag.line": ("- {cat} {amt} on {date} ({ids}): {reason}", "- {cat} {amt}, {date} ({ids}): {reason}"),
    "odd.none": ("Nothing unusual found between {a} and {b}.", "{a} से {b} के बीच कुछ असामान्य नहीं मिला।"),
    "odd.head": ("**{n} transaction(s) worth checking** between {a} and {b}:", "{a} से {b} के बीच **{n} लेन-देन जाँचने लायक**:"),
    "odd.possible_duplicate": ("possible duplicate", "शायद दोहरा भुगतान"), "odd.outlier": ("unusually large", "असामान्य रूप से बड़ा"),
    "odd.rare_large_payment": ("rare large payment", "कभी-कभार का बड़ा भुगतान"),
    "odd.line": ("- **{type}** — {cat}, {party}, {amt} on {date} ({ids}). {reason}", "- **{type}** — {cat}, {party}, {amt}, {date} ({ids})। {reason}"),
    "odd.note": ("\nA flag is a prompt to check, not a finding of error.", "\nयह सिर्फ़ जाँचने का इशारा है, गलती का सबूत नहीं।"),
    "cash.unknown": ("**Cash position unknown.** {msg}", "**कैश पता नहीं।** {msg}"),
    "cash.head": ("**Cash in bank on {date}: {cash}.**", "**{date} को बैंक में कैश: {cash}।**"),
    "cash.from": ("- From the balance of {bal} on {date}, plus {n} later transactions (net {net}).", "- {date} के {bal} के बैलेंस से, बाद के {n} लेन-देन जोड़कर (कुल {net})।"),
    "cash.rec_ok": ("- Statement balance on {date}: {bal} — matches the ledger.", "- {date} का स्टेटमेंट बैलेंस {bal} — हिसाब से मेल खाता है।"),
    "cash.rec_bad": ("- Statement balance on {date}: {bal} — differs from the ledger by {diff}.", "- {date} का स्टेटमेंट बैलेंस {bal} — हिसाब से {diff} का अंतर।"),
    "cash.note": ("\nThis is a bank balance, not profit: it includes loans, asset purchases, taxes and owner drawings.", "\nयह बैंक बैलेंस है, मुनाफ़ा नहीं: इसमें लोन, मशीन ख़रीद, टैक्स और मालिक की निकासी भी शामिल हैं।"),
    "owed.head": ("**Customers owe you {total}** — {overdue} of it overdue.", "**ग्राहकों पर आपके {total} बाकी** — इनमें {overdue} बकाया (देर से)।"),
    "owed.item": ("- {id} from {party}: {amt}, due {date} ({days} days late)", "- {id} — {party}: {amt}, देय {date} ({days} दिन देर)"),
    "owe.head": ("\n**You owe suppliers {total}** — {overdue} overdue.", "\n**आपको सप्लायरों को {total} देने हैं** — {overdue} बकाया।"),
    "owe.item": ("- {id} to {party}: {amt}, due {date} ({days} days late)", "- {id} — {party}: {amt}, देय {date} ({days} दिन देर)"),
    "bills.head": ("\nBills due in the next 30 days: {total}.", "\nअगले 30 दिन में देय बिल: {total}।"),
    "bills.item": ("- {date}: {what} — {party}, {amt}", "- {date}: {what} — {party}, {amt}"),
    "sum.head": ("**{period}**", "**{period}**"),
    "sum.rev": ("- Sales received: {amt}", "- बिक्री से मिला: {amt}"),
    "sum.cost": ("- Running costs paid: {amt}", "- चलाने का खर्च: {amt}"),
    "sum.profit": ("- **Profit (estimate): {amt}**{margin} — an estimate before depreciation, unpaid bills and the interest in loan EMIs.",
                   "- **मुनाफ़ा (अनुमान): {amt}**{margin} — घिसाई, बकाया बिल और EMI के ब्याज से पहले का अनुमान।"),
    "sum.margin": (" ({m:.1f}% of sales)", " (बिक्री का {m:.1f}%)"),
    "sum.net": ("- Net cash movement (all money in − out): {amt}", "- कुल आया − कुल गया: {amt}"),
    "sum.outside": ("\nOutside profit: equipment bought {capex}, loans received {loan}, loan repayments {emi}, owner drawings {draw}, GST/TDS paid {tax}.",
                    "\nमुनाफ़े से बाहर: मशीन/सामान {capex}, लोन मिला {loan}, लोन चुकाया {emi}, मालिक ने निकाला {draw}, GST/TDS भरा {tax}।"),
    "rec.txn": ("- {id}: {date} · {what} · {party} · {cat} · {dir} {amt}", "- {id}: {date} · {what} · {party} · {cat} · {dir} {amt}"),
    "in": ("in", "आया"), "out": ("out", "गया"),
    "rec.obl": ("- {id}: {kind} · {party} · {amt} · due {date} · {status}", "- {id}: {kind} · {party} · {amt} · देय {date} · {status}"),
    "rec.nf": ("- Not found: {ids}", "- नहीं मिला: {ids}"),
    "rec.none": ("No matching records.", "कोई रिकॉर्ड नहीं मिला।"),
    "act.ok": ("**Added to your to-dos (#{id}) for your approval.** Nothing has been sent, paid or filed — FinPilot can't do that.",
               "**आपकी मंज़ूरी के लिए काम-सूची में जोड़ा (#{id})।** कुछ भेजा, भरा या चुकाया नहीं गया — FinPilot ऐसा नहीं करता।"),
    "help": ("I can answer questions like:\n- *How profitable were we in the last 6 months?*\n- *Why did expenses go up last month?*\n- *Any duplicate or unusual payments?*\n"
             "- *How much cash do we have, and who owes us?*\n- *Forecast our cash for the next 90 days.*\n"
             "- *Can we afford a ₹12 lakh packing machine on a loan at 11% for 3 years? It would save ₹45,000 a month.*",
             "मैं ऐसे सवालों के जवाब दे सकता हूँ:\n- *पिछले 6 महीने में कितना मुनाफ़ा हुआ?*\n- *पिछले महीने खर्च क्यों बढ़ा?*\n- *कोई दोहरा या अजीब भुगतान?*\n"
             "- *बैंक में कितना पैसा है, और किस पर उधारी बाकी है?*\n- *अगले 90 दिन का कैश अनुमान बताओ।*\n"
             "- *क्या मैं ₹12 लाख की मशीन 11% पर 3 साल के लोन पर ले सकता हूँ? इससे हर महीने ₹45,000 बचेंगे।*"),
}


def _reason(text: str) -> str:
    """Hindi wording for the engine's flag reasons (numbers unchanged)."""
    if _LANG["v"] != "hi":
        return text
    m = re.match(r"([\d.]+)× the usual (.+?) payment \(median ([\d,]+) over (\d+) earlier payments\)\.?", text)
    if m:
        return f"आम {m.group(2)} भुगतान का {m.group(1)}× (पिछले {m.group(4)} भुगतानों का मध्य {m.group(3)})।"
    m = re.match(r"(\d+) identical (outflows|inflows) on the same day", text)
    if m:
        return f"एक ही दिन, एक ही पार्टी के साथ {m.group(1)} एक जैसे लेन-देन।"
    m = re.match(r"A large (.+?) payment", text)
    if m:
        return "इस श्रेणी में कभी-कभार होने वाला बड़ा भुगतान।"
    return text


def tr(key: str, **kw) -> str:
    en, hi = P[key]
    return (hi if _LANG["v"] == "hi" else en).format(**kw)


# ---------------------------------------------------------------- intents


def _purchase(q: str, call: ToolCaller, as_of: pd.Timestamp) -> str:
    amounts = _money(q)
    if not amounts:
        return tr("need_price")
    low = q.lower()
    loan = bool(re.search(r"\b(loan|emi|finance|financ)|लोन|कर्ज", low))
    benefit = None
    m = re.search(r"(?:save|saves|earn|earns|bring|brings|extra|more|benefit|bach|बच)[^.₹\d]{0,30}(₹?\s?\d[\d,]*(?:\.\d+)?\s*(?:lakh|k)?)\s*(?:a|per|/|each)?\s*(?:month|mahine|महीने)", low)
    if not m:  # "हर महीने ₹45,000 बचेंगे" / "har mahine 45k bachenge"
        m = re.search(r"(?:har|हर|every|each|per)\s*(?:month|mahine|महीने)\s*(₹?\s?\d[\d,]*(?:\.\d+)?\s*(?:lakh|k|लाख|हज़ार|हजार)?)", low)
    if not m:
        m = re.search(r"(₹?\s?\d[\d,]*(?:\.\d+)?\s*(?:lakh|k|लाख|हज़ार|हजार)?)\s*(?:a|per|har|हर)?\s*(?:month|mahine|महीने)", low)
    if m:
        b = _money(m.group(1))
        benefit = b[0] if b else None
    cost = max(a for a in amounts if a != benefit) if benefit and len(amounts) > 1 else amounts[0]
    name = "the purchase" if _LANG["v"] == "en" else "यह ख़रीद"
    nm = re.search(r"(?:buy|purchase|afford|get)\s+(?:a|an|the|new)?\s*(?:₹?\s?[\d,.]+\s*(?:lakh|lakhs|crore|cr|k)?\s*)?([a-z][a-z \-]{2,40}?)(?:\s+(?:on|with|for|using|at|that|which|now|next|this)\b|[?.,]|$)", low)
    if nm:
        name = nm.group(1).strip()
    args = {"name": name[:80], "cost": cost, "financing": "loan" if loan else "cash"}
    if loan:
        rate, tenure = _pct(q), _months(q)
        if rate is not None:
            args["loan_rate_pct"] = rate
        if tenure is not None:
            args["tenure_months"] = tenure
        dp = re.search(r"(\d+(?:\.\d+)?)\s?%\s*(?:down|upfront|margin)", low)
        if dp:
            args["down_payment_pct"] = float(dp.group(1))
            if rate == float(dp.group(1)):
                rest = re.sub(r"(\d+(?:\.\d+)?)\s?%\s*(?:down|upfront|margin)", "", q)
                r2 = _pct(rest)
                args.pop("loan_rate_pct", None) if r2 is None else args.update(loan_rate_pct=r2)
    if benefit:
        args["monthly_benefit"] = benefit
    ok_c, cash = call("get_cash_position", {})
    if ok_c and cash.get("status") != "ok":
        return tr("no_afford", msg=cash["message"])
    call("get_upcoming_payments", {"days": 30})
    ok, r = call("simulate_purchase", args)
    if not ok:
        return tr("sim_fail", msg=r["message"])
    if r.get("status") == "needs_input":
        return tr("need_loan")
    if r.get("status") != "ok":
        return r.get("message", "The simulation could not run.")
    sc = {s["scenario"]: s for s in r["scenarios"]}
    lines = [
        f"**{tr('verdict.' + r['verdict_tone'])}**",
        "",
        tr("buy.loan", name=name, cost=_inr(cost), dp=f"{args.get('down_payment_pct', 20):g}", emi=_inr(r["emi"]), days=r["horizon_days"]) if loan
        else tr("buy.cash", name=name, cost=_inr(cost), days=r["horizon_days"]),
        _bullets([tr("sc.line", label=tr("sc." + k), low=_inr(sc[k]["with_purchase"]["lowest_balance"]), date=sc[k]["with_purchase"]["lowest_balance_date"],
                     without=_inr(sc[k]["without_purchase"]["lowest_balance"])) for k in ("base", "downside", "optimistic") if k in sc]),
        tr("buffer", buf=_inr(r["buffer"])),
        tr("today_cash", cash=_inr(cash.get("cash_balance"))) if ok_c and cash.get("status") == "ok" else "",
    ]
    if r["payback_months"]:
        lines.append(tr("payback", m=r["payback_months"]))
    elif not benefit:
        lines.append(tr("no_benefit"))
    if loan and r.get("total_loan_interest"):
        lines.append(tr("interest", amt=_inr(r["total_loan_interest"])))
    lines.append(tr("sc.note"))
    return "\n".join(x for x in lines if x is not None)


def _forecast(q: str, call: ToolCaller, as_of) -> str:
    ok, cash = call("get_cash_position", {})
    if ok and cash.get("status") != "ok":
        return tr("no_fc", msg=cash["message"])
    days = 90
    m = re.search(r"(\d{2,3})\s*(days|din|दिन)", q)
    if m and 7 <= int(m.group(1)) <= 365:
        days = int(m.group(1))
    ok1, typical = call("forecast_cash_flow", {"horizon_days": days, "include_typical_unscheduled_flows": True})
    ok2, sched = call("forecast_cash_flow", {"horizon_days": days, "include_typical_unscheduled_flows": False})
    if not ok1 or typical.get("status") != "ok":
        return typical.get("message", tr("fc.fail"))
    lines = [
        tr("fc.head", cash=_inr(typical["starting_cash"]), date=typical["as_of"]),
        _bullets([tr("fc.cp", d=c["days"], date=c["date"], bal=_inr(c["balance"])) for c in typical["checkpoints"]]),
        tr("fc.low", low=_inr(typical["lowest_balance"]), date=typical["lowest_balance_date"]),
    ]
    if typical.get("first_negative_date"):
        lines.append(tr("fc.neg", date=typical["first_negative_date"]))
    if ok2 and sched.get("status") == "ok":
        lines.append(tr("fc.sched", d=days, bal=_inr(sched["checkpoints"][-1]["balance"])))
    if typical.get("excluded_items"):
        lines.append(tr("fc.excl", amt=_inr(typical["excluded_total"])))
    lines.append(tr("fc.note"))
    return "\n".join(lines)


def _expenses(q: str, call: ToolCaller, as_of) -> str:
    months = 3 if re.search(r"quarter|3 months|three months|3 mahine|3 महीने|तिमाही", q, re.I) else 1
    ok, c = call("analyze_expense_changes", {"months": months})
    if not ok or c.get("status") != "ok":
        return c.get("message", tr("exp.fail"))
    ok_u, u = call("find_unusual_transactions", {"lookback_days": 90})
    pa, pb = c["period_a"], c["period_b"]
    lines = [
        tr("exp.head", b=_inr(c["total_b"]), pb=f"{pb['start']} to {pb['end']}", dir=tr("up" if c["total_change"] > 0 else "down"), chg=_inr(abs(c["total_change"])),
           pct=f" ({abs(c['total_change_pct']):.1f}%)" if c["total_change_pct"] is not None else "", pa=f"{pa['start']} to {pa['end']}", a=_inr(c["total_a"])),
        "",
        tr("exp.big"),
    ]
    for r in [r for r in c["by_category"] if r["change"]][:4]:
        top = r["largest_in_b"][0] if r["largest_in_b"] else None
        pct = f" ({r['change_pct']:+.1f}%)" if r["change_pct"] is not None else tr("exp.new")
        lines.append(f"- **{r['category']}**: {_inr(r['period_a'])} → {_inr(r['period_b'])}{pct}"
                     + (tr("exp.largest", what=top["description"], amt=_inr(top["amount"]), date=top["date"], id=top["txn_id"]) if top else ""))
    if ok_u and u.get("flags"):
        lines.append(tr("exp.check"))
        for f in u["flags"][:4]:
            lines.append(tr("flag.line", cat=f["category"], amt=_inr(f["amount"]), date=f["date"], ids=", ".join(f["txn_ids"]), reason=_reason(f["reason"])))
    return "\n".join(lines)


def _unusual(q: str, call: ToolCaller, as_of) -> str:
    ok, u = call("find_unusual_transactions", {"lookback_days": 90})
    if not ok:
        return u["message"]
    a, b = u["window"]["start"], u["window"]["end"]
    if not u["flags"]:
        return tr("odd.none", a=a, b=b)
    lines = [tr("odd.head", n=len(u["flags"]), a=a, b=b)]
    for f in u["flags"]:
        lines.append(tr("odd.line", type=tr("odd." + f["type"]), cat=f["category"], party=f["counterparty"], amt=_inr(f["amount"]), date=f["date"],
                        ids=", ".join(f["txn_ids"]), reason=_reason(f["reason"])))
    lines.append(tr("odd.note"))
    return "\n".join(lines)


def _cash(q: str, call: ToolCaller, as_of) -> str:
    ok, c = call("get_cash_position", {})
    if c.get("status") != "ok":
        return tr("cash.unknown", msg=c["message"])
    lines = [
        tr("cash.head", date=c["as_of"], cash=_inr(c["cash_balance"])),
        tr("cash.from", bal=_inr(c["anchor_balance"]["balance"]), date=c["anchor_balance"]["as_of"], n=c["transactions_since_anchor"], net=_inr(c["net_movement_since_anchor"])),
    ]
    for r in c["reconciliation"]:
        lines.append(tr("cash.rec_ok", date=r["as_of"], bal=_inr(r["stated_balance"])) if r["reconciled"]
                     else tr("cash.rec_bad", date=r["as_of"], bal=_inr(r["stated_balance"]), diff=_inr(r["difference"])))
    lines.append(tr("cash.note"))
    return "\n".join(lines)


def _owed(q: str, call: ToolCaller, as_of) -> str:
    ok, o = call("get_receivables_and_payables", {})
    if o.get("status") != "ok":
        return o["message"]
    ok_u, up = call("get_upcoming_payments", {"days": 30})
    r, p = o["receivables"], o["payables"]
    lines = [tr("owed.head", total=_inr(r["outstanding"]), overdue=_inr(r["overdue"]))]
    for i in r["overdue_items"][:6]:
        lines.append(tr("owed.item", id=i["item_id"], party=i["counterparty"], amt=_inr(i["amount"]), date=i["due_date"], days=i["days_overdue"]))
    lines.append(tr("owe.head", total=_inr(p["outstanding"]), overdue=_inr(p["overdue"])))
    for i in p["overdue_items"][:4]:
        lines.append(tr("owe.item", id=i["item_id"], party=i["counterparty"], amt=_inr(i["amount"]), date=i["due_date"], days=i["days_overdue"]))
    if ok_u and up.get("status") == "ok":
        lines.append(tr("bills.head", total=_inr(up["upcoming_total"])))
        for i in up["upcoming"][:6]:
            lines.append(tr("bills.item", date=i["due_date"], what=i["description"], party=i["counterparty"], amt=_inr(i["amount"])))
    return "\n".join(lines)


def _summary(q: str, call: ToolCaller, as_of: pd.Timestamp) -> str:
    args: dict = {}
    m = re.search(r"(?:last|pichle|पिछले)\s+(\d+)\s+(?:months?|mahine|महीने)", q, re.I)
    if m:
        args["start_date"] = str((as_of - pd.DateOffset(months=int(m.group(1))) + pd.Timedelta(days=1)).date())
    elif re.search(r"last month|pichle mahine|पिछले महीने", q, re.I):
        end = as_of.replace(day=1) - pd.Timedelta(days=1)
        args = {"start_date": str(end.replace(day=1).date()), "end_date": str(end.date())}
    elif re.search(r"this month|is mahine|इस महीने", q, re.I):
        args["start_date"] = str(as_of.replace(day=1).date())
    ok, s = call("get_financial_summary", args)
    if s.get("status") != "ok":
        return s["message"]
    o = s["other_flows"]
    margin = tr("sum.margin", m=s["estimated_margin_pct"]) if s["estimated_margin_pct"] is not None else ""
    return "\n".join([
        tr("sum.head", period=f"{s['period']['start']} to {s['period']['end']}"),
        tr("sum.rev", amt=_inr(s["revenue"])),
        tr("sum.cost", amt=_inr(s["operating_expenses"])),
        tr("sum.profit", amt=_inr(s["estimated_operating_profit"]), margin=margin),
        tr("sum.net", amt=_inr(s["net_cash_movement"])),
        tr("sum.outside", capex=_inr(o["capex"]), loan=_inr(o["financing_in"]), emi=_inr(o["loan_repayments"]), draw=_inr(o["owner_drawings"]), tax=_inr(o["tax_remitted"])),
    ])


def _records(q: str, call: ToolCaller, as_of) -> str:
    ids = IDS.findall(q)
    ok, r = call("get_supporting_records", {"record_ids": ids})
    if not ok:
        return r["message"]
    lines = []
    for t in r["transactions"]:
        lines.append(tr("rec.txn", id=t["txn_id"], date=t["date"], what=t["description"], party=t["counterparty"], cat=t["category"],
                        dir=tr("in" if t["direction"] == "in" else "out"), amt=_inr(t["amount"])))
    for b in r["invoices_and_bills"]:
        lines.append(tr("rec.obl", id=b["item_id"], kind=b["kind"], party=b["counterparty"], amt=_inr(b["amount"]), date=b["due_date"], status=b["status"]))
    if r["not_found"]:
        lines.append(tr("rec.nf", ids=", ".join(r["not_found"])))
    return "\n".join(lines) or tr("rec.none")


def _action(q: str, call: ToolCaller, as_of) -> str:
    ok, r = call("propose_action", {"action": q.strip()[:120], "reason": "Requested by the user in Ask FinPilot"})
    if not ok or r.get("status") != "awaiting_human_approval":
        return r["message"]
    return tr("act.ok", id=r["approval_id"])


INTENTS: list[tuple[re.Pattern, Callable]] = [
    (re.compile(r"\b(T\d{4}|U\d{5}|E\d{5}|INV-\d{3,}|BILL-[A-Z0-9-]+|SCH-\d{3,}|K-\d{4})\b"), _records),
    (re.compile(r"\b(send|remind|reminder|pay (?:the|this|bill)|file|submit|transfer)\b|याद दिला|भेज", re.I), _action),
    (re.compile(r"\b(afford|buy|purchase|invest in|should (?:i|we) get|kharid\w*|le sakte|le sakta)\b|ख़रीद|खरीद|ले सकता|ले सकते", re.I), _purchase),
    (re.compile(r"\b(forecast|next \d+ days|runway|run out|projection|cash flow|will (?:i|we) have|anuman|agle)\b|अनुमान|अगले", re.I), _forecast),
    (re.compile(r"\b(duplicate|unusual|anomal|suspicious|odd|strange|fraud|double|ajeeb|dohra)\w*|दोहरा|अजीब|असामान्य", re.I), _unusual),
    (re.compile(r"\b(expense|expenses|cost|costs|spend|spending|spent|kharcha|kharch|kharche)\b|खर्च", re.I), _expenses),
    (re.compile(r"\b(overdue|owe|owes|owed|receivable|payable|collect|pending|due|bills|upcoming|udhaar|udhar|baki|baaki)\b|उधार|बाकी|बकाया|देना|लेना", re.I), _owed),
    (re.compile(r"\b(cash|balance|bank|paisa|paise)\b|कैश|बैलेंस|पैसा|पैसे|बैंक", re.I), _cash),
    (re.compile(r"\b(profit\w*|revenue|sales|summary|margin|income|how (?:is|are|was) (?:the |my )?business|performance|munafa|munafe|bikri|dhanda|dhandha)\b|मुनाफ़ा|मुनाफा|बिक्री|कारोबार|धंधा", re.I), _summary),
]

_SPAN = re.compile(r"(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})")
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_HI_M = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
_HI_MS = ["जन", "फ़र", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अग", "सित", "अक्टू", "नव", "दिस"]


def _human_dates(text: str, lang: str = "en") -> str:
    """'2026-09-01 to 2026-09-30' → 'September 2026'; '2026-10-04' → '4 Oct 2026'. Only formatting changes."""

    def span(m):
        a, b = pd.Timestamp(m.group(1)), pd.Timestamp(m.group(2))
        if a.day == 1 and b == a + pd.offsets.MonthEnd(0):
            return f"{_HI_M[a.month - 1]} {a.year}" if lang == "hi" else f"{a:%B %Y}"
        return f"{m.group(1)} {'से' if lang == 'hi' else 'to'} {m.group(2)}"

    text = _SPAN.sub(span, text)

    def one(m):
        d = pd.Timestamp(m.group(0))
        return f"{d.day} {_HI_MS[d.month - 1]} {d.year}" if lang == "hi" else f"{d.day} {d:%b %Y}"

    return _ISO.sub(one, text)


def answer(question: str, call: ToolCaller, as_of: pd.Timestamp, lang: str = "en") -> str:
    _LANG["v"] = "hi" if lang == "hi" else "en"
    for pattern, handler in INTENTS:
        if pattern.search(question):
            return _human_dates(handler(question, call, as_of), _LANG["v"])
    return tr("help")


HELP = P["help"][0]
