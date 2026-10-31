"""Business specific, deterministic product and service analysis.

All amounts are derived from owner entered operational records. Missing demand and
capacity data is reported as missing rather than inferred from bank activity.
"""

from __future__ import annotations

from typing import Any

from finpilot.data import books


DEMO_PROFILES = {
    "demo": {"category": "inventory", "type": "Spice manufacturer", "model": "Make to stock and wholesale distribution", "information": "Fictional Pune spice business. The operating data is seeded for product margin, stock cover and replenishment demonstrations."},
    "demo_agency": {"category": "service", "type": "Creative agency", "model": "Monthly retainers and fixed-fee projects", "information": "Fictional Bengaluru design agency. The operating data is seeded for service margins and delivery capacity demonstrations."},
    "demo_cafe": {"category": "hybrid", "type": "Cafe and catering", "model": "Walk-in cafe, packaged goods and catering bookings", "information": "Fictional Mumbai cafe. The operating data includes packaged products and catering services to demonstrate hybrid intelligence."},
}

DEMO_INVENTORY = {
    "demo": [
        ("Garam Masala 250g", "SP-GM250", 42, 118, 210, 76, 18),
        ("Turmeric Powder 500g", "SP-TP500", 220, 68, 125, 42, 8),
        ("Chilli Powder 500g", "SP-CP500", 65, 92, 160, 90, 14),
        ("Biryani Masala 100g", "SP-BM100", 14, 45, 95, 75, 21),
    ],
    "demo_cafe": [
        ("Cold Brew Bottle 250ml", "BB-CB250", 28, 52, 125, 92, 5),
        ("House Chai Masala Pouch", "BB-HC100", 78, 35, 90, 24, 10),
        ("Diwali Snack Box", "BB-DSB", 46, 280, 495, 22, 14),
    ],
}

DEMO_SERVICES = {
    "demo_agency": [
        ("Brand Identity Sprint", 85000, 29000, 8, 5),
        ("Monthly Growth Retainer", 125000, 72000, 10, 9),
        ("Product Photography Day", 42000, 28000, 12, 4),
        ("Website UX Audit", 32000, 14000, 20, 6),
    ],
    "demo_cafe": [
        ("Office Brunch Catering", 38000, 26000, 12, 9),
        ("Weekend Tasting Table Booking", 2500, 1250, 24, 8),
    ],
}


