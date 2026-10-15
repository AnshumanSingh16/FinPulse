"""Owner-facing text in English and Hindi. Numbers are formatted the same way in both (₹14.85 L, ₹4,15,800)."""

from __future__ import annotations

import pandas as pd

LANGS = ("en", "hi")

MONTHS_HI = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
MONTHS_HI_SHORT = ["जन", "फ़र", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अग", "सित", "अक्टू", "नव", "दिस"]
WEEKDAYS_HI = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]


def norm(lang: str | None) -> str:
    return lang if lang in LANGS else "en"


def day(d, lang: str = "en") -> str:
    d = pd.Timestamp(d)
    return f"{d.day} {MONTHS_HI_SHORT[d.month - 1]}" if lang == "hi" else f"{d.day} {d:%b}"


def day_full(d, lang: str = "en") -> str:
    d = pd.Timestamp(d)
    return f"{d.day} {MONTHS_HI_SHORT[d.month - 1]} {d.year}" if lang == "hi" else f"{d.day} {d:%b %Y}"


def month(d, lang: str = "en", year: bool = True) -> str:
    d = pd.Timestamp(d)
    if lang == "hi":
        return f"{MONTHS_HI[d.month - 1]} {d.year}" if year else MONTHS_HI[d.month - 1]
    return d.strftime("%B %Y" if year else "%B")


def weekday(d, lang: str = "en") -> str:
    d = pd.Timestamp(d)
    return WEEKDAYS_HI[d.weekday()] if lang == "hi" else d.strftime("%A")


