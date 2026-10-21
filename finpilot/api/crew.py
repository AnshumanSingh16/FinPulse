"""
The agent crew, in words: what each agent found, from the cash autopilot's numbers (never new numbers), in English or Hindi.
Also the "what changed" feed: a small picture of the plan is kept per book, and the next look is compared with it.
"""

from __future__ import annotations

from .views import day, short

AGENTS = {
    "forecaster": ("Forecaster", "पूर्वानुमान एजेंट"),
    "risk": ("Risk analyst", "जोखिम विश्लेषक"),
    "collections": ("Collections agent", "वसूली एजेंट"),
    "payables": ("Payables agent", "भुगतान एजेंट"),
    "spending": ("Spending agent", "खर्च एजेंट"),
    "tax": ("Tax agent", "टैक्स एजेंट"),
    "planner": ("Planner", "योजनाकार"),
    "financing": ("Financing agent", "फ़ाइनेंस एजेंट"),
    "auditor": ("Auditor", "ऑडिटर"),
}

DOING = {
    "forecaster": ("Reading every upcoming bill and invoice…", "आने वाले सारे बिल और इनवॉइस पढ़ रहा हूँ…"),
    "risk": ("Playing out 1,000 possible futures…", "1,000 संभावित भविष्य चला रहा हूँ…"),
    "collections": ("Checking who owes you…", "देख रहा हूँ किस पर पैसा बाकी है…"),
    "payables": ("Looking for bills that could move…", "आगे बढ़ सकने वाले बिल ढूँढ रहा हूँ…"),
    "spending": ("Looking for spending that can wait…", "रुक सकने वाले खर्च ढूँढ रहा हूँ…"),
    "tax": ("Checking upcoming GST…", "आने वाला GST देख रहा हूँ…"),
    "planner": ("Comparing every combination…", "हर मेल की तुलना कर रहा हूँ…"),
    "financing": ("Sizing a backup…", "बैकअप का आकार तय कर रहा हूँ…"),
    "auditor": ("Re-running the forecast to check the plan…", "योजना जाँचने के लिए अनुमान दोबारा चला रहा हूँ…"),
}


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _l(lang: str, en: str, hi: str, **kw) -> str:
    return (hi if lang == "hi" else en).format(**kw)


def name(agent: str, lang: str) -> str:
    return AGENTS[agent][1 if lang == "hi" else 0]


def doing(agent: str, lang: str) -> str:
    return DOING[agent][1 if lang == "hi" else 0]


def move_title(m: dict, lang: str) -> str:
    k = m["kind"]
    if k == "collect":
        return _l(lang, "collect {amt} from {who}", "{who} से {amt} वसूलें", amt=short(m["amount"]), who=m["party"])
    if k == "defer":
        return _l(lang, "ask {who} to move a {amt} bill to {d}", "{who} से {amt} का बिल {d} तक बढ़वाएँ", who=m["party"], amt=short(m["amount"]), d=day(m["to_date"], lang))
    if k == "pause":
        return _l(lang, "pause {w} for 60 days", "60 दिन {w} रोकें", w=_what(m, lang))
    if k == "reserve":
        return _l(lang, "set aside {amt} for GST", "GST के लिए {amt} अलग रखें", amt=short(m["amount"]))
    if k == "borrow":
        return _l(lang, "keep a {amt} overdraft ready", "{amt} का ओवरड्राफ़्ट तैयार रखें", amt=short(m["amount"]))
    return m["title"]


def _what(m: dict, lang: str) -> str:
    w = {"Owner Drawings": ("owner drawings", "मालिक की निकासी"), "Marketing": ("marketing", "मार्केटिंग")}.get(m["party"], (m["party"], m["party"]))
    return w[1 if lang == "hi" else 0]


