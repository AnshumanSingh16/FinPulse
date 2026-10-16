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
    "need_loan": ("**I need a bit more detail to check this loan.** Tell me the interest rate and how many years, from your lender's quote — Munshi doesn't guess loan terms.",
                  "**इस लोन को जाँचने के लिए थोड़ी और जानकारी चाहिए।** लोन देने वाले से मिली ब्याज दर और कितने साल का लोन है, बताइए — Munshi लोन की शर्तें अंदाज़े से नहीं लगाता।"),
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
    "payback": ("- Simple payback: {m:g} months, based on your expected benefit (not verified by Munshi).", "- लागत लगभग {m:g} महीने में निकलेगी — आपके बताए फ़ायदे के आधार पर (Munshi ने इसे जाँचा नहीं)।"),
    "no_benefit": ("- No monthly benefit was given, so the simulation counts only the cost. Tell me what it would save or earn each month to include it.",
                   "- हर महीने का फ़ायदा नहीं बताया, इसलिए सिर्फ़ लागत गिनी गई। जोड़ना हो तो बताइए कि इससे हर महीने कितनी बचत या कमाई होगी।"),
    "interest": ("- Total loan interest over the tenure: {amt}.", "- पूरे लोन पर कुल ब्याज: {amt}।"),
    "sc.note": ("\nScenarios are illustrations under the stated settings, not predictions. Ask me again with different numbers to compare.",
                "\nये अनुमान बताई गई शर्तों पर हैं, भविष्यवाणी नहीं। अलग आंकड़ों के साथ फिर पूछें।"),
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
    "act.ok": ("**Added to your to-dos (#{id}) for your approval.** Nothing has been sent, paid or filed — Munshi can't do that.",
               "**आपकी मंज़ूरी के लिए काम-सूची में जोड़ा (#{id})।** कुछ भेजा, भरा या चुकाया नहीं गया — Munshi ऐसा नहीं करता।"),
    "help": ("I didn't quite catch that. I can help with things like:\n- *What should I do today?*\n- *Who owes me money?* · *Who pays late?* · *How much does Metro owe?*\n"
             "- *Am I making money?* · *How did this week go?* · *What's my health score?*\n- *Is my rent too high?* · *Why did costs go up?* · *Any double payments?*\n"
             "- *Can I raise prices by 5%?* · *Should I hire a helper for ₹15,000?* · *How much GST should I keep aside?*\n"
             "- *Can we afford a ₹12 lakh machine on a loan at 11% for 3 years?*\n- *Add a sale of ₹500 cash* · *Remind Metro Foods* · *Save ₹60,000 for a fridge by March*",
             "मैं ठीक से समझ नहीं पाया। मैं इनमें मदद कर सकता हूँ:\n- *आज मुझे क्या करना चाहिए?*\n- *किस पर उधारी बाकी है?* · *कौन देर से चुकाता है?*\n"
             "- *क्या मैं मुनाफ़ा कमा रहा हूँ?* · *इस हफ़्ते कैसा रहा?* · *मेरा सेहत स्कोर क्या है?*\n- *पिछले महीने खर्च क्यों बढ़ा?* · *कोई दोहरा भुगतान?*\n"
             "- *दाम 5% बढ़ाऊँ तो?* · *₹15,000 पर हेल्पर रखूँ?* · *GST के लिए कितना अलग रखूँ?*\n"
             "- *क्या मैं ₹12 लाख की मशीन 11% पर 3 साल के लोन पर ले सकता हूँ?*\n- *₹500 की नकद बिक्री जोड़ो* · *Metro को याद दिलाओ*"),
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
    ok, r = call("propose_action", {"action": q.strip()[:120], "reason": "Requested by the user in Ask Munshi"})
    if not ok or r.get("status") != "awaiting_human_approval":
        return r["message"]
    return tr("act.ok", id=r["approval_id"])


# ---------------------------------------------------------------- shop handlers (khata, health, week, what-ifs, GST, drafts)