T: dict[str, tuple[str, str]] = {
    # status
    "st.no_balance.h": ("Add your bank balance to see where you stand", "अपना बैंक बैलेंस जोड़ें, ताकि आपकी असली स्थिति दिखे"),
    "st.no_balance.d": ("FinPilot needs one balance from your bank statement to work out your cash. It never guesses cash from sales.",
                        "आपका कैश जानने के लिए FinPilot को बैंक स्टेटमेंट का एक बैलेंस चाहिए। यह बिक्री से कैश का अंदाज़ा नहीं लगाता।"),
    "st.negative.h": ("Cash could run out around {date}", "{date} के आसपास पैसे खत्म हो सकते हैं"),
    "st.negative.d": ("Based on bills due, money customers owe you and your usual monthly spending. Act now: chase payments or delay big purchases.",
                      "बकाया बिल, ग्राहकों की उधारी और आपके हर महीने के खर्च के आधार पर। अभी कदम उठाएँ: वसूली करें या बड़ी ख़रीद टालें।"),
    "st.tight.h": ("Cash could get tight around {date}", "{date} के आसपास पैसों की तंगी हो सकती है"),
    "st.tight.d": ("Your balance may drop below {cushion} — one month of running costs — with a low of {low} on {lowdate}.",
                   "बैलेंस {cushion} (एक महीने का खर्च) से नीचे जा सकता है; सबसे कम {low}, {lowdate} को।"),
    "st.nohist.h": ("{cash} in the bank", "बैंक में {cash}"),
    "st.nohist.d": ("Record a few weeks of sales and expenses and FinPilot will show how long your cash lasts and warn you before it runs low.",
                    "कुछ हफ़्तों की बिक्री और खर्च दर्ज करें — फिर FinPilot बताएगा कि पैसा कितने दिन चलेगा और कम होने से पहले चेतावनी देगा।"),
    "st.good.h": ("Your business is in good shape", "आपका कारोबार अच्छी हालत में है"),
    "st.good.d": ("{cash} in the bank — about {months} months of running costs. On current plans it stays above one month's costs for the next 90 days.",
                  "बैंक में {cash} — लगभग {months} महीने का खर्च। मौजूदा हिसाब से अगले 90 दिन यह एक महीने के खर्च से ऊपर रहेगा।"),
    # attention
    "att.recon.t": ("Your records don't match the bank", "आपका हिसाब बैंक से मेल नहीं खाता"),
    "att.recon.b": ("On {date} the bank said {stated}, your records say {computed}. Some transactions may be missing or entered twice.",
                    "{date} को बैंक में {stated} था, आपके हिसाब में {computed}। कुछ लेन-देन छूटे या दो बार दर्ज हो सकते हैं।"),
    "att.recon.a": ("Check transactions", "लेन-देन जाँचें"),
    "att.cash_out.t": ("Cash may run out on {date}", "{date} को पैसे खत्म हो सकते हैं"),
    "att.cash_tight.t": ("Cash may get tight on {date}", "{date} को पैसों की तंगी हो सकती है"),
    "att.cash.b": ("Lowest expected balance: {low} on {date}. See what's coming in and out.", "सबसे कम अनुमानित बैलेंस: {low}, {date} को। देखें क्या आ रहा है और क्या जा रहा है।"),
    "att.cash.a": ("See cash ahead", "आगे का कैश देखें"),
    "att.owed.t": ("{name} owes you {amt}", "{name} पर आपके {amt} बाकी हैं"),
    "att.owed.b": ("{n} invoice(s) overdue, the oldest by {days} days.", "{n} बिल बकाया, सबसे पुराना {days} दिन से।"),
    "att.owed.a": ("Draft a reminder", "याद दिलाने का मैसेज बनाएँ"),
    "att.promise.t": ("{name} promised {amt} by {date}", "{name} ने {date} तक {amt} देने का वादा किया था"),
    "att.promise.b": ("The date has passed and {due} is still due.", "तारीख निकल गई और अभी भी {due} बाकी है।"),
    "att.bill.t": ("Bill to {name} is {days} days late", "{name} का बिल {days} दिन लेट है"),
    "att.bill.b": ("{amt} was due on {date}. Late payments can cost supplier goodwill.", "{amt} {date} को देना था। देर से भुगतान से सप्लायर का भरोसा घटता है।"),
    "att.bill.a": ("Add to my to-dos", "मेरे काम में जोड़ें"),
    "att.bill.todo": ("Pay {name} {amt} ({id})", "{name} को {amt} दें ({id})"),
    "att.dup.t": ("Possible double payment to {name}", "{name} को शायद दो बार भुगतान हुआ"),
    "att.dup.b": ("{n} identical payments of {amt} on {date}. Worth checking with your bank or supplier.", "{date} को {amt} के {n} एक जैसे भुगतान। बैंक या सप्लायर से जाँच लें।"),
    "att.dup.a": ("Review payments", "भुगतान देखें"),
    "att.odd.t": ("Unusual {cat} payment: {amt}", "असामान्य {cat} भुगतान: {amt}"),
    "att.odd.b": ("Paid to {party} on {date} — {times}× the usual amount.", "{date} को {party} को — आम रकम का {times} गुना।"),
    "att.odd.a": ("See payment", "भुगतान देखें"),
    "att.budget.t": ("{cat} is over budget", "{cat} का बजट पार हो गया"),
    "att.budget.b": ("Spent {spent} of {limit} this month.", "इस महीने {limit} में से {spent} खर्च।"),
    "att.budget.a": ("See budgets", "बजट देखें"),
    "att.review.t": ("{n} transactions need a category", "{n} लेन-देन की श्रेणी चुननी है"),
    "att.review.b": ("A quick sort makes your profit and budgets accurate. FinPilot remembers your choices.", "श्रेणी चुनने से मुनाफ़ा और बजट सही बनते हैं। FinPilot आपकी पसंद याद रखता है।"),
    "att.review.a": ("Sort them", "श्रेणी चुनें"),
    # insight
    "ins.up": ("Running costs rose {pct}% compared with {month}. Biggest jump: {cat} (+{amt}).", "{month} के मुकाबले खर्च {pct}% बढ़ा। सबसे ज़्यादा बढ़त: {cat} (+{amt})।"),
    "ins.down": ("Running costs fell {pct}% compared with {month}. Biggest drop: {cat} (−{amt}).", "{month} के मुकाबले खर्च {pct}% घटा। सबसे ज़्यादा कमी: {cat} (−{amt})।"),
    "ins.ask.up": ("Why did costs go up in {month}?", "{month} में खर्च क्यों बढ़ा?"),
    "ins.ask.down": ("Why did costs go down in {month}?", "{month} में खर्च क्यों घटा?"),
    "month.so_far": ("{month} so far", "{month} अब तक"),
    # forecast
    "fc.neutral": ("{cash} today — add more history for a fuller forecast", "आज {cash} — पूरे अनुमान के लिए और हिसाब जोड़ें"),
    "fc.bad": ("Cash runs out on {date}", "{date} को पैसे खत्म हो जाएँगे"),
    "fc.caution": ("Cash dips below your cushion on {date}", "{date} को कैश आपकी सुरक्षित सीमा से नीचे जाएगा"),
    "fc.good": ("Cash stays above {cushion} for the next {days} days", "अगले {days} दिन कैश {cushion} से ऊपर रहेगा"),
    "fc.detail": ("Lowest point: {low} on {date}. Starting from {start} today.", "सबसे कम: {low}, {date} को। आज {start} से शुरू।"),
    "fc.pay": ("Pay {name}", "{name} को भुगतान"),
    "fc.from": ("From {name}", "{name} से"),
    "fc.need_balance": ("Add your bank balance first — the forecast starts from your real cash.", "पहले बैंक बैलेंस जोड़ें — अनुमान आपके असली कैश से शुरू होता है।"),
    # afford
    "af.need_balance": ("Add your bank balance first — FinPilot checks affordability against your real cash.", "पहले बैंक बैलेंस जोड़ें — FinPilot आपके असली कैश से जाँचता है।"),
    "af.need_loan": ("Enter the interest rate and number of years from your lender's quote. FinPilot doesn't guess loan terms.",
                     "लोन देने वाले से मिली ब्याज दर और साल भरें। FinPilot लोन की शर्तें अंदाज़े से नहीं लगाता।"),
    "af.invalid": ("Please enter a valid price and numbers.", "कृपया सही कीमत और संख्याएँ भरें।"),
    "af.good.h": ("Yes, you can afford it", "हाँ, आप इसे खरीद सकते हैं"),
    "af.good.d": ("Even if the next few months are tough, your bank balance stays above {cushion} — one month of running costs. Lowest: {low} around {date}.",
                  "अगले कुछ महीने मुश्किल हों तब भी बैलेंस {cushion} (एक महीने का खर्च) से ऊपर रहेगा। सबसे कम: {low}, {date} के आसपास।"),
    "af.tight.h": ("Yes — but it's tight if business slows", "हाँ — पर धंधा धीमा हुआ तो तंगी होगी"),
    "af.tight.d": ("Most likely your balance stays above {cushion}. In tough months it could dip to {low} around {date}, below one month of running costs.",
                   "ज़्यादा संभावना है कि बैलेंस {cushion} से ऊपर रहेगा। मुश्किल महीनों में {date} के आसपास {low} तक गिर सकता है — एक महीने के खर्च से कम।"),
    "af.tight.extra": (" Tough months would be tight even without this purchase.", " मुश्किल महीनों में यह ख़रीद न भी करें तो तंगी रहेगी।"),
    "af.risky.h": ("Risky right now", "अभी जोखिम भरा है"),
    "af.risky.d": ("Even in the most likely case your balance falls to {low} around {date} — below one month of running costs ({cushion}).",
                   "सबसे संभावित हालत में भी बैलेंस {date} के आसपास {low} तक गिरेगा — एक महीने के खर्च ({cushion}) से कम।"),
    "af.bad.h": ("Not right now", "अभी नहीं"),
    "af.bad.d": ("Your bank balance would go below zero around {date} in the most likely case.", "सबसे संभावित हालत में {date} के आसपास बैलेंस शून्य से नीचे चला जाएगा।"),
    "sc.optimistic": ("If things go well", "अगर सब अच्छा रहा"),
    "sc.base": ("Most likely", "सबसे संभावित"),
    "sc.downside": ("If the next few months are tough", "अगर अगले कुछ महीने मुश्किल रहे"),
    "sc.assumes": ("Assumes {parts}.", "मान कर: {parts}।"),
    "sc.default": ("Assumes customers pay on time and the benefit is what you expect.", "मान कर: ग्राहक समय पर देंगे और फ़ायदा आपके अनुमान जितना होगा।"),
    "sc.p.mult_hi": ("the benefit is higher ({x}× your estimate)", "फ़ायदा ज़्यादा ({x}× अनुमान)"),
    "sc.p.mult_lo": ("the benefit is lower ({x}× your estimate)", "फ़ायदा कम ({x}× अनुमान)"),
    "sc.p.delay": ("it starts {n} months late", "यह {n} महीने देर से शुरू होगा"),
    "sc.p.late": ("customers pay {n} days late", "ग्राहक {n} दिन देर से देंगे"),
    "sc.p.loss": ("{n}% of what's owed isn't collected", "उधारी का {n}% वसूल नहीं होगा"),
    "sc.p.overdue": ("overdue customers pay up", "बकाया ग्राहक पैसा दे देंगे"),
    "sep": (", ", ", "),
    # evidence titles
    "ev.cash": ("How we know your cash", "हमें आपका कैश कैसे पता है"),
    "ev.month_profit": ("How we worked out {month}'s profit", "{month} का मुनाफ़ा कैसे निकाला"),
    "ev.owed": ("How we worked out what's owed", "बकाया कैसे निकाला"),
    "ev.profit": ("How we worked out profit", "मुनाफ़ा कैसे निकाला"),
    "ev.forecast": ("How this forecast works", "यह अनुमान कैसे बनता है"),
    "ev.afford": ("How we checked this", "हमने इसे कैसे जाँचा"),
    "ev.health": ("How the health score works", "हेल्थ स्कोर कैसे बनता है"),
    "ev.gst": ("How the GST estimate works", "GST अनुमान कैसे बनता है"),
    "ev.whatif": ("How this is calculated", "यह कैसे निकाला"),
    # report labels
    "rep.capex": ("Bought equipment / assets", "मशीन / सामान खरीदा"),
    "rep.loan_in": ("Loans received", "लोन मिला"),
    "rep.emi": ("Loan EMIs paid", "लोन की EMI दी"),
    "rep.drawings": ("Taken out by owner", "मालिक ने निकाला"),
    "rep.tax": ("GST / TDS paid", "GST / TDS भरा"),
    # misc
    "owed.missing": ("Upload your invoices and bills to see who owes you and what you owe.", "उधारी और बकाया देखने के लिए बिल अपलोड करें या उधार दर्ज करें।"),
}