def ensure_demo_operational_data(db, book: str) -> None:
    """Seed each demo once; unique book/name keys preserve owner edits and additions."""
    if book not in DEMO_PROFILES:
        return
    with books.connect(db) as con:
        for row in DEMO_INVENTORY.get(book, []):
            name, sku, qty, cost, price, sold, lead = row
            con.execute("INSERT OR IGNORE INTO inventory_items(book,name,sku,stock_qty,unit_cost,selling_price,monthly_units_sold,lead_time_days,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (book, name, sku, qty, cost, price, sold, lead, "demo seed"))
        for row in DEMO_SERVICES.get(book, []):
            name, price, cost, capacity, bookings_per_month = row
            con.execute("INSERT OR IGNORE INTO service_offerings(book,name,price,delivery_cost,monthly_capacity,monthly_bookings,updated_at) VALUES(?,?,?,?,?,?,?)", (book, name, price, cost, capacity, bookings_per_month, "demo seed"))


def _records(db, book: str, table: str) -> list[dict]:
    with books.connect(db) as con:
        rows = con.execute(f"SELECT * FROM {table} WHERE book = ? ORDER BY name", (book,)).fetchall()
        cols = [x[0] for x in con.execute(f"SELECT * FROM {table} LIMIT 0").description]
    return [dict(zip(cols, r)) for r in rows]


def inventory(db, book: str) -> list[dict]:
    ensure_demo_operational_data(db, book)
    return _records(db, book, "inventory_items")


def services(db, book: str) -> list[dict]:
    ensure_demo_operational_data(db, book)
    return _records(db, book, "service_offerings")


def profile(db, book: str, fallback_name: str = "") -> dict:
    s = books.settings(db, book)
    demo = DEMO_PROFILES.get(book, {})
    return {
        "name": s.get("business_name") or fallback_name,
        "category": s.get("business_category") or demo.get("category", "hybrid"),
        "type": s.get("business_type") or demo.get("type", ""),
        "model": s.get("business_model") or demo.get("model", ""),
        "information": s.get("business_info") or demo.get("information", ""),
    }


def opportunities(db, book: str) -> list[dict]:
    found: list[dict] = []
    for p in inventory(db, book):
        stock, sold = float(p["stock_qty"]), float(p["monthly_units_sold"] or 0)
        cost, price = float(p["unit_cost"]), float(p["selling_price"])
        lead_days = int(p["lead_time_days"] or 0)
        margin = (price - cost) / price * 100 if price > 0 else None
        if sold > 0 and stock <= sold * lead_days / 30:
            days_cover = stock / sold * 30
            found.append({"key": f"stock:{p['id']}", "kind": "inventory", "tone": "caution", "title": f"Review stock for {p['name']}", "reason": f"Current stock is {stock:g} units against {sold:g} units sold per month. At that pace, recorded stock covers about {days_cover:.0f} days, versus a {lead_days}-day supplier lead time.", "impact": None, "basis": "Owner-entered stock, monthly sales and supplier lead time; the stock-to-sales ratio is not a demand forecast."})
        elif sold > 0 and stock >= sold * 3:
            found.append({"key": f"slow:{p['id']}", "kind": "inventory", "tone": "info", "title": f"Review working capital in {p['name']}", "reason": f"Recorded stock is {stock:g} units, or about {stock / sold:.1f} months of sales at the entered monthly rate.", "impact": round(stock * cost, 2), "basis": "Potential cash tied in stock = stock × recorded unit cost. This ratio does not establish that stock is dead."})
        elif sold == 0 and stock > 0:
            found.append({"key": f"slow:{p['id']}", "kind": "inventory", "tone": "caution", "title": f"Check movement of {p['name']}", "reason": f"{stock:g} units are recorded in stock, with no monthly sales rate entered.", "impact": round(stock * cost, 2), "basis": "Potential cash tied in stock = stock × recorded unit cost. Sales history is missing, so dead stock is not confirmed."})
        if margin is not None and margin < 20:
            found.append({"key": f"margin:{p['id']}", "kind": "inventory", "tone": "info", "title": f"Review the margin on {p['name']}", "reason": f"Recorded gross margin is {margin:.1f}% (selling price less unit cost).", "impact": None, "basis": "Calculated from owner-entered selling price and unit cost; excludes overhead and tax."})
        elif margin is not None and margin >= 40:
            found.append({"key": f"high-margin:{p['id']}", "kind": "inventory", "tone": "good", "title": f"Consider promoting {p['name']}", "reason": f"Recorded gross margin is {margin:.1f}% before overhead and tax.", "impact": None, "basis": "Calculated from owner-entered selling price and unit cost; margin alone does not confirm customer demand."})
    for s in services(db, book):
        capacity, bookings = float(s["monthly_capacity"] or 0), float(s["monthly_bookings"] or 0)
        price, cost = float(s["price"]), float(s["delivery_cost"])
        if capacity > 0:
            utilization = bookings / capacity * 100
            if utilization < 60:
                found.append({"key": f"utilization:{s['id']}", "kind": "service", "tone": "info", "title": f"Review capacity for {s['name']}", "reason": f"Recorded utilisation is {utilization:.1f}% ({bookings:g} bookings of {capacity:g} monthly capacity).", "impact": None, "basis": "Bookings divided by owner-entered monthly capacity. This identifies available capacity, not likely demand."})
        if price > 0 and (price - cost) / price < .2:
            found.append({"key": f"service-margin:{s['id']}", "kind": "service", "tone": "caution", "title": f"Review delivery costs for {s['name']}", "reason": f"Recorded contribution margin is {(price - cost) / price * 100:.1f}% before overhead.", "impact": None, "basis": "Calculated from owner-entered price and delivery cost; excludes overhead and tax."})
        elif price > 0 and (price - cost) / price >= .4:
            found.append({"key": f"service-high-margin:{s['id']}", "kind": "service", "tone": "good", "title": f"Consider featuring {s['name']}", "reason": f"Recorded contribution margin is {(price - cost) / price * 100:.1f}% before overhead and tax.", "impact": None, "basis": "Calculated from owner-entered price and delivery cost; margin alone does not confirm demand."})
    with books.connect(db) as con:
        outcomes = {k: {"status": st, "outcome_note": note, "outcome_updated_at": updated}
                    for k, st, note, updated in con.execute("SELECT key, status, note, updated_at FROM opportunity_outcomes WHERE book = ?", (book,))}
    return [x | outcomes.get(x["key"], {"status": "open", "outcome_note": "", "outcome_updated_at": None}) for x in found]


def simulate(db, book: str, request: dict) -> dict:
    kind = request.get("kind")
    name = str(request.get("name", ""))
    if kind in ("inventory_discount", "inventory_price"):
        p = next((x for x in inventory(db, book) if x["name"].casefold() == name.casefold()), None)
        if not p:
            raise ValueError("Choose a product that exists in your inventory records.")
        units, price, cost = float(p["monthly_units_sold"] or 0), float(p["selling_price"]), float(p["unit_cost"])
        if units <= 0:
            raise ValueError("Enter a positive monthly sales quantity before simulating a product price decision.")
        change = float(request.get("change_pct", 0))
        if not -90 <= change <= 200:
            raise ValueError("Price change must be between -90% and 200%.")
        new_price = price * (1 + change / 100)
        new_units = units
        assumption = "Monthly sales volume is held constant; no demand response is forecast."
        if kind == "inventory_discount" and float(request.get("volume_uplift_pct", 0)):
            uplift = float(request["volume_uplift_pct"])
            if not 0 <= uplift <= 1000:
                raise ValueError("Volume uplift assumption must be between 0% and 1000%.")
            new_units = units * (1 + uplift / 100)
            assumption = f"Hypothetical owner-supplied sales uplift of {uplift:g}%; not a demand forecast."
        return _scenario(name, units, price, cost, new_units, new_price, assumption, category="inventory")
    if kind in ("service_price", "service_launch", "service_hire"):
        s = next((x for x in services(db, book) if x["name"].casefold() == name.casefold()), None) if name else None
        if kind == "service_price" and not s:
            raise ValueError("Choose a service that exists in your service records.")
        price = float(s["price"] if s else request.get("price", 0))
        cost = float(s["delivery_cost"] if s else request.get("cost_per_booking", 0))
        units = float(s["monthly_bookings"] or 0) if s else float(request.get("monthly_bookings", 0))
        if kind in ("service_launch", "service_hire"):
            units = float(request.get("expected_bookings", 0))
            price = float(request.get("price", price))
            cost = float(request.get("cost_per_booking", cost)) + float(request.get("monthly_fixed_cost", 0)) / max(units, 1)
        if price <= 0 or units <= 0:
            raise ValueError("Enter a positive price and monthly bookings, either on the service or in this scenario.")
        change = float(request.get("change_pct", 0)) if kind == "service_price" else 0
        new_price = price * (1 + change / 100)
        assumption = "Monthly bookings and delivery costs are held constant; no demand response is forecast."
        if kind != "service_price":
            assumption = f"Scenario uses {units:g} expected monthly bookings and user-entered costs; these are assumptions, not a forecast."
        return _scenario(name or "New service", units, price, cost, units, new_price, assumption, category="service")
    if kind == "restock":
        p = next((x for x in inventory(db, book) if x["name"].casefold() == name.casefold()), None)
        if not p:
            raise ValueError("Choose a product that exists in your inventory records.")
        quantity, cost = float(request.get("quantity", 0)), float(p["unit_cost"])
        if quantity <= 0:
            raise ValueError("Restock quantity must be greater than zero.")
        return {"kind": kind, "name": name, "cash_outflow": round(quantity * cost, 2), "quantity": quantity, "unit_cost": cost, "estimated_contribution_if_all_sell": round(quantity * (float(p["selling_price"]) - cost), 2), "assumptions": ["All units sell at current recorded price.", "No timing, taxes, operating costs, or cash balance impact is included."], "classification": "Hypothetical scenario; not a forecast."}
    raise ValueError("Unsupported scenario. Choose inventory discount/price/restock or service price/launch/hire.")


def _scenario(name, base_units, base_price, cost, units, price, assumption, category):
    return {"kind": category, "name": name, "baseline": {"monthly_revenue": round(base_units * base_price, 2), "monthly_contribution": round(base_units * (base_price - cost), 2)}, "scenario": {"monthly_revenue": round(units * price, 2), "monthly_contribution": round(units * (price - cost), 2), "unit_price": round(price, 2), "units": round(units, 2)}, "change": {"monthly_revenue": round(units * price - base_units * base_price, 2), "monthly_contribution": round(units * (price - cost) - base_units * (base_price - cost), 2)}, "assumptions": [assumption, "Contribution excludes overhead, tax, payment timing, and other cash flows."], "classification": "Deterministic arithmetic on recorded values and stated assumptions; not a forecast."}
