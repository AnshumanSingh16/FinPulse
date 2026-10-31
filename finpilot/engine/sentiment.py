"""Local Naive Bayes sentiment analysis for customer feedback.

The bundled labeled text is a small, fictional starter corpus. It demonstrates the
model without calling an external service; results are suggestions, not ground truth.
"""

from __future__ import annotations

import math
import re

import numpy as np

from finpilot.data import books

LABELS = ("negative", "neutral", "positive")
MODEL_NAME = "Multinomial Naive Bayes (word + bigram features)"
STOP_WORDS = {"a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "can", "could", "did", "do", "does", "for", "from", "had", "has", "have", "he", "her", "here", "i", "in", "into", "is", "it", "its", "me", "my", "of", "on", "or", "our", "please", "she", "that", "the", "their", "them", "there", "they", "this", "to", "us", "was", "we", "were", "what", "when", "which", "who", "will", "with", "would", "you", "your"}

# Small, generic English starter corpus. Ratings or feedback labels are not fabricated
# for owner records; only these examples are training labels.
TRAINING_TEXT = {
    "positive": [
        "excellent quality and very fresh",
        "great service and fast delivery",
        "we are happy with the result",
        "friendly staff and a lovely experience",
        "the product is reliable and good value",
        "prompt response and helpful team",
        "beautiful work exactly as requested",
        "delicious food and warm service",
        "easy to book and arrived on time",
        "we will order again, highly recommend",
        "the package exceeded expectations",
        "smooth process and excellent communication",
        "consistent quality and quick dispatch we will reorder this month",
        "the new product is very good and customers like it",
        "customers love the product and the service is excellent",
        "friendly helpful staff and a delicious meal",
        "fast delivery and fresh items, great value",
        "the team was helpful and everything arrived on time",
        "the campaign looks excellent and the design is polished",
        "quick response and a smooth handover",
        "beautiful work, we are very happy with the result",
        "reliable service and excellent quality every time",
    ],
    "neutral": [
        "please send the updated price list",
        "what are the available appointment times",
        "we received the order this morning",
        "the meeting is scheduled for next week",
        "please confirm the quantity and date",
        "share the invoice when it is ready",
        "we would like information about the package",
        "the service was provided on monday",
        "please call me about the next booking",
        "the order contains three items",
        "can you share the menu and timings",
        "we are reviewing the proposal internally",
        "please send the invoice for the september order",
        "please share the revised proposal for the next phase",
        "confirm the turmeric quantity and expected dispatch date",
        "can you confirm the deliverables and booking times for next week",
        "please share the catering menu and available dates for twenty people",
        "the meeting is scheduled for the coming week",
        "send the updated wholesale price list and availability",
        "please confirm the next appointment date",
        "the order contains two cartons and three items",
        "we received the documents this morning",
    ],
    "negative": [
        "very poor quality and stale product",
        "delivery was late and the order was cold",
        "we are unhappy with the slow service",
        "the staff were rude and unhelpful",
        "the product broke and does not work",
        "the project missed the promised deadline",
        "poor communication and repeated mistakes",
        "not worth the price, very disappointing",
        "we had to wait too long for our booking",
        "the package was damaged and incomplete",
        "the food was bland and arrived late",
        "we will not order again",
        "two seals were broken and replacements took too long",
        "some items were missing and the response was slow",
        "the order arrived late and the carton was damaged",
        "the final revisions took too long and the launch is delayed",
        "the team missed the deadline and gave poor updates",
        "the service was slow and we are unhappy",
        "the coffee was cold and the staff were rude",
        "the product tasted stale and was not fresh",
        "we had to wait too long and the quality was poor",
        "the booking was delayed and nobody replied",
    ],
}

DEMO_FEEDBACK = {
    "demo": [
        ("Shree Ganesh Traders", "The garam masala aroma is excellent and the pouches arrived fresh."),
        ("Metro Foods Pvt Ltd", "Our last chilli powder batch tasted stale and the delivery was late."),
        ("FreshMart Retail", "Please share the updated wholesale price list and next week's availability."),
        ("Om Sai Distributors", "Consistent quality and quick dispatch. We will reorder this month."),
        ("Patil Kirana Stores", "Two pouch seals were broken and replacements took too long."),
        ("Kumar Wholesale", "Can you confirm the turmeric quantity and expected dispatch date?"),
        ("Shree Ganesh Traders", "The new biryani masala is very good and our customers like it."),
        ("Metro Foods Pvt Ltd", "The order arrived late and one carton was damaged."),
        ("FreshMart Retail", "Please send the invoice for the September order."),
    ],
    "demo_agency": [
        ("Zenith Realty", "The brand identity work was polished and your team delivered on time."),
        ("Kaveri Hospitals", "Final revisions took longer than promised and the launch is delayed."),
        ("Nimbus EdTech", "Please send the invoice and next month's project timeline."),
        ("Bloom Organics", "The team understood our brief and the campaign looks excellent."),
        ("UrbanFit Gyms", "Communication was slow and we had to request several corrections."),
        ("Orbit Fintech", "Can you confirm the deliverables and booking times for next week?"),
        ("Zenith Realty", "Fast response, excellent design, and a smooth handover."),
        ("Kaveri Hospitals", "We are unhappy with the missed deadline and poor updates."),
        ("Nimbus EdTech", "Please share the revised proposal for the next phase."),
    ],
    "demo_cafe": [
        ("Walk-in customer", "Coffee was delicious and the staff were warm and friendly."),
        ("Techno Park Pvt Ltd", "The brunch order arrived cold and later than the booking time."),
        ("Seaview Co-working", "Please share the catering menu and available dates for 20 people."),
        ("Walk-in customer", "The snack box was fresh, nicely packed, and great value."),
        ("Walk-in customer", "We waited too long and the chai was lukewarm."),
        ("Zippy Eats (delivery app)", "The delivery was quick and everything tasted excellent."),
        ("Techno Park Pvt Ltd", "The catering team was helpful and everything arrived on time."),
        ("Seaview Co-working", "Some items were missing from the order and the response was slow."),
        ("Walk-in customer", "Can you confirm the weekend tasting table timings?"),
    ],
}


def _features(text: str) -> list[str]:
    words = [w for w in re.findall(r"[^\W_]+", str(text).casefold(), flags=re.UNICODE) if w not in STOP_WORDS]
    out = list(words)
    out.extend(f"{a}_{b}" for a, b in zip(words, words[1:]))
    # Preserve common negation phrases as a feature that the model can learn.
    for i, word in enumerate(words[:-1]):
        if word in {"not", "never", "no"}:
            out.append(f"{word}_{words[i + 1]}")
    return out


def _fit():
    docs = {label: [set(_features(text)) for text in texts] for label, texts in TRAINING_TEXT.items()}
    vocab = set().union(*(set().union(*items) for items in docs.values()))
    token_counts = {label: {} for label in LABELS}
    total_tokens = {label: 0 for label in LABELS}
    for label, items in docs.items():
        for item in items:
            for token in item:
                token_counts[label][token] = token_counts[label].get(token, 0) + 1
                total_tokens[label] += 1
    return docs, vocab, token_counts, total_tokens


MODEL = _fit()


def predict(text: str) -> dict:
    docs, vocab, counts, totals = MODEL
    features = _features(text)
    known = [x for x in features if x in vocab]
    size = max(len(vocab), 1)
    log_scores = {}
    for label in LABELS:
        prior = len(docs[label]) / sum(len(v) for v in docs.values())
        score = math.log(prior)
        denom = totals[label] + size
        for token in known:
            score += math.log((counts[label].get(token, 0) + 1) / denom)
        log_scores[label] = score
    peak = max(log_scores.values())
    probs = np.exp(np.array([log_scores[x] - peak for x in LABELS], dtype=float))
    probs /= probs.sum()
    ix = int(np.argmax(probs))
    label = LABELS[ix]
    # The posterior is an uncalibrated model score, not a probability that the text is true.
    matched = list(dict.fromkeys(known))[:6]
    return {"sentiment": label, "score": round(float(probs[ix]), 3), "matched_features": matched}


def ensure_demo_feedback(db, book: str) -> None:
    if book not in DEMO_FEEDBACK:
        return
    with books.connect(db) as con:
        for customer, text in DEMO_FEEDBACK[book]:
            con.execute("INSERT INTO customer_feedback(book,customer,text,created_at,source) SELECT ?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM customer_feedback WHERE book = ? AND customer = ? AND text = ? AND source = ?)", (book, customer, text, "2026-09-30", "fictional demo feedback", book, customer, text, "fictional demo feedback"))


def add_feedback(db, book: str, text: str, customer: str = "", created_at: str | None = None, source: str = "owner entry") -> int:
    text = str(text).strip()
    customer = str(customer).strip()
    if not text or len(text) > 1000:
        raise ValueError("Feedback must contain 1 to 1000 characters.")
    if len(customer) > 120:
        raise ValueError("Customer name must be 120 characters or fewer.")
    ensure_demo_feedback(db, book)
    with books.connect(db) as con:
        cur = con.execute("INSERT INTO customer_feedback(book,customer,text,created_at,source) VALUES(?,?,?,?,?)", (book, customer, text, created_at or books.store.now(), source))
        return int(cur.lastrowid)


def analysis(db, book: str) -> dict:
    ensure_demo_feedback(db, book)
    with books.connect(db) as con:
        rows = con.execute("SELECT id,customer,text,created_at,source FROM customer_feedback WHERE book = ? ORDER BY id DESC LIMIT 200", (book,)).fetchall()
    records = []
    counts = {x: 0 for x in (*LABELS, "uncertain")}
    for ident, customer, text, created_at, source in rows:
        result = predict(text)
        label = result["sentiment"] if result["score"] >= 0.45 else "uncertain"
        counts[label] += 1
        records.append({"id": ident, "customer": customer, "text": text, "date": created_at, "source": source, **result, "sentiment": label})
    return {
        "model": MODEL_NAME,
        "training": "Small bundled English starter corpus of fictional labeled examples; owner feedback is not used to train the model.",
        "limitation": "Short text, sarcasm, mixed language and industry-specific wording can be misread. Scores are uncalibrated model scores, not probabilities or verified customer intent.",
        "counts": counts,
        "total": len(records),
        "records": records,
    }