# Health score components
T |= {
    "hs.cash": ("Cash cushion", "कैश की सुरक्षा"),
    "hs.profit": ("Profit", "मुनाफ़ा"),
    "hs.collections": ("Collections", "वसूली"),
    "hs.bills": ("Paying bills", "बिल भुगतान"),
    "hs.momentum": ("Sales trend", "बिक्री का रुझान"),
    "hs.cash.v": ("{v} months of running costs in the bank", "बैंक में {v} महीने का खर्च"),
    "hs.profit.v": ("{v}% profit on sales (last 3 months)", "बिक्री पर {v}% मुनाफ़ा (पिछले 3 महीने)"),
    "hs.collections.v": ("{v}% of customer dues are overdue", "ग्राहकों की {v}% उधारी बकाया है"),
    "hs.bills.v": ("{v}% of your bills are overdue", "आपके {v}% बिल बकाया हैं"),
    "hs.momentum.v": ("Sales {v}% vs the 3 months before", "पिछले 3 महीनों के मुकाबले बिक्री {v}%"),
    "hs.unknown": ("Not enough data yet", "अभी पूरा हिसाब नहीं"),
    "hs.cash.tip": ("Keep at least 2 months of costs in the bank. Collect overdue dues before big purchases.", "बैंक में कम से कम 2 महीने का खर्च रखें। बड़ी ख़रीद से पहले उधारी वसूलें।"),
    "hs.profit.tip": ("Check your biggest costs and whether prices need a small increase — try the price simulator.", "सबसे बड़े खर्च देखें और सोचें क्या दाम थोड़े बढ़ाने चाहिए — प्राइस सिम्युलेटर आज़माएँ।"),
    "hs.collections.tip": ("Send reminders to customers with old dues and agree a payment date.", "पुरानी उधारी वाले ग्राहकों को याद दिलाएँ और भुगतान की तारीख तय करें।"),
    "hs.bills.tip": ("Pay overdue supplier bills first to keep good terms.", "पहले बकाया सप्लायर बिल चुकाएँ ताकि रिश्ते अच्छे रहें।"),
    "hs.momentum.tip": ("Sales are slowing — look at your top customers and run an offer if margins allow.", "बिक्री धीमी है — बड़े ग्राहकों पर ध्यान दें और मुनाफ़ा अनुमति दे तो ऑफ़र चलाएँ।"),
    "hs.good": ("Looking good", "अच्छा है"),
    "hs.grade.Excellent": ("Excellent", "बहुत बढ़िया"),
    "hs.grade.Good": ("Good", "अच्छा"),
    "hs.grade.Fair": ("Fair", "ठीक-ठाक"),
    "hs.grade.Needs attention": ("Needs attention", "ध्यान चाहिए"),
}