def _join(items: list[str], lang: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + (" और " if lang == "hi" else " and ") + items[-1]


def headline(p: dict, lang: str) -> str:
    b = p["baseline"]
    if b["runs_out"]:
        return _l(lang, "If nothing changes, cash runs out on {d} — {n} days from now.", "कुछ न बदला तो {d} को कैश खत्म — आज से {n} दिन में।",
                  d=day(b["runs_out"], lang), n=b["days_to_trouble"])
    if not b["safe"]:
        return _l(lang, "Cash drops below your cushion of {s} on {d} — {n} days from now.", "{d} को कैश आपके कुशन {s} से नीचे जाएगा — आज से {n} दिन में।",
                  s=short(p["safety"]), d=day(b["below_safety_from"], lang), n=b["days_to_trouble"])
    return _l(lang, "You stay above your cushion of {s} for the next 90 days. Tightest day: {d}, at {low}.",
              "अगले 90 दिन आप अपने कुशन {s} से ऊपर रहेंगे। सबसे तंग दिन: {d}, {low}।", s=short(p["safety"]), d=day(b["lowest_date"], lang), low=short(b["lowest"]))


def steps(p: dict, lang: str = "en") -> list[dict]:
    """One finding per agent, in order. `p` is the autopilot view (moves carry their state)."""
    moves = [m for m in p["moves"] if m.get("state") != "dismissed"]
    by = lambda k: [m for m in moves if m["kind"] == k]  # noqa: E731
    o = p["odds"]
    out = []

    def add(agent, text, tone="info", **data):
        out.append({"agent": agent, "name": name(agent, lang), "doing": doing(agent, lang), "text": text, "tone": tone, **data})

    b = p["baseline"]
    t = _l(lang, "Read {n} upcoming bills and invoices plus your usual day-to-day sales and costs. ", "{n} आने वाले बिल-इनवॉइस और आपकी रोज़ की आम बिक्री-खर्च पढ़े। ", n=p["known_items"])
    t += headline(p, lang)
    for r in p["at_risk"]:
        t += _l(lang, " Not counting {amt} from {who} — already {d} days late.", " {who} के {amt} नहीं गिने — पहले से {d} दिन लेट।", amt=short(r["amount"]), who=r["party"], d=r["oldest_late_days"])
    add("forecaster", t, "bad" if b["runs_out"] else "caution" if not b["safe"] else "good")

    ob = o["baseline"]
    t = _l(lang, "Played out {n:,} possible futures, using how each customer has actually paid before. If nothing changes, you stay above your cushion in {s} of them",
           "{n:,} संभावित भविष्य चलाए — हर ग्राहक पहले कैसे भुगतान करता रहा, उसके आधार पर। कुछ न बदला तो {s} में आप कुशन से ऊपर रहते हैं", n=ob["sims"], s=_pct(ob["p_safe"]))
    t += _l(lang, " and run out of cash in {r}.", " और {r} में कैश खत्म हो जाता है।", r=_pct(ob["p_short"])) if ob["p_short"] > 0 else "."
    t += _l(lang, " In a bad case (1 in 10), your tightest day is {x}.", " बुरी स्थिति में (10 में 1), सबसे तंग दिन {x} रहेगा।", x=short(ob["bad_case_lowest"]))
    add("risk", t, "good" if ob["p_safe"] >= o["target"] else "bad" if ob["p_short"] >= 0.2 else "caution")

    c = by("collect")
    if c:
        parts = [_l(lang, "{who} owes {amt}, {d} day{s} late", "{who} पर {amt} बाकी, {d} दिन लेट", who=m["party"], amt=short(m["amount"]), d=m["days_late"],
                    s="" if m["days_late"] == 1 else "s") for m in c[:3]]
        add("collections", _join(parts, lang) + _l(lang, ". WhatsApp reminders are ready.", "। WhatsApp याद-संदेश तैयार हैं।"), "info")
    else:
        add("collections", _l(lang, "Nobody owes you overdue money right now.", "अभी किसी पर बकाया पैसा नहीं है।"), "good")

    d = by("defer")
    if d:
        parts = [_l(lang, "{who}'s {amt} bill on {f} could move to {to}", "{who} का {amt} का बिल {f} से {to} तक बढ़ सकता है", who=m["party"], amt=short(m["amount"]),
                    f=day(m["from_date"], lang), to=day(m["to_date"], lang)) for m in d[:3]]
        add("payables", _join(parts, lang) + ".", "info")
    else:
        add("payables", _l(lang, "No supplier bill is worth moving before the tight days.", "तंग दिनों से पहले कोई सप्लायर बिल बढ़वाने लायक नहीं।"), "info")

    sp = by("pause")
    if sp:
        parts = [_l(lang, "{w} (about {m} a month)", "{w} (लगभग {m} महीना)", w=_what(m, lang), m=short(m["monthly"])) for m in sp]
        t = _join(parts, lang)
        add("spending", t[:1].upper() + t[1:] + _l(lang, " could wait for 60 days.", " 60 दिन रुक सकते हैं।"), "info")
    else:
        add("spending", _l(lang, "No optional spending big enough to matter.", "कोई ऐसा वैकल्पिक खर्च नहीं जो फ़र्क डाले।"), "info")

    tx = by("reserve")
    if tx:
        m = tx[0]
        add("tax", _l(lang, "GST due {d}: about {amt}. I'll keep it aside so it isn't spent by mistake.", "{d} को GST: लगभग {amt}। इसे अलग रखूँगा ताकि गलती से खर्च न हो।",
                      d=day(m["due"], lang), amt=short(m["amount"])), "info")
    else:
        add("tax", _l(lang, "No regular GST payment found in your records.", "आपके रिकॉर्ड में नियमित GST भुगतान नहीं मिला।"), "info")

    sr = p["search"]
    sug = [m for m in moves if m["suggested"] and m["kind"] != "reserve"]
    os_ = o["suggested"]
    t = _l(lang, "Scored all {c} combinations of these moves and stress-tested {k} of them in {n:,} futures each. ", "इन कदमों के सभी {c} मेल जाँचे और {k} को {n:,} भविष्यों में परखा। ",
           c=sr["combinations"], k=sr["stress_tested"], n=sr["sims_each"])
    if sug:
        t += _l(lang, "Best plan: {plan}. Your odds of staying above your cushion go from {a} to {b}.", "सबसे अच्छी योजना: {plan}। कुशन से ऊपर रहने की संभावना {a} से {b} हो जाती है।",
                plan=_join([move_title(m, lang) for m in sug], lang), a=_pct(ob["p_safe"]), b=_pct(os_["p_safe"]))
        easier = [x for x in sr["plans"] if x["cost"] < sum(m["effort"] for m in sug) and x["reaches_safety"]]
        if easier:
            t += _l(lang, " Easier plans exist, but they leave you safe in only {x}.", " आसान योजनाएँ भी हैं, पर उनमें संभावना सिर्फ़ {x} है।", x=_pct(max(e["p_safe"] for e in easier)))
    else:
        t += _l(lang, "No moves needed — you're already safe in {a} of futures.", "किसी कदम की ज़रूरत नहीं — {a} भविष्यों में आप पहले से सुरक्षित हैं।", a=_pct(ob["p_safe"]))
    add("planner", t, "good" if os_["p_safe"] >= o["target"] else "caution")

    bk = next((m for m in moves if m["kind"] == "borrow"), None)
    if bk:
        add("financing", _l(lang, "The plan still leaves real risk ({r} chance of running out). Keep a {amt} overdraft ready as a backup — your odds rise to {o}. "
                                  "Using all of it for 90 days would cost about {i} in interest.",
                            "योजना के बाद भी जोखिम है (कैश खत्म होने की {r} संभावना)। बैकअप के लिए {amt} का ओवरड्राफ़्ट तैयार रखें — संभावना {o} हो जाती है। "
                            "पूरा 90 दिन इस्तेमाल करने पर ब्याज लगभग {i}।",
                            r=_pct(os_["p_short"]), amt=short(bk["amount"]), o=_pct(bk["odds_with_plan"]), i=short(bk["interest_if_used"])), "caution")

    a = p["audit"]
    if a["matches"]:
        add("auditor", _l(lang, "Re-ran the full forecast with the plan: tightest day {x} — matches the planner. Every number above comes from your own records.",
                          "योजना के साथ पूरा अनुमान दोबारा चलाया: सबसे तंग दिन {x} — योजनाकार से मेल खाता है। ऊपर का हर आंकड़ा आपके अपने रिकॉर्ड से है।",
                          x=short(a["rerun_lowest"])), "good")
    else:
        add("auditor", _l(lang, "The re-run gives {x}, not {y} — treat this plan with care.", "दोबारा चलाने पर {x} आया, {y} नहीं — इस योजना को सावधानी से लें।",
                          x=short(a["rerun_lowest"]), y=short(a["planned_lowest"])), "bad")
    return out


def brief(p: dict, lang: str = "en") -> str:
    """The plain summary FinPilot gives when no AI is on (and the fallback when the AI's figures can't be verified)."""
    moves = [m for m in p["moves"] if m.get("state") != "dismissed"]
    sug = [m for m in moves if m["suggested"] and m["kind"] != "reserve"]
    o, b = p["odds"], p["baseline"]
    if b["safe"] and o["baseline"]["p_safe"] >= o["target"]:
        return _l(lang, "You're in good shape. You can spend up to {x} today and still stay above your cushion, and you stay safe in {s} of possible futures.",
                  "आप ठीक हैं। आज {x} तक खर्च कर सकते हैं और फिर भी कुशन से ऊपर रहेंगे; {s} भविष्यों में आप सुरक्षित हैं।",
                  x=short(b["spendable_today"]), s=_pct(o["baseline"]["p_safe"]))
    t = headline(p, lang) + " "
    if sug:
        t += _l(lang, "Approve the plan — {plan} — and your odds go from {a} to {b}.", "योजना मंज़ूर करें — {plan} — और संभावना {a} से {b} हो जाती है।",
                plan=_join([move_title(m, lang) for m in sug], lang), a=_pct(o["baseline"]["p_safe"]), b=_pct(o["suggested"]["p_safe"]))
    bk = next((m for m in moves if m["kind"] == "borrow"), None)
    if bk:
        t += _l(lang, " As a backup, keep a {amt} overdraft ready: that takes you to {o}.", " बैकअप के लिए {amt} का ओवरड्राफ़्ट तैयार रखें: इससे {o} हो जाता है।",
                amt=short(bk["amount"]), o=_pct(bk["odds_with_plan"]))
    return t.strip()


BRIEF_QUESTION = {
    "en": "Brief me like my finance manager, in at most 4 short sentences: will I run short of cash, what should I approve, and how much does it improve my odds? "
          "Use get_cash_autopilot.",
    "hi": "मेरे फ़ाइनेंस मैनेजर की तरह, ज़्यादा से ज़्यादा 4 छोटे वाक्यों में बताइए: क्या कैश कम पड़ेगा, मुझे क्या मंज़ूर करना चाहिए, और इससे संभावना कितनी सुधरती है? get_cash_autopilot इस्तेमाल करें।",
}


# ---------------------------------------------------------------- what changed


def picture(p: dict) -> dict:
    b = p["baseline"]
    return {"today": p["today"], "lowest": b["lowest"], "runs_out": b["runs_out"], "below": b["below_safety_from"], "spendable": b["spendable_today"],
            "p_safe": p["odds"]["baseline"]["p_safe"], "overdue": {m["party"]: m["amount"] for m in p["moves"] if m["kind"] == "collect"}}


def changes(prev: dict | None, cur: dict, lang: str = "en") -> list[dict]:
    if not prev:
        return []
    out: list[dict] = []

    def add(tone, en, hi, **kw):
        out.append({"tone": tone, "text": _l(lang, en, hi, **kw)})

    for who, amt in prev.get("overdue", {}).items():
        now = cur["overdue"].get(who, 0)
        if now < amt - 1:
            add("good", "{who} paid {amt} of what was overdue.", "{who} ने बकाया में से {amt} चुकाए।", who=who, amt=short(amt - now))
    for who, amt in cur["overdue"].items():
        if who not in prev.get("overdue", {}):
            add("caution", "{who} is now overdue: {amt}.", "{who} अब बकाया है: {amt}।", who=who, amt=short(amt))
    if prev.get("runs_out") and not cur["runs_out"]:
        add("good", "You no longer run out of cash (it was {d}).", "अब कैश खत्म नहीं होगा (पहले {d} था)।", d=day(prev["runs_out"], lang))
    elif cur["runs_out"] and not prev.get("runs_out"):
        add("bad", "New risk: cash would run out on {d}.", "नया खतरा: {d} को कैश खत्म हो सकता है।", d=day(cur["runs_out"], lang))
    elif cur["runs_out"] and cur["runs_out"] != prev.get("runs_out"):
        later = cur["runs_out"] > prev["runs_out"]
        add("good" if later else "bad", "Cash now runs out on {d} (was {p}).", "कैश अब {d} को खत्म होगा (पहले {p})।", d=day(cur["runs_out"], lang), p=day(prev["runs_out"], lang))
    elif not cur["runs_out"] and prev.get("below") != cur["below"]:
        if cur["below"] and not prev.get("below"):
            add("caution", "Cash now dips below your cushion on {d}.", "कैश अब {d} को कुशन से नीचे जाएगा।", d=day(cur["below"], lang))
        elif prev.get("below") and not cur["below"]:
            add("good", "You now stay above your cushion all 90 days.", "अब आप पूरे 90 दिन कुशन से ऊपर रहेंगे।")
    if abs(cur["p_safe"] - prev.get("p_safe", cur["p_safe"])) >= 0.05:
        add("good" if cur["p_safe"] > prev["p_safe"] else "caution", "Your odds of staying safe went from {a} to {b}.", "सुरक्षित रहने की संभावना {a} से {b} हुई।",
            a=_pct(prev["p_safe"]), b=_pct(cur["p_safe"]))
    if abs(cur["spendable"] - prev.get("spendable", cur["spendable"])) >= 10_000:
        add("good" if cur["spendable"] > prev["spendable"] else "caution", "Safe to spend today: {a} (was {b}).", "आज सुरक्षित खर्च: {a} (पहले {b})।",
            a=short(cur["spendable"]), b=short(prev["spendable"]))
    return out[:5]