P.update({
    "greet": ("Namaste! 🙏 I'm your Munshi assistant. I look at your own records and tell you what matters. Try:\n"
              "- *What should I do today?*\n- *Who owes me money?*\n- *Who are my best customers?*\n- *Add a sale of ₹500 cash*",
              "नमस्ते! 🙏 मैं आपका Munshi सहायक हूँ। आपके अपने हिसाब से बताता हूँ कि क्या ज़रूरी है। पूछिए:\n"
              "- *आज मुझे क्या करना चाहिए?*\n- *किस पर उधारी बाकी है?*\n- *मेरे सबसे अच्छे ग्राहक कौन हैं?*\n- *₹500 की नकद बिक्री जोड़ो*"),
    "brief.head": ("**Here's what needs you today ({date}):**", "**आज ({date}) आपके ध्यान लायक बातें:**"),
    "brief.collect": ("**Collect from {name}** — {amt} overdue, oldest {days} days late. I've drafted a WhatsApp reminder below for you to check.",
                      "**{name} से वसूली करें** — {amt} बकाया, सबसे पुराना {days} दिन देर से। नीचे WhatsApp याद-संदेश तैयार है, देखकर भेजें।"),
    "brief.collect_more": ("Also overdue: {rest}.", "और बकाया: {rest}।"),
    "brief.bills": ("**Keep {amt} ready** for {n} bill(s) due by {date}.", "**{amt} तैयार रखें** — {date} तक {n} बिल देने हैं।"),
    "brief.bills_overdue": ("**{amt} of supplier bills are already overdue** — pay or call them.", "**सप्लायरों के {amt} के बिल पहले से बकाया हैं** — चुकाएँ या बात करें।"),
    "brief.odd": ("**Check {n} unusual payment(s)** in the last 30 days, e.g. {cat} {amt} on {date} ({id}).", "**{n} असामान्य भुगतान जाँचें** (पिछले 30 दिन), जैसे {cat} {amt}, {date} ({id})।"),
    "brief.health": ("Health score **{score}/100** ({grade}). Weakest area: {weak}.", "सेहत स्कोर **{score}/100** ({grade})। सबसे कमज़ोर: {weak}।"),
    "brief.cash": ("Cash in bank: {cash}.", "बैंक में कैश: {cash}।"),
    "brief.calm": ("Nothing urgent — no overdue dues and no bills this week. 👍", "कुछ ज़रूरी नहीं — न उधारी बकाया, न इस हफ़्ते कोई बिल। 👍"),
    "grade.Excellent": ("Excellent", "बहुत बढ़िया"), "grade.Good": ("Good", "अच्छा"), "grade.Fair": ("Fair", "ठीक-ठाक"), "grade.Needs attention": ("Needs attention", "ध्यान चाहिए"),
    "hs.cash": ("cash cushion", "कैश की गद्दी"), "hs.profit": ("profit margin", "मुनाफ़े का मार्जिन"), "hs.collections": ("collecting dues", "उधारी वसूली"),
    "hs.bills": ("paying bills on time", "समय पर बिल चुकाना"), "hs.momentum": ("sales growth", "बिक्री में बढ़त"),
    "best.head": ("**Your top customers** by money received, {start} to {end}:", "**आपके सबसे अच्छे ग्राहक** (मिले पैसे के हिसाब से), {start} से {end}:"),
    "best.line": ("{i}. **{name}** — {amt}{owes}", "{i}. **{name}** — {amt}{owes}"),
    "best.owes": (" · still owes {amt}", " · अभी {amt} बाकी"),
    "best.total": ("All customers together paid {amt} in this period.", "इस दौरान सभी ग्राहकों से कुल {amt} मिले।"),
    "late.head": ("**Slowest payers** (from their paid bills):", "**सबसे देर से चुकाने वाले** (चुकाए बिलों के आधार पर):"),
    "late.line": ("- **{name}** — {ontime}% on time, {days} days late on average{od}", "- **{name}** — {ontime}% समय पर, औसतन {days} दिन देर{od}"),
    "late.od": ("; {amt} overdue now", "; अभी {amt} बकाया"),
    "late.none": ("Not enough paid bills yet to judge who pays late.", "अभी इतने चुकाए बिल नहीं कि देर से चुकाने वालों का पता चले।"),
    "sup.head": ("**Your suppliers** — you owe {total} in all, {overdue} overdue:", "**आपके सप्लायर** — कुल {total} देने हैं, {overdue} बकाया:"),
    "sup.line": ("- **{name}** — owe {amt}{od}; paid {paid} in the period", "- **{name}** — {amt} देने हैं{od}; इस दौरान {paid} चुकाए"),
    "sup.od": (" ({amt} overdue)", " ({amt} बकाया)"),
    "person.nf": ("I couldn't find one person by that name.{dym}", "उस नाम से कोई एक व्यक्ति नहीं मिला।{dym}"),
    "person.dym": (" Did you mean: {names}?", " क्या आपका मतलब: {names}?"),
    "person.cust": ("**{name}** has paid you {amt} in total ({n} transactions, last on {last}).", "**{name}** ने अब तक कुल {amt} दिए ({n} लेन-देन, आख़िरी {last} को)।"),
    "person.sup": ("**{name}**: you've paid them {amt} in total ({n} transactions, last on {last}).", "**{name}**: आपने कुल {amt} चुकाए ({n} लेन-देन, आख़िरी {last} को)।"),
    "person.owes": ("- Still open: {amt}", "- अभी बाकी: {amt}"),
    "person.item": ("  - {id}: {amt}, due {date}{late}", "  - {id}: {amt}, देय {date}{late}"),
    "person.late": (" ({d} days late)", " ({d} दिन देर)"),
    "person.rel": ("- Payment habit: {label} — {ontime}% of bills on time, {days} days late on average.", "- चुकाने की आदत: {ontime}% बिल समय पर, औसतन {days} दिन देर।"),
    "person.clear": ("- Nothing pending. ✅", "- कुछ बाकी नहीं। ✅"),
    "person.tip": ("\nSay *“remind {name}”* and I'll draft a WhatsApp reminder.", "\n*“{name} को याद दिलाओ”* कहिए, मैं WhatsApp संदेश तैयार कर दूँगा।"),
    "health.head": ("**Your health score is {score}/100 — {grade}.**", "**आपका सेहत स्कोर {score}/100 है — {grade}।**"),
    "health.line": ("- {icon} {label}: {pts:g}/20", "- {icon} {label}: {pts:g}/20"),
    "health.hist": ("Recent months: {hist}.", "पिछले महीने: {hist}।"),
    "health.note": ("\nA summary of your own records — not a credit score.", "\nयह आपके अपने हिसाब का सार है — क्रेडिट स्कोर नहीं।"),
    "week.head": ("**Last 7 days ({a} to {b}): sales {sales}**{vs}", "**पिछले 7 दिन ({a} से {b}): बिक्री {sales}**{vs}"),
    "week.vs": (" (the week before: {prev})", " (उससे पहले के हफ़्ते: {prev})"),
    "week.best": ("- Best day: {day} {date}, {amt}", "- सबसे अच्छा दिन: {date}, {amt}"),
    "week.top": ("- Top customer: {name}, {amt}", "- सबसे बड़ा ग्राहक: {name}, {amt}"),
    "week.spend": ("- Biggest payment: {what} to {party}, {amt} ({id})", "- सबसे बड़ा भुगतान: {what} — {party}, {amt} ({id})"),
    "week.inout": ("- Money in {inn}, money out {out}", "- आया {inn}, गया {out}"),
    "week.udhaar": ("- Udhaar given {given}; dues collected {coll}", "- उधारी दी {given}; वसूली {coll}"),
    "wi.price": ("**Raising prices by {p:g}%** (if you sell the same amount): about {chg} more profit a month — {yr} a year.",
                 "**दाम {p:g}% बढ़ाने पर** (उतनी ही बिक्री रहे तो): हर महीने लगभग {chg} ज़्यादा मुनाफ़ा — साल में {yr}।"),
    "wi.price_vol": ("**Prices {p:g}% and units sold {v:g}%**: profit changes by {chg} a month ({yr} a year).", "**दाम {p:g}% और बिक्री की मात्रा {v:g}%**: मुनाफ़े में हर महीने {chg} का बदलाव (साल में {yr})।"),
    "wi.be": ("- You could sell up to {be:g}% fewer units before the price rise stops paying off.", "- {be:g}% तक कम माल बिके तब भी दाम बढ़ाना फ़ायदे में रहेगा।"),
    "wi.base": ("- Based on your average month ({a} to {b}): sales {sales}, profit {profit}.", "- आपके औसत महीने ({a} से {b}) पर: बिक्री {sales}, मुनाफ़ा {profit}।"),
    "wi.disc": ("**A {d:g}% discount for {w} weeks** with {u:g}% more sales changes profit by {chg} over the offer.", "**{w} हफ़्ते {d:g}% छूट**, {u:g}% ज़्यादा बिक्री के साथ: ऑफ़र में मुनाफ़े पर {chg} का असर।"),
    "wi.disc_need": ("- To break even you'd need about {n:g}% more sales during the offer.", "- बराबरी के लिए ऑफ़र में लगभग {n:g}% ज़्यादा बिक्री चाहिए।"),
    "wi.disc_tip": ("- Tell me how much more you expect to sell (e.g. *“10% discount, 20% more customers”*) for a fuller picture.", "- कितनी ज़्यादा बिक्री की उम्मीद है, बताइए (जैसे *“10% छूट, 20% ज़्यादा ग्राहक”*)।"),
    "wi.hire_need": ("To check a hire I need the monthly salary — e.g. *“Should I hire a helper for ₹15,000 a month?”*", "भर्ती जाँचने के लिए महीने की तनख़्वाह बताइए — जैसे *“₹15,000 महीने पर हेल्पर रखूँ?”*"),
    "wi.hire": ("**Hiring at {sal} a month** changes profit by {chg} a month{extra}.", "**{sal} महीने पर स्टाफ़ रखने से** मुनाफ़े में हर महीने {chg} का बदलाव{extra}।"),
    "wi.hire_extra": (" (with {x} extra sales a month)", " ({x} ज़्यादा महीने की बिक्री के साथ)"),
    "wi.hire_be": ("- They pay for themselves if they bring about {be} of extra sales a month.", "- अगर वे हर महीने लगभग {be} की ज़्यादा बिक्री लाएँ तो ख़र्च निकल जाएगा।"),
    "wi.hire_cash": ("- Lowest bank balance over 6 months: {w} with the hire vs {wo} without.", "- 6 महीने में सबसे कम बैलेंस: भर्ती के साथ {w}, बिना {wo}।"),
    "wi.note": ("\nA what-if on your past averages, not a prediction. Ask again with other numbers to compare.", "\nयह पिछले औसत पर हिसाब है, भविष्यवाणी नहीं। अलग आंकड़ों के साथ फिर पूछें।"),
    "tax.not": ("You've marked the business as not GST-registered, so there's no GST to set aside.", "आपने व्यवसाय को GST में पंजीकृत नहीं बताया है, इसलिए GST अलग रखने की ज़रूरत नहीं।"),
    "tax.head": ("**Set aside about {amt} for GST** for last month ({a} to {b}), at {r:g}% on sales minus {rp:g}% credit on purchases.",
                 "**पिछले महीने ({a} से {b}) के GST के लिए लगभग {amt} अलग रखें** — बिक्री पर {r:g}%, ख़रीद पर {rp:g}% क्रेडिट घटाकर।"),
    "tax.zero": ("**Little or no GST to set aside for last month ({a} to {b})** — estimated payable {amt}: the credit on your purchases ({rp:g}%) covers the GST on sales ({r:g}%).",
                 "**पिछले महीने ({a} से {b}) का GST लगभग नहीं बनता** — अनुमानित {amt}: ख़रीद पर क्रेडिट ({rp:g}%) बिक्री के GST ({r:g}%) को पूरा कर देता है।"),
    "tax.now": ("- This month so far: about {amt}.", "- इस महीने अब तक: लगभग {amt}।"),
    "tax.paid": ("- GST already paid last month: {amt}.", "- पिछले महीने भरा GST: {amt}।"),
    "tax.dates": ("Coming up:", "आने वाली तारीख़ें:"),
    "tax.date": ("- {date}: {what}", "- {date}: {what}"),
    "tax.note": ("\nAn estimate to help you save — not a GST return. Your CA's figures take precedence.", "\nयह बचत के लिए अनुमान है — GST रिटर्न नहीं। आपके CA के आंकड़े ही मान्य हैं।"),
    "bg.head": ("**Budgets this month:** {spent} spent of {limit}.", "**इस महीने का बजट:** {limit} में से {spent} खर्च।"),
    "bg.line": ("- {cat}: {spent} of {limit}{over}", "- {cat}: {limit} में से {spent}{over}"),
    "bg.over": (" — over budget", " — बजट से ज़्यादा"),
    "bg.none": ("You haven't set budgets yet. Based on the last 3 months, a starting point would be:", "अभी बजट तय नहीं है। पिछले 3 महीनों के आधार पर शुरुआत ऐसे कर सकते हैं:"),
    "bg.sugg": ("- {cat}: {amt} a month", "- {cat}: {amt} महीना"),
    "bg.goals": ("**Goals:**", "**लक्ष्य:**"),
    "bg.goal": ("- {name}: {saved} saved of {target}{pm}", "- {name}: {target} में से {saved} जमा{pm}"),
    "bg.pm": (" — save {amt} a month to make it", " — पूरा करने के लिए हर महीने {amt}"),
    "bg.tip": ("\nSay e.g. *“set a rent budget of ₹50,000”* or *“save ₹60,000 for a fridge by March”* and I'll set it up for you to confirm.",
               "\nकहिए, जैसे *“किराये का बजट ₹50,000 रखो”* या *“मार्च तक फ़्रिज के लिए ₹60,000 बचाने हैं”* — मैं तैयार कर दूँगा।"),
    "draft.ready": ("**{summary}** — ready for you to confirm below. Nothing is saved until you tap Confirm.", "**{summary}** — नीचे पुष्टि के लिए तैयार है। Confirm दबाने तक कुछ सेव नहीं होगा।"),
    "draft.settles": ("- It will clear: {items}.", "- इससे चुकता होगा: {items}।"),
    "draft.more": ("- That's {amt} more than they owe; the extra is recorded as received.", "- यह बकाया से {amt} ज़्यादा है; अतिरिक्त राशि जमा मानी जाएगी।"),
    "draft.goal": ("- You'd need to save {amt} a month for {m} month(s).", "- {m} महीने तक हर महीने {amt} बचाने होंगे।"),
    "draft.budget": ("- Spent on {cat} so far this month: {amt}.", "- इस महीने {cat} पर अब तक खर्च: {amt}।"),
    "draft.rem": ("**I've drafted a WhatsApp reminder to {name}** for {amt} overdue. Check it below and tap to open WhatsApp — nothing is sent automatically.",
                  "**{name} के लिए WhatsApp याद-संदेश तैयार है** — {amt} बकाया। नीचे देखें और WhatsApp खोलने के लिए दबाएँ — अपने आप कुछ नहीं भेजा जाता।"),
    "draft.rem_none": ("Nothing from {name} is overdue, so there's nothing to remind them about. 👍", "{name} का कुछ बकाया नहीं, याद दिलाने की ज़रूरत नहीं। 👍"),
    "draft.need_amt": ("How much was it? For example *“sale of ₹500 cash”* or *“received ₹5,000 from Sharma ji”*.", "कितने का था? जैसे *“₹500 की नकद बिक्री”* या *“शर्मा जी से ₹5,000 मिले”*।"),
    "draft.need_party": ("Whose name should this go under? For example *“udhaar ₹2,000 to Ramesh”*.", "किसके नाम पर लिखूँ? जैसे *“रमेश को ₹2,000 उधार”*।"),
    "draft.bad": ("I couldn't prepare that: {msg}", "तैयार नहीं हो सका: {msg}"),
    "goal.need": ("Tell me the amount and what it's for, e.g. *“save ₹60,000 for a fridge by March”*.", "रकम और किसलिए, बताइए — जैसे *“मार्च तक फ़्रिज के लिए ₹60,000”*।"),
    "cat.head": ("**{cat}: {amt} over {a} to {b}** — about {avg} a month{share}.", "**{cat}: {a} से {b} में {amt}** — लगभग {avg} महीना{share}।"),
    "cat.share": (", {p:g}% of your sales", ", आपकी बिक्री का {p:g}%"),
    "cat.change": ("- Last month vs the month before: {dir} {chg}.", "- पिछला महीना उससे पहले वाले के मुकाबले: {chg} {dir}।"),
    "cat.note": ("\nMunshi has no industry benchmarks, so compare this with what similar shops near you pay.", "\nMunshi के पास बाज़ार के मानक नहीं हैं — आस-पास की दुकानों से तुलना करें।"),
    "cat.none": ("No spending found under {cat}.", "{cat} में कोई खर्च नहीं मिला।"),
})