# Weekly story
T |= {
    "story.title": ("Your week", "आपका हफ़्ता"),
    "story.range": ("{start} – {end}", "{start} – {end}"),
    "story.sales": ("You sold {amt} this week", "इस हफ़्ते {amt} की बिक्री"),
    "story.sales.vs_up": ("{pct}% more than last week ({prev}).", "पिछले हफ़्ते ({prev}) से {pct}% ज़्यादा।"),
    "story.sales.vs_down": ("{pct}% less than last week ({prev}).", "पिछले हफ़्ते ({prev}) से {pct}% कम।"),
    "story.sales.vs_none": ("Nothing to compare with last week.", "पिछले हफ़्ते से तुलना के लिए कुछ नहीं।"),
    "story.best": ("Best day: {day}", "सबसे अच्छा दिन: {day}"),
    "story.best.b": ("{amt} in sales — your busiest day of the week.", "{amt} की बिक्री — हफ़्ते का सबसे व्यस्त दिन।"),
    "story.top": ("Top customer: {name}", "सबसे बड़ा ग्राहक: {name}"),
    "story.top.b": ("Paid you {amt} this week.", "इस हफ़्ते {amt} दिए।"),
    "story.spend": ("Biggest spend: {amt}", "सबसे बड़ा खर्च: {amt}"),
    "story.spend.b": ("{what} — {party}.", "{what} — {party}।"),
    "story.collect": ("You collected {amt} of udhaar", "{amt} की उधारी वसूली"),
    "story.collect.b": ("{n} invoice(s) cleared. Keep it up!", "{n} बिल चुकता। ऐसे ही जारी रखें!"),
    "story.udhaar": ("New udhaar given: {amt}", "नई उधारी दी: {amt}"),
    "story.udhaar.b": ("Remember to set a due date and follow up.", "भुगतान की तारीख तय करें और याद दिलाते रहें।"),
    "story.net_pos": ("You ended the week {amt} up", "हफ़्ते के अंत में {amt} का फ़ायदा"),
    "story.net_neg": ("You ended the week {amt} down", "हफ़्ते के अंत में {amt} कम"),
    "story.net.b": ("Money in {inn} · money out {out}.", "आया {inn} · गया {out}।"),
    "story.empty": ("No transactions this week yet. Add today's sales with the + button.", "इस हफ़्ते अभी कोई लेन-देन नहीं। + बटन से आज की बिक्री जोड़ें।"),
}

# Calendar statutory titles
T |= {
    "cal.TDS deposit for last month": ("TDS deposit for last month", "पिछले महीने का TDS जमा"),
    "cal.GSTR-1": ("GSTR-1", "GSTR-1"),
    "cal.GSTR-3B + GST payment": ("GSTR-3B + GST payment", "GSTR-3B + GST भुगतान"),
    "cal.GSTR-1 (quarterly)": ("GSTR-1 (quarterly)", "GSTR-1 (तिमाही)"),
    "cal.GSTR-3B (quarterly) + GST payment": ("GSTR-3B (quarterly) + GST payment", "GSTR-3B (तिमाही) + GST भुगतान"),
    "cal.GST payment (PMT-06)": ("GST payment (PMT-06)", "GST भुगतान (PMT-06)"),
    "cal.Advance income tax instalment": ("Advance income tax instalment", "एडवांस इनकम टैक्स किस्त"),
    "cal.expected": ("Usually paid to {party} around day {day}", "आमतौर पर {day} तारीख के आसपास {party} को"),
    "cal.typical": ("Typical due date — confirm on the GST / income-tax portal.", "आम तौर पर यही तारीख — GST / इनकम टैक्स पोर्टल पर पुष्टि करें।"),
}


def t(lang: str, key: str, **kw) -> str:
    en, hi = T.get(key, (key, key))
    s = hi if lang == "hi" else en
    try:
        return s.format(**kw)
    except (KeyError, IndexError):
        return s