CATEGORY_WORDS = {
    "rent": "Rent", "kiraya": "Rent", "किराया": "Rent", "किराये": "Rent", "salary": "Salaries", "salaries": "Salaries", "wages": "Salaries", "tankhwah": "Salaries",
    "तनख़्वाह": "Salaries", "वेतन": "Salaries", "electricity": "Electricity", "bijli": "Electricity", "बिजली": "Electricity", "power bill": "Electricity",
    "packaging": "Packaging", "marketing": "Marketing", "advertising": "Marketing", "logistics": "Logistics", "transport": "Logistics", "delivery": "Logistics",
    "raw material": "Raw materials", "raw materials": "Raw materials", "stock": "Raw materials", "maal": "Raw materials", "software": "Software",
    "professional fees": "Professional Fees", "ca fees": "Professional Fees",
}


def _cat_in(q: str) -> str | None:
    low = q.lower()
    for w in sorted(CATEGORY_WORDS, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", low):
            return CATEGORY_WORDS[w]
    return None


def _briefing(q: str, call: ToolCaller, as_of) -> str:
    lines = [tr("brief.head", date=str(as_of.date()))]
    todo = []
    ok, ppl = call("get_customers_and_suppliers", {"side": "customers", "sort_by": "overdue", "limit": 3})
    od = [p for p in ppl.get("people", []) if p["overdue"] > 0] if ok and ppl.get("status") == "ok" else []
    if od:
        top = od[0]
        todo.append(tr("brief.collect", name=top["name"], amt=_inr(top["overdue"]), days=top["oldest_days_late"]))
        if len(od) > 1:
            todo[-1] += " " + tr("brief.collect_more", rest=", ".join(f"{p['name']} {_inr(p['overdue'])}" for p in od[1:]))
        call("draft_reminder", {"customer": top["name"]})
    ok, up = call("get_upcoming_payments", {"days": 7})
    if ok and up.get("status") == "ok":
        if up.get("overdue_total"):
            todo.append(tr("brief.bills_overdue", amt=_inr(up["overdue_total"])))
        if up["upcoming"]:
            todo.append(tr("brief.bills", amt=_inr(up["upcoming_total"]), n=len(up["upcoming"]), date=up["upcoming"][-1]["due_date"]))
    ok, odd = call("find_unusual_transactions", {"lookback_days": 30})
    if ok and odd.get("status") == "ok" and odd.get("flags"):
        f = odd["flags"][0]
        todo.append(tr("brief.odd", n=len(odd["flags"]), cat=f["category"], amt=_inr(f["amount"]), date=f["date"], id=", ".join(f["txn_ids"][:2])))
    lines += [f"{i}. {t}" for i, t in enumerate(todo, 1)] or [tr("brief.calm")]
    extra = []
    ok, h = call("get_health_score", {})
    if ok and h.get("status") == "ok":
        weak = min(h["components"], key=lambda c: c["points"])
        extra.append(tr("brief.health", score=h["score"], grade=tr(f"grade.{h['grade']}"), weak=tr(f"hs.{weak['key']}")))
    ok, c = call("get_cash_position", {})
    if ok and c.get("status") == "ok":
        extra.append(tr("brief.cash", cash=_inr(c["cash_balance"])))
    if extra:
        lines.append("\n" + " ".join(extra))
    return "\n".join(lines)


def _greet(q: str, call: ToolCaller, as_of) -> str:
    return tr("greet")


def _side(q: str) -> str:
    return "suppliers" if re.search(r"supplier|vendor|सप्लायर|vyapari", q, re.I) else "customers"


def _best(q: str, call: ToolCaller, as_of) -> str:
    if _side(q) == "suppliers":
        return _suppliers(q, call, as_of)
    ok, r = call("get_customers_and_suppliers", {"side": "customers", "sort_by": "paid", "limit": 5})
    if r.get("status") != "ok":
        return r.get("message", "")
    lines = [tr("best.head", start=r["period"]["start"], end=r["period"]["end"])]
    for i, p in enumerate([p for p in r["people"] if p["paid_in_period"] > 0], 1):
        lines.append(tr("best.line", i=i, name=p["name"], amt=_inr(p["paid_in_period"]), owes=tr("best.owes", amt=_inr(p["outstanding"])) if p["outstanding"] else ""))
    lines.append(tr("best.total", amt=_inr(r["total_paid_in_period"])))
    return "\n".join(lines)


def _late(q: str, call: ToolCaller, as_of) -> str:
    ok, r = call("get_customers_and_suppliers", {"side": _side(q), "sort_by": "late", "limit": 5})
    if r.get("status") != "ok":
        return r.get("message", "")
    rows = [p for p in r["people"] if p["reliability_avg_days_late"] is not None]
    if not rows:
        return tr("late.none")
    lines = [tr("late.head")]
    for p in rows:
        lines.append(tr("late.line", name=p["name"], ontime=p["reliability_on_time_pct"], days=f"{p['reliability_avg_days_late']:g}",
                        od=tr("late.od", amt=_inr(p["overdue"])) if p["overdue"] else ""))
    return "\n".join(lines)


def _suppliers(q: str, call: ToolCaller, as_of) -> str:
    ok, r = call("get_customers_and_suppliers", {"side": "suppliers", "sort_by": "outstanding", "limit": 6})
    if r.get("status") != "ok":
        return r.get("message", "")
    lines = [tr("sup.head", total=_inr(r["total_outstanding"]), overdue=_inr(r["total_overdue"]))]
    for p in r["people"]:
        lines.append(tr("sup.line", name=p["name"], amt=_inr(p["outstanding"]), od=tr("sup.od", amt=_inr(p["overdue"])) if p["overdue"] else "",
                        paid=_inr(p["paid_to_them_in_period"])))
    return "\n".join(lines)


def _person_named(name: str) -> Callable:
    def handler(q: str, call: ToolCaller, as_of) -> str:
        ok, r = call("get_person_details", {"name": name})
        if r.get("status") != "ok":
            dym = tr("person.dym", names=", ".join(r.get("did_you_mean", []))) if r.get("did_you_mean") else ""
            return tr("person.nf", dym=dym)
        last = r["last_date"] or "—"
        if r["type"] == "customer":
            lines = [tr("person.cust", name=r["name"], amt=_inr(r["money_received_from_them"]), n=r["transactions"], last=last)]
        else:
            lines = [tr("person.sup", name=r["name"], amt=_inr(r["money_paid_to_them"]), n=r["transactions"], last=last)]
        if r["open_items"]:
            lines.append(tr("person.owes", amt=_inr(r["outstanding"])))
            for i in r["open_items"][:5]:
                lines.append(tr("person.item", id=i["id"], amt=_inr(i["amount"]), date=i["due_date"], late=tr("person.late", d=i["days_late"]) if i["days_late"] else ""))
        else:
            lines.append(tr("person.clear"))
        if r["reliability_on_time_pct"] is not None:
            lines.append(tr("person.rel", label=r["reliability_label"], ontime=r["reliability_on_time_pct"], days=f"{r['reliability_avg_days_late']:g}"))
        if r["type"] == "customer" and any(i["days_late"] for i in r["open_items"]):
            lines.append(tr("person.tip", name=r["name"].split()[0]))
        return "\n".join(lines)
    return handler


def _health(q: str, call: ToolCaller, as_of) -> str:
    ok, h = call("get_health_score", {})
    if h.get("status") != "ok":
        return h.get("message", "")
    icon = {"good": "🟢", "caution": "🟡", "bad": "🔴", "unknown": "⚪"}
    lines = [tr("health.head", score=h["score"], grade=tr(f"grade.{h['grade']}"))]
    for c in h["components"]:
        lines.append(tr("health.line", icon=icon.get(c["status"], "⚪"), label=tr(f"hs.{c['key']}"), pts=c["points"]))
    if h["history"]:
        lines.append(tr("health.hist", hist=", ".join(f"{x['month']} {x['score']}" for x in h["history"])))
    return "\n".join(lines) + tr("health.note")


def _week(q: str, call: ToolCaller, as_of) -> str:
    ok, w = call("get_weekly_story", {"days": 7})
    if w.get("status") != "ok":
        return w.get("message", "")
    t, p = w["this_period"], w["previous_period"]
    lines = [tr("week.head", a=w["period"][0], b=w["period"][1], sales=_inr(t["sales"]), vs=tr("week.vs", prev=_inr(p["sales"])) if p["sales"] else "")]
    if w["best_day"]:
        lines.append(tr("week.best", day=w["best_day"]["weekday"], date=w["best_day"]["date"], amt=_inr(w["best_day"]["amount"])))
    if w["top_customer"]:
        lines.append(tr("week.top", name=w["top_customer"]["name"], amt=_inr(w["top_customer"]["amount"])))
    if w["biggest_expense"]:
        b = w["biggest_expense"]
        lines.append(tr("week.spend", what=b["what"], party=b["party"], amt=_inr(b["amount"]), id=b["id"]))
    lines.append(tr("week.inout", inn=_inr(t["money_in"]), out=_inr(t["money_out"])))
    if w["udhaar_given"] or w["collected"]:
        lines.append(tr("week.udhaar", given=_inr(w["udhaar_given"]), coll=_inr(w["collected"])))
    return "\n".join(lines)


def _pcts(q: str) -> list[float]:
    return [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s?%", q)]


def _wi_base(r: dict) -> str:
    b = r["baseline"]
    return tr("wi.base", a=b["period"][0], b=b["period"][1], sales=_inr(b["sales"]), profit=_inr(b["profit"]))


def _price(q: str, call: ToolCaller, as_of) -> str:
    ps = _pcts(q)
    price = ps[0] if ps else 5.0
    if re.search(r"\b(lower|reduce|cut|kam|ghata)\w*|घटा|कम कर", q, re.I) and not re.search(r"\b(raise|increase|badha)\w*|बढ़ा", q, re.I):
        price = -abs(price)
    vol = -abs(ps[1]) if len(ps) > 1 and re.search(r"\b(lose|drop|fewer|less|kam)\b|कम", q, re.I) else (ps[1] if len(ps) > 1 else 0.0)
    ok, r = call("run_what_if", {"kind": "price", "price_change_pct": price, "volume_change_pct": vol})
    if r.get("status") != "ok":
        return r.get("message", "")
    if vol:
        lines = [tr("wi.price_vol", p=price, v=vol, chg=_inr(r["monthly_change"]), yr=_inr(r["yearly_change"]))]
    else:
        lines = [tr("wi.price", p=price, chg=_inr(r["monthly_change"]), yr=_inr(r["yearly_change"]))]
    if r.get("breakeven_volume_pct") is not None and price > 0:
        lines.append(tr("wi.be", be=abs(r["breakeven_volume_pct"])))
    lines.append(_wi_base(r))
    return "\n".join(lines) + tr("wi.note")


def _discount(q: str, call: ToolCaller, as_of) -> str:
    ps = _pcts(q)
    d = ps[0] if ps else 10.0
    u = ps[1] if len(ps) > 1 else 0.0
    m = re.search(r"(\d+)\s*(weeks?|hafte|हफ़्ते)", q, re.I)
    weeks = int(m.group(1)) if m else 4
    ok, r = call("run_what_if", {"kind": "discount", "discount_pct": d, "sales_uplift_pct": u, "weeks": weeks})
    if r.get("status") != "ok":
        return r.get("message", "")
    lines = [tr("wi.disc", d=d, w=weeks, u=u, chg=_inr(r["profit_change"]))]
    if r.get("uplift_needed_pct") is not None:
        lines.append(tr("wi.disc_need", n=r["uplift_needed_pct"]))
    if len(ps) < 2:
        lines.append(tr("wi.disc_tip"))
    lines.append(_wi_base(r))
    return "\n".join(lines) + tr("wi.note")


def _hire(q: str, call: ToolCaller, as_of) -> str:
    amounts = _money(q)
    if not amounts:
        m = re.search(r"(\d{4,6})", q)
        amounts = [float(m.group(1))] if m else []
    if not amounts:
        return tr("wi.hire_need")
    args = {"kind": "hire", "monthly_salary": amounts[0]}
    if len(amounts) > 1:
        args["extra_monthly_sales"] = amounts[1]
    ok, r = call("run_what_if", args)
    if r.get("status") != "ok":
        return r.get("message", "")
    lines = [tr("wi.hire", sal=_inr(amounts[0]), chg=_inr(r["monthly_change"]), extra=tr("wi.hire_extra", x=_inr(amounts[1])) if len(amounts) > 1 else "")]
    if r.get("breakeven_sales"):
        lines.append(tr("wi.hire_be", be=_inr(r["breakeven_sales"])))
    if r.get("cash"):
        lines.append(tr("wi.hire_cash", w=_inr(r["cash"]["lowest_with"]), wo=_inr(r["cash"]["lowest_without"])))
    lines.append(_wi_base(r))
    return "\n".join(lines) + tr("wi.note")


def _tax(q: str, call: ToolCaller, as_of) -> str:
    ok, r = call("get_tax_calendar_and_gst", {"days": 45})
    if r.get("status") != "ok":
        return r.get("message", "")
    lines = []
    if not r["gst_registered"]:
        lines.append(tr("tax.not"))
    elif "gst_last_full_month" in r:
        g, c = r["gst_last_full_month"], r["gst_this_month_so_far"]
        key = "tax.head" if g["estimated_payable"] > 0 else "tax.zero"
        lines.append(tr(key, amt=_inr(g["estimated_payable"]), a=g["period"][0], b=g["period"][1], r=r["gst_rate_sales_pct"], rp=r["gst_rate_purchases_pct"]))
        lines.append(tr("tax.now", amt=_inr(c["estimated_payable"])))
        if g["gst_paid_in_period"]:
            lines.append(tr("tax.paid", amt=_inr(g["gst_paid_in_period"])))
    if r["upcoming_due_dates"]:
        lines.append(tr("tax.dates"))
        lines += [tr("tax.date", date=d["date"], what=d["what"]) for d in r["upcoming_due_dates"][:5]]
    return "\n".join(lines) + (tr("tax.note") if r["gst_registered"] else "")


def _draft_reply(r: dict) -> str:
    if r.get("status") != "needs_confirmation":
        return tr("draft.bad", msg=r.get("message", ""))
    lines = [tr("draft.ready", summary=r["summary"])]
    pv = r.get("preview") or {}
    if pv.get("would_settle"):
        lines.append(tr("draft.settles", items=", ".join(f"{s['id']} ({_inr(s['amount'])})" for s in pv["would_settle"])))
    if pv.get("more_than_due"):
        lines.append(tr("draft.more", amt=_inr(pv["more_than_due"])))
    if pv.get("per_month") and pv.get("months_left"):
        lines.append(tr("draft.goal", amt=_inr(pv["per_month"]), m=pv["months_left"]))
    if "spent_this_month" in pv:
        lines.append(tr("draft.budget", cat=r["payload"]["category"], amt=_inr(pv["spent_this_month"])))
    return "\n".join(lines)


def _entry_with(parties: list[str]) -> Callable:
    from finpilot.data.parse_entry import parse as parse_entry

    def handler(q: str, call: ToolCaller, as_of) -> str:
        e = parse_entry(q, as_of, parties)
        if not e["amount"]:
            return tr("draft.need_amt")
        if "party" in e["missing"]:
            return tr("draft.need_party")
        args = {k: e[k] for k in ("kind", "amount", "party", "category", "mode", "date", "due_date") if e.get(k)}
        ok, r = call("draft_entry", args)
        return _draft_reply(r)
    return handler


def _remind_with(parties: list[str]) -> Callable:
    def handler(q: str, call: ToolCaller, as_of) -> str:
        name = _find_party(q, parties)
        if not name:
            ok, ppl = call("get_customers_and_suppliers", {"side": "customers", "sort_by": "overdue", "limit": 3})
            od = [p for p in ppl.get("people", []) if p["overdue"] > 0] if ok else []
            if not od:
                return tr("brief.calm")
            name = od[0]["name"]
        ok, r = call("draft_reminder", {"customer": name})
        if r.get("status") == "needs_confirmation":
            return tr("draft.rem", name=r["payload"]["customer"], amt=_inr(r["preview"]["total"]))
        if r.get("status") == "nothing_overdue":
            return tr("draft.rem_none", name=r["customer"])
        return tr("draft.bad", msg=r.get("message", ""))
    return handler


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _budget_goal(q: str, call: ToolCaller, as_of) -> str:
    amounts = _money(q)
    cat = _cat_in(q)
    if re.search(r"budget|बजट|limit", q, re.I) and amounts and cat:
        ok, r = call("draft_budget", {"category": cat, "monthly_limit": amounts[0]})
        return _draft_reply(r)
    if re.search(r"\b(save|saving|goal|target|bachat|bachana|jama)\b|बचत|बचाने|लक्ष्य", q, re.I) and amounts:
        m = re.search(r"\bfor (?:a |an |the |my |new )?([a-z][a-z ]{1,30}?)(?: by\b| in\b| till\b|[.?!,]|$)", q, re.I)
        name = (m.group(1).strip().capitalize() if m else "My goal")[:60]
        args = {"name": name, "target": amounts[0]}
        dm = re.search(r"\bby\s+([a-z]{3})[a-z]*\s*(\d{4})?", q, re.I)
        if dm and dm.group(1).lower() in _MONTHS:
            mon = _MONTHS[dm.group(1).lower()]
            year = int(dm.group(2)) if dm.group(2) else (as_of.year if mon > as_of.month else as_of.year + 1)
            args["target_date"] = str((pd.Timestamp(year=year, month=mon, day=1) + pd.offsets.MonthEnd(0)).date())
        ok, r = call("draft_goal", args)
        return _draft_reply(r)
    ok, r = call("get_budgets_and_goals", {})
    lines = []
    st = r.get("budget_month")
    if st:
        lines.append(tr("bg.head", spent=_inr(st["total_spent"]), limit=_inr(st["total_limit"])))
        lines += [tr("bg.line", cat=x["category"], spent=_inr(x["spent"]), limit=_inr(x["limit"]), over=tr("bg.over") if x["state"] == "over" else "") for x in st["rows"][:6]]
    elif r.get("suggested_monthly_budgets"):
        lines.append(tr("bg.none"))
        lines += [tr("bg.sugg", cat=c, amt=_inr(v)) for c, v in list(r["suggested_monthly_budgets"].items())[:6]]
    if r.get("goals"):
        lines.append(tr("bg.goals"))
        lines += [tr("bg.goal", name=g["name"], saved=_inr(g["saved"]), target=_inr(g["target"]), pm=tr("bg.pm", amt=_inr(g["per_month"])) if g.get("per_month") and not g["done"] else "")
                  for g in r["goals"][:5]]
    return "\n".join(lines) + tr("bg.tip")


def _category(q: str, call: ToolCaller, as_of) -> str:
    from finpilot.engine.common import last_full_month

    cat = _cat_in(q)
    _, m_end = last_full_month(as_of)
    start = (m_end - pd.DateOffset(months=2)).replace(day=1)
    ok, s = call("get_financial_summary", {"start_date": str(start.date()), "end_date": str(m_end.date())})
    if s.get("status") != "ok":
        return s.get("message", "")
    amt = s["expenses_by_category"].get(cat)
    if not amt:
        return tr("cat.none", cat=cat)
    share = s.get("expense_share_of_sales_pct", {}).get(cat)
    lines = [tr("cat.head", cat=cat, amt=_inr(amt), a=s["period"]["start"], b=s["period"]["end"], avg=_inr(s["expenses_by_category_monthly_average"][cat]),
                share=tr("cat.share", p=share) if share is not None else "")]
    ok, e = call("analyze_expense_changes", {"months": 1})
    if ok and e.get("status") == "ok":
        row = next((c for c in e["by_category"] if c["category"] == cat), None)
        if row and row["change"]:
            lines.append(tr("cat.change", dir=tr("up" if row["change"] > 0 else "down"), chg=_inr(abs(row["change"]))))
    return "\n".join(lines) + tr("cat.note")


# ---------------------------------------------------------------- missions: multi-step goals with a visible plan (check-up, collect, cut costs), memory, promises

P.update({
    "m.ck.cash": ("Check cash and the month ahead", "कैश और आगे का महीना देखना"), "m.ck.owed": ("Check who owes you", "किस पर उधारी है, देखना"),
    "m.ck.bills": ("Check bills due this week", "इस हफ़्ते के बिल देखना"), "m.ck.budget": ("Check budgets and goals", "बजट और लक्ष्य देखना"),
    "m.ck.odd": ("Look for unusual payments", "असामान्य भुगतान खोजना"), "m.ck.review": ("Check bank lines needing a category", "बिना श्रेणी वाली एंट्री देखना"),
    "m.ck.prep": ("Prepare actions for you", "आपके लिए काम तैयार करना"),
    "ck.calm": ("**Namaste 🙏 All calm today** — nothing overdue, no bills this week and nothing unusual.", "**नमस्ते 🙏 आज सब ठीक है** — न उधारी बकाया, न इस हफ़्ते बिल, न कुछ असामान्य।"),
    "ck.head": ("**Namaste 🙏 I've gone through your books. {n} thing(s) need you today:**", "**नमस्ते 🙏 मैंने आपका हिसाब देख लिया। आज {n} काम आपके ध्यान के लिए:**"),
    "ck.cash": ("Cash in bank {cash}{low}.", "बैंक में {cash}{low}।"),
    "ck.low": ("; lowest in the next 30 days {low} on {date}", "; अगले 30 दिन में सबसे कम {low}, {date} को"),
    "ck.collect": ("**Collect {amt} from {name}** — oldest {days} days late.", "**{name} से {amt} वसूलें** — सबसे पुराना {days} दिन देर।"),
    "ck.promise": ("**{name} broke a promise** to pay by {date}.", "**{name} ने {date} तक चुकाने का वादा तोड़ा।**"),
    "ck.bills_od": ("**Pay {amt} of overdue supplier bills.**", "**सप्लायरों के {amt} के बकाया बिल चुकाएँ।**"),
    "ck.bills": ("**Keep {amt} ready** for {n} bill(s) due by {date}.", "**{amt} तैयार रखें** — {date} तक {n} बिल।"),
    "ck.budget": ("**Over budget:** {cats}.", "**बजट से ज़्यादा:** {cats}।"),
    "ck.odd": ("**Check {n} unusual payment(s)**, e.g. {cat} {amt} on {date} ({id}).", "**{n} असामान्य भुगतान जाँचें**, जैसे {cat} {amt}, {date} ({id})।"),
    "ck.review": ("**{n} bank line(s) need a category** — {party} is guessed as {cat}.", "**{n} बैंक एंट्री की श्रेणी तय करनी है** — {party} को {cat} माना गया है।"),
    "ck.prepared": ("\nI've prepared {n} action(s) below — approve the ones you want. Nothing is saved or sent until you do.", "\nनीचे {n} काम तैयार हैं — जो ठीक लगें उन्हें मंज़ूरी दें। आपकी मंज़ूरी के बिना कुछ सेव या भेजा नहीं जाता।"),
    "ck.skipped": ("\nSkipped a reminder to {names} — you asked me not to remind them.", "\n{names} को याद-संदेश नहीं बनाया — आपने मना किया था।"),
    "m.co.find": ("Find who owes you and how late", "किस पर कितनी उधारी और कितनी देर, पता करना"), "m.co.mem": ("Check what you asked me to remember", "आपकी कही बातें देखना"),
    "m.co.draft": ("Draft reminders for the most overdue", "सबसे पुराने बकाया वालों के लिए याद-संदेश बनाना"), "m.co.follow": ("Plan follow-ups", "आगे की योजना"),
    "co.none": ("**Nobody owes you anything overdue right now. 🎉**", "**अभी किसी का कुछ बकाया नहीं है। 🎉**"),
    "co.head": ("**Mission: collect {amt} overdue from {n} customer(s).**", "**मिशन: {n} ग्राहकों से {amt} की बकाया वसूली।**"),
    "co.line": ("- {name}: {amt}, oldest {days} days late{rel}", "- {name}: {amt}, सबसे पुराना {days} दिन देर{rel}"),
    "co.rel": (" · pays on time {p}% of the time", " · {p}% बार समय पर चुकाते हैं"),
    "co.drafted": ("\nI've drafted {n} WhatsApp reminder(s) below — tap each to open WhatsApp and send it yourself.", "\nनीचे {n} WhatsApp याद-संदेश तैयार हैं — हर एक को दबाकर WhatsApp में ख़ुद भेजें।"),
    "co.tip": ("\nWhen someone promises a date, tell me — e.g. *“{name} promised to pay by 25 Oct”* — and I'll track it.", "\nकोई तारीख़ का वादा करे तो बताइए — जैसे *“{name} ने 25 Oct तक देने का वादा किया”* — मैं याद रखूँगा।"),
    "m.cc.look": ("Look at 3 months of costs", "3 महीने का खर्च देखना"), "m.cc.cmp": ("Compare last month with the one before", "पिछले महीने की तुलना"),
    "m.cc.odd": ("Look for unusual or double payments", "असामान्य या दोहरे भुगतान खोजना"), "m.cc.budget": ("Prepare budgets for the biggest costs", "सबसे बड़े खर्चों का बजट तैयार करना"),
    "cc.head": ("**Mission: cut costs.** Your biggest running costs ({a} to {b}), per month:", "**मिशन: खर्च घटाना।** आपके सबसे बड़े खर्च ({a} से {b}), हर महीने:"),
    "cc.line": ("- {cat}: about {avg} a month{share}", "- {cat}: लगभग {avg} महीना{share}"),
    "cc.share": (" ({p:g}% of sales)", " (बिक्री का {p:g}%)"),
    "cc.rise": ("Biggest rise last month: **{cat}**, up {chg}.", "पिछले महीने सबसे ज़्यादा बढ़ा: **{cat}**, {chg}।"),
    "cc.odd": ("{n} payment(s) look unusual or doubled — worth checking (ask *“any double payments?”*).", "{n} भुगतान असामान्य या दोहरे लगते हैं — जाँच लें (पूछें *“कोई दोहरा भुगतान?”*)।"),
    "cc.budgets": ("\nI've prepared monthly budgets for {cats} at your recent average, so they can't creep up unnoticed — I'll tell you in the morning check-up if you go over.", "\n{cats} के लिए आपके हाल के औसत पर महीने का बजट तैयार किया है, ताकि खर्च चुपचाप न बढ़े — ज़्यादा होने पर सुबह के चेक-अप में बताऊँगा।"),
    "cc.has_budgets": ("\nYou already have budgets for your biggest costs — ask me *“how are my budgets?”* any time.", "\nसबसे बड़े खर्चों का बजट पहले से है — कभी भी पूछें *“मेरे बजट कैसे चल रहे हैं?”*"),
    "mem.saved": ("**Got it — I'll remember:** “{fact}”. You can see or delete it in Settings → What Munshi remembers.", "**ठीक है, याद रखूँगा:** “{fact}”। इसे सेटिंग्स → Munshi को क्या याद है, में देख या हटा सकते हैं।"),
    "mem.none": ("I haven't been asked to remember anything yet. Tell me things like *“remember that Ramesh is my brother — never remind him”*.", "अभी कुछ याद रखने को नहीं कहा गया। जैसे कहें *“याद रखना, रमेश मेरा भाई है — उसे याद-संदेश मत भेजना”*।"),
    "mem.head": ("**Here's what you asked me to remember:**", "**आपने ये बातें याद रखने को कहा था:**"),
    "mem.forgot": ("Done — I've forgotten #{id}.", "ठीक है — #{id} भूल गया।"),
    "mem.nf": ("I couldn't find that memory.", "वह बात नहीं मिली।"),
    "prom.need": ("Tell me who promised and by when — e.g. *“Metro Foods promised to pay by 25 Oct”*.", "बताइए किसने और कब तक का वादा किया — जैसे *“Metro Foods ने 25 Oct तक देने का वादा किया”*।"),
})

_NO_REMIND = re.compile(r"(never|don'?t|do not|not to|no)\s+(send\s+\w+\s+)?remind|no reminders?|mat (bhej|yaad)|nahi(n)? (bhej|yaad)|याद.*मत|मत.*याद", re.I)


def _excluded(name: str, memories: list[dict]) -> bool:
    first = name.split()[0].lower()
    return any(first in m["fact"].lower() and _NO_REMIND.search(m["fact"]) for m in memories) if len(first) >= 3 else False


def _plan(call: ToolCaller, keys: list[str], done: int = 0, doing: bool = True) -> None:
    steps = [{"title": tr(k), "status": "done" if i < done else ("doing" if i == done and doing else "todo")} for i, k in enumerate(keys)]
    call("update_plan", {"steps": steps})


def _mission_checkup(q: str, call: ToolCaller, as_of) -> str:
    keys = ["m.ck.cash", "m.ck.owed", "m.ck.bills", "m.ck.budget", "m.ck.odd", "m.ck.review", "m.ck.prep"]
    _plan(call, keys, 0)
    todo, drafted, skipped = [], 0, []
    ok, c = call("get_cash_position", {})
    cash_line = ""
    if ok and c.get("status") == "ok":
        ok2, f = call("forecast_cash_flow", {"horizon_days": 30})
        low = tr("ck.low", low=_inr(f["lowest_balance"]), date=f["lowest_balance_date"]) if ok2 and f.get("status") == "ok" else ""
        cash_line = tr("ck.cash", cash=_inr(c["cash_balance"]), low=low)
    ok, h = call("get_health_score", {})
    if ok and h.get("status") == "ok":
        weak = min(h["components"], key=lambda x: x["points"])
        cash_line += " " + tr("brief.health", score=h["score"], grade=tr(f"grade.{h['grade']}"), weak=tr(f"hs.{weak['key']}"))
    _plan(call, keys, 1)
    ok, ppl = call("get_customers_and_suppliers", {"side": "customers", "sort_by": "overdue", "limit": 5})
    ok_m, mem = call("recall_memory", {})
    memories = mem.get("memories", []) if ok_m else []
    od = [p for p in ppl.get("people", []) if p["overdue"] > 0] if ok and ppl.get("status") == "ok" else []
    for p in od[:2]:
        todo.append(tr("ck.collect", amt=_inr(p["overdue"]), name=p["name"], days=p["oldest_days_late"]))
        if _excluded(p["name"], memories):
            skipped.append(p["name"])
            continue
        ok_r, r = call("draft_reminder", {"customer": p["name"]})
        drafted += r.get("status") == "needs_confirmation"
    for p in ppl.get("people", []) if ok else []:
        if p.get("promise") and p["promise"].get("broken"):
            todo.append(tr("ck.promise", name=p["name"], date=p["promise"]["date"]))
    _plan(call, keys, 2)
    ok, up = call("get_upcoming_payments", {"days": 7})
    if ok and up.get("status") == "ok":
        if up.get("overdue_total"):
            todo.append(tr("ck.bills_od", amt=_inr(up["overdue_total"])))
        if up["upcoming"]:
            todo.append(tr("ck.bills", amt=_inr(up["upcoming_total"]), n=len(up["upcoming"]), date=up["upcoming"][-1]["due_date"]))
    _plan(call, keys, 3)
    ok, bg = call("get_budgets_and_goals", {})
    if ok and bg.get("budget_month") and bg["budget_month"].get("over"):
        todo.append(tr("ck.budget", cats=", ".join(bg["budget_month"]["over"])))
    _plan(call, keys, 4)
    ok, odd = call("find_unusual_transactions", {"lookback_days": 30})
    if ok and odd.get("status") == "ok" and odd.get("flags"):
        f = odd["flags"][0]
        todo.append(tr("ck.odd", n=len(odd["flags"]), cat=f["category"], amt=_inr(f["amount"]), date=f["date"], id=", ".join(f["txn_ids"][:2])))
    _plan(call, keys, 5)
    ok, rq = call("get_review_queue", {})
    if ok and rq.get("lines_to_review"):
        g = next((g for g in rq["groups"] if g["is_guess"]), rq["groups"][0])
        todo.append(tr("ck.review", n=rq["lines_to_review"], party=g["party"], cat=g["current_category"]))
        if g["is_guess"] and g["current_category"] not in ("Uncategorised", "Unknown"):
            ok_d, r = call("draft_recategorise", {"party": g["party"], "category": g["current_category"]})
            drafted += r.get("status") == "needs_confirmation"
    _plan(call, keys, len(keys), doing=False)
    lines = [tr("ck.head", n=len(todo)) if todo else tr("ck.calm")]
    lines += [f"{i}. {t}" for i, t in enumerate(todo, 1)]
    if cash_line:
        lines.append("\n" + cash_line)
    if drafted:
        lines.append(tr("ck.prepared", n=drafted))
    if skipped:
        lines.append(tr("ck.skipped", names=", ".join(skipped)))
    return "\n".join(lines)


def _mission_collect(q: str, call: ToolCaller, as_of) -> str:
    keys = ["m.co.find", "m.co.mem", "m.co.draft", "m.co.follow"]
    _plan(call, keys, 0)
    ok, ppl = call("get_customers_and_suppliers", {"side": "customers", "sort_by": "overdue", "limit": 8})
    od = [p for p in ppl.get("people", []) if p["overdue"] > 0] if ok and ppl.get("status") == "ok" else []
    _plan(call, keys, 1)
    ok_m, mem = call("recall_memory", {})
    memories = mem.get("memories", []) if ok_m else []
    if not od:
        _plan(call, keys, len(keys), doing=False)
        return tr("co.none")
    _plan(call, keys, 2)
    lines = [tr("co.head", amt=_inr(ppl["total_overdue"]), n=len(od))]
    drafted, skipped = 0, []
    for p in od:
        rel = tr("co.rel", p=p["reliability_on_time_pct"]) if p.get("reliability_on_time_pct") is not None else ""
        lines.append(tr("co.line", name=p["name"], amt=_inr(p["overdue"]), days=p["oldest_days_late"], rel=rel))
    for p in od:
        if drafted >= 3:
            break
        if _excluded(p["name"], memories):
            skipped.append(p["name"])
            continue
        ok_r, r = call("draft_reminder", {"customer": p["name"]})
        drafted += r.get("status") == "needs_confirmation"
    _plan(call, keys, 3)
    broken = [p for p in od if p.get("promise") and p["promise"].get("broken")]
    for p in broken:
        lines.append("\n" + tr("ck.promise", name=p["name"], date=p["promise"]["date"]))
    _plan(call, keys, len(keys), doing=False)
    if drafted:
        lines.append(tr("co.drafted", n=drafted))
    if skipped:
        lines.append(tr("ck.skipped", names=", ".join(skipped)))
    lines.append(tr("co.tip", name=od[0]["name"].split()[0]))
    return "\n".join(lines)


def _mission_costs(q: str, call: ToolCaller, as_of) -> str:
    from finpilot.engine.common import last_full_month

    keys = ["m.cc.look", "m.cc.cmp", "m.cc.odd", "m.cc.budget"]
    _plan(call, keys, 0)
    _, m_end = last_full_month(as_of)
    start = (m_end - pd.DateOffset(months=2)).replace(day=1)
    ok, s = call("get_financial_summary", {"start_date": str(start.date()), "end_date": str(m_end.date())})
    if s.get("status") != "ok":
        return s.get("message", "")
    avg = s["expenses_by_category_monthly_average"]
    top = sorted(avg, key=lambda c: -avg[c])[:4]
    lines = [tr("cc.head", a=s["period"]["start"], b=s["period"]["end"])]
    share = s.get("expense_share_of_sales_pct", {})
    lines += [tr("cc.line", cat=c, avg=_inr(avg[c]), share=tr("cc.share", p=share[c]) if c in share else "") for c in top]
    _plan(call, keys, 1)
    ok, e = call("analyze_expense_changes", {"months": 1})
    if ok and e.get("status") == "ok":
        ups = [c for c in e["by_category"] if c["change"] > 0]
        if ups:
            u = max(ups, key=lambda c: c["change"])
            lines.append("\n" + tr("cc.rise", cat=u["category"], chg=_inr(u["change"])))
    _plan(call, keys, 2)
    ok, odd = call("find_unusual_transactions", {"lookback_days": 90})
    if ok and odd.get("status") == "ok" and odd.get("flags"):
        lines.append(("" if any(x.startswith("\n") for x in lines[1:]) else "\n") + tr("cc.odd", n=len(odd["flags"])))
    _plan(call, keys, 3)
    ok, bg = call("get_budgets_and_goals", {})
    have = set((bg.get("budget_month") or {}).get("rows") and [r["category"] for r in bg["budget_month"]["rows"]] or [])
    sugg = bg.get("suggested_monthly_budgets", {}) if ok else {}
    picked = [c for c in top if c in sugg and c not in have][:2]
    for c in picked:
        call("draft_budget", {"category": c, "monthly_limit": sugg[c]})
    _plan(call, keys, len(keys), doing=False)
    lines.append(tr("cc.budgets", cats=" & ".join(picked)) if picked else tr("cc.has_budgets"))
    return "\n".join(lines)


_REMEMBER = re.compile(r"^\s*(?:please\s+)?(?:remember|yaad rakh\w*|dhyan rakh\w*|याद रखना|याद रखो)\s*(?:that|ki|कि)?\s*[:,-]?\s*(.+)$", re.I)


def _remember(q: str, call: ToolCaller, as_of) -> str:
    m = _REMEMBER.match(q)
    fact = (m.group(1) if m else q).strip().rstrip(".")
    ok, r = call("remember", {"fact": fact[:300]})
    return tr("mem.saved", fact=fact) if r.get("status") == "remembered" else r.get("message", "")


def _recall(q: str, call: ToolCaller, as_of) -> str:
    ok, r = call("recall_memory", {})
    mem = r.get("memories", [])
    if not mem:
        return tr("mem.none")
    return "\n".join([tr("mem.head")] + [f"- #{m['id']}: {m['fact']}" for m in mem])


def _forget(q: str, call: ToolCaller, as_of) -> str:
    m = re.search(r"#?(\d+)", q)
    if not m:
        return _recall(q, call, as_of)
    ok, r = call("forget", {"id": int(m.group(1))})
    return tr("mem.forgot", id=m.group(1)) if r.get("status") == "forgotten" else tr("mem.nf")


_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"


def _promise_with(parties: list[str]) -> Callable:
    def handler(q: str, call: ToolCaller, as_of) -> str:
        name = _find_party(q, parties)
        m = re.search(rf"(\d{{1,2}})\s*{_MON}|{_MON}\s*(\d{{1,2}})", q, re.I)
        if not name or not m:
            return tr("prom.need")
        day = int(m.group(1) or m.group(4))
        mon = (m.group(2) or m.group(3))[:3].lower()
        d = pd.Timestamp(f"{day} {mon} {as_of.year}")
        if d < as_of:
            d = d.replace(year=as_of.year + 1)
        args = {"customer": name, "date": str(d.date())}
        amounts = _money(q)
        if amounts:
            args["amount"] = amounts[0]
        ok, r = call("draft_promise", args)
        return _draft_reply(r)
    return handler


_GENERIC = {"traders", "trader", "enterprises", "foods", "pvt", "ltd", "retail", "store", "stores", "shop", "suppliers", "supplier", "agro", "wholesale",
            "and", "the", "india", "services", "company", "co", "mart", "customer", "walk-in", "bank", "sharma", "kumar"}


def _find_party(q: str, parties: list[str]) -> str | None:
    """A known customer/supplier named in the question: full name, or a distinctive first word (e.g. 'Metro')."""
    low = q.lower()
    full = [p for p in parties if p.lower() in low]
    if full:
        return max(full, key=len)
    hits = []
    for p in parties:
        words = [w for w in re.findall(r"[a-z]+", p.lower()) if len(w) >= 4 and w not in _GENERIC]
        if words and re.search(rf"\b{re.escape(words[0])}\b", low):
            hits.append(p)
    return hits[0] if len(hits) == 1 else None


_Q_START = re.compile(r"^\s*(how|what|why|when|which|who|whom|is|are|was|were|can|could|should|do|does|did|will|kya|kitna|kitne|kab|kaun|kaise|क्या|कितना|कितने|कौन|कैसे)\b", re.I)
_ENTRY_VERB = re.compile(r"\b(add|record|enter|note|log|likh\w*|daal\w*|jod\w*|darj)\b|जोड़|लिख|दर्ज", re.I)
_ENTRY_KIND = re.compile(r"^\s*(sold|sale of|received|got|collected|paid|spent|bought|udhaar|udhar|gave|diya|diye|mila|mile|becha|bechi)\b"
                         r"|\b(becha|bechi|beche|bika|udhaar|udhar|chukaya|chukaye|kharcha kiya|jama kiya|bheje|mile|mila)\b|बेचा|उधार दिया|चुकाया|मिले|मिला", re.I)
EXCLUSIVE = {"records", "entry", "remind", "action", "purchase", "briefing", "greet", "price", "discount", "hire", "budget_goal",
             "checkup", "collect", "costs", "remember", "recall", "forget", "promise"}

BASE_INTENTS: list[tuple[str, re.Pattern, Callable | None]] = [
    ("records", re.compile(r"\b(T\d{4}|U\d{5}|E\d{5}|INV-\d{3,}|BILL-[A-Z0-9-]+|SCH-\d{3,}|K-\d{4})\b"), _records),
    ("greet", re.compile(r"^\s*(hi+|hello|hey|namaste|namaskar|good (?:morning|evening|afternoon)|thanks?|thank you|shukriya|dhanyavad|नमस्ते|नमस्कार|धन्यवाद|शुक्रिया)\b[\s!.?🙏]*\w{0,12}[\s!.?]*$", re.I), _greet),
    ("remember", re.compile(r"^\s*(?:please\s+)?(?:remember|yaad rakh\w*|dhyan rakh\w*)\b|^\s*याद रख|\b(never|don'?t|do not)\s+(send\s+\w+\s+)?remind\b", re.I), _remember),
    ("recall", re.compile(r"what do you (remember|know about (me|my (shop|business)))|(show|list)( me)? (your )?memor(y|ies)|kya yaad hai|क्या याद है", re.I), _recall),
    ("forget", re.compile(r"^\s*(forget|bhool ja\w*|भूल जाओ)\b", re.I), _forget),
    ("entry", re.compile(r"$^"), None),  # decided in code, see answer()
    ("promise", re.compile(r"\b(promised?|will pay (by|on)|vaada|wada|वादा)\b", re.I), None),
    ("checkup", re.compile(r"\b(check-?up|daily check|autopilot|scan my (shop|business|books))\b|चेक-?अप", re.I), _mission_checkup),
    ("collect", re.compile(r"\b(collect|recover|chase|get back)\b.{0,25}\b(money|dues|payments?|udhaa?r|paisa|everyone|all)\b|\bremind (all|everyone|everybody|sab\w*)\b|\b(vasool\w*|wasool\w*|vasuli|wasuli)\b|वसूल", re.I), _mission_collect),
    ("costs", re.compile(r"\b(cut|reduce|lower|control|bring down|save on)\b.{0,15}\b(costs?|expenses?|spending|kharch\w*)\b|kharch\w* kam|खर्च कम", re.I), _mission_costs),
    ("remind", re.compile(r"\b(remind|reminder|yaad dila\w*|whatsapp)\b|याद दिला", re.I), None),
    ("action", re.compile(r"\b(send|pay (?:the|this|bill)|file|submit|transfer)\b|भेज", re.I), _action),
    ("purchase", re.compile(r"\b(afford|buy|purchase|invest in|should (?:i|we) get|kharid\w*|le sakte|le sakta)\b|ख़रीद|खरीद|ले सकता|ले सकते", re.I), _purchase),
    ("budget_goal", re.compile(r"\b(budget|goal|savings? (?:goal|target)|save (?:₹|rs|up|for|\d)|bachat|lakshya)\b|बजट|लक्ष्य|बचत|बचाने", re.I), _budget_goal),
    ("price", re.compile(r"\b(raise|increase|hike|lower|reduce|cut)\b.{0,20}\b(price|prices|rate|rates)\b|\bprice (?:rise|hike|increase)|\b(daam|dam|keemat|kimat)\b|दाम|कीमत", re.I), _price),
    ("discount", re.compile(r"\b(discount|offer|chhoot|chhut)\b|छूट|ऑफ़र", re.I), _discount),
    ("hire", re.compile(r"\b(hire|hiring|helper|employee|worker|staff|naukar|karigar|rakh\w*)\b|कर्मचारी|हेल्पर|रखूँ|रखना", re.I), _hire),
    ("briefing", re.compile(r"\b(what should (?:i|we) (?:do|focus)|to ?do today|today'?s? (?:plan|tasks?|priorit\w*)|priorit\w*|what needs|anything (?:urgent|important)|brief\w*|aaj kya|kya karu\w*|kya karna)\b|आज क्या|क्या करूँ|क्या करना", re.I), _mission_checkup),
    ("forecast", re.compile(r"\b(forecast|next \d+ days|runway|run out|projection|cash flow|will (?:i|we) have|anuman|agle)\b|अनुमान|अगले", re.I), _forecast),
    ("health", re.compile(r"\b(health|score|sehat|rating|how healthy)\b|सेहत|स्कोर", re.I), _health),
    ("week", re.compile(r"\b(this week|last week|past week|last 7 days|weekly|week|hafte|hafta)\b|हफ़्ते|हफ्ते|सप्ताह", re.I), _week),
    ("tax", re.compile(r"\b(gst|tds|tax|taxes|return|filing|itr)\b|जीएसटी|टैक्स", re.I), _tax),
    ("best", re.compile(r"\b(best|top|biggest|largest|most valuable|loyal|regular)\b.{0,15}\b(customers?|clients?|buyers?|grahak)\b|\bwho buys? (?:the )?most\b|सबसे अच्छे ग्राहक|बड़े ग्राहक|grahak", re.I), _best),
    ("late", re.compile(r"\b(pays?|paying|payers?)\b.{0,12}\b(late|slow|delay\w*)\b|\b(late|slow)\s+payers?\b|der se|देर से", re.I), _late),
    ("suppliers", re.compile(r"\b(suppliers?|vendors?)\b|सप्लायर", re.I), _suppliers),
    ("unusual", re.compile(r"\b(duplicate|unusual|anomal|suspicious|odd|strange|fraud|double|ajeeb|dohra)\w*|दोहरा|अजीब|असामान्य", re.I), _unusual),
    ("category", re.compile(r"$^"), _category),  # decided in code
    ("expenses", re.compile(r"\b(expense|expenses|cost|costs|spend|spending|spent|kharcha|kharch|kharche)\b|खर्च", re.I), _expenses),
    ("owed", re.compile(r"\b(overdue|owe|owes|owed|receivable|payable|collect|pending|due|bills|upcoming|udhaar|udhar|baki|baaki)\b|उधार|बाकी|बकाया|देना|लेना", re.I), _owed),
    ("cash", re.compile(r"\b(cash|balance|bank|paisa|paise)\b|कैश|बैलेंस|पैसा|पैसे|बैंक", re.I), _cash),
    ("summary", re.compile(r"\b(profit\w*|revenue|sales|summary|margin|income|making money|earn\w*|kamai|kama|how (?:is|are|was) (?:the |my )?(?:business|shop|dukaan)|performance|munafa|munafe|bikri|dhanda|dhandha)\b|मुनाफ़ा|मुनाफा|बिक्री|कारोबार|धंधा|कमाई", re.I), _summary),
]
INTENTS = [(p, h) for _, p, h in BASE_INTENTS if h is not None]  # kept for older callers


def _entry_amount(q: str) -> float | None:
    from finpilot.data.parse_entry import parse as parse_entry

    return parse_entry(q, pd.Timestamp.today())["amount"]


def plan(question: str, parties: list[str] | None = None) -> list[tuple[str, Callable]]:
    """Which handlers answer this question, in order. Exclusive intents (actions, simulations) stand alone; up to three read-only ones combine."""
    parties = parties or []
    q = question.strip()
    is_question = q.endswith("?") or bool(_Q_START.match(q))
    found: list[tuple[str, Callable]] = []
    person = _find_party(q, parties)
    for key, pat, handler in BASE_INTENTS:
        if key == "entry":
            if _entry_amount(q) and not is_question and (_ENTRY_VERB.search(q) or _ENTRY_KIND.search(q)) and not re.search(r"budget|goal|बजट|लक्ष्य", q, re.I):
                found.append((key, _entry_with(parties)))
            continue
        if key == "category":
            if _cat_in(q) and not re.search(r"budget|बजट", q, re.I) and re.search(r"\b(too|high|much|kitna|zyada|jyada|spend|spent|paying|pay)\b|ज़्यादा|ज्यादा|कितना", q, re.I):
                found.append((key, _category))
            continue
        if key == "remind":
            if pat.search(q) and not _REMEMBER.match(q):
                found.append((key, _remind_with(parties)))
            continue
        if key == "promise":
            if pat.search(q) and not is_question:
                found.append((key, _promise_with(parties)))
            continue
        if pat.search(q):
            found.append((key, handler))
    if person and not any(k in EXCLUSIVE for k, _ in found):
        found.insert(0, ("person", _person_named(person)))
    for k, h in found:
        if k in EXCLUSIVE:
            return [(k, h)]
    out, seen = [], set()
    for k, h in found:
        if k in seen:
            continue
        if k == "owed" and "person" in seen:  # "how much does Metro owe" is about that person
            continue
        if k == "expenses" and "category" in seen:
            continue
        seen.add(k)
        out.append((k, h))
    return out[:3]


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


def answer(question: str, call: ToolCaller, as_of: pd.Timestamp, lang: str = "en", parties: list[str] | None = None) -> str:
    _LANG["v"] = "hi" if lang == "hi" else "en"
    steps = plan(question, parties)
    if not steps:
        return tr("help")
    parts = [handler(question, call, as_of) for _, handler in steps]
    return _human_dates("\n\n".join(p for p in parts if p), _LANG["v"])


HELP = P["help"][0]
