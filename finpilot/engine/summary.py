"""
Revenue, recorded expenses and estimated operating profit — kept apart from cash flow.

Basis: cash basis on the ledger (money that actually moved). Invoices raised but not yet paid are
receivables, not revenue here, so nothing is counted twice.
"""

from __future__ import annotations

import pandas as pd

from finpilot.data.schema import CLASS_LABEL, Evidence
from finpilot.engine.common import in_period, money, prepare_ledger

OPEX_CLASSES = ("operating", "unclassified_out")


def financial_summary(
    ledger: pd.DataFrame,
    start=None,
    end=None,
    obligations: pd.DataFrame | None = None,
    as_of=None,
) -> dict:
    df = in_period(prepare_ledger(ledger), start, end)
    if df.empty:
        return {
            "status": "insufficient_data",
            "message": "No ledger transactions fall in the requested period.",
            "evidence": Evidence(method="No rows to summarise.").to_dict(),
        }
    inflow = df[df["direction"] == "in"]
    outflow = df[df["direction"] == "out"]

    rev_rows = inflow[inflow["cls"] == "revenue"]
    revenue = rev_rows["amount"].sum()
    # Operating expenses net of any inflows booked to operating categories (e.g. a supplier refund).
    opex_out = outflow[outflow["cls"].isin(OPEX_CLASSES)]
    opex_back = inflow[inflow["cls"].isin(("operating",))]
    opex = opex_out["amount"].sum() - opex_back["amount"].sum()

    def total(cls: str, direction: str) -> float:
        part = df[(df["cls"] == cls) & (df["direction"] == direction)]
        return money(part["amount"].sum())

    other = {
        "capex": total("capex", "out"),
        "financing_in": total("financing_in", "in"),
        "loan_repayments": total("financing_out", "out"),
        "owner_drawings": total("drawings", "out"),
        "tax_remitted": total("tax_remittance", "out"),
        "transfers_in": total("transfer", "in"),
        "transfers_out": total("transfer", "out"),
        "other_inflows": money(total("other_in", "in") + total("unclassified_in", "in")),
    }

    total_in = inflow["amount"].sum()
    total_out = outflow["amount"].sum()

    monthly = (
        df.assign(month=df["date"].dt.to_period("M").astype(str))
        .groupby("month")
        .apply(
            lambda g: pd.Series(
                {
                    "revenue": money(g.loc[(g.direction == "in") & (g.cls == "revenue"), "amount"].sum()),
                    "operating_expenses": money(
                        g.loc[(g.direction == "out") & g.cls.isin(OPEX_CLASSES), "amount"].sum()
                        - g.loc[(g.direction == "in") & (g.cls == "operating"), "amount"].sum()
                    ),
                    "net_cash_movement": money(g["signed"].sum()),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    monthly["estimated_operating_profit"] = (monthly["revenue"] - monthly["operating_expenses"]).round(2)

    by_category = (
        opex_out.groupby("category")["amount"].sum().sort_values(ascending=False).round(2).to_dict()
    )
    revenue_by_category = rev_rows.groupby("category")["amount"].sum().round(2).to_dict()

    limitations = [
        "Cash basis: revenue is money received from sales in the period; unpaid invoices are not included.",
        "Revenue − operating expenses is a net operating CASH difference, not accounting profit: it leaves out "
        "unpaid invoices, unpaid bills (accruals), costs that belong to other periods, depreciation, GST input-credit "
        "adjustments and the interest inside loan EMIs.",
        "This is not a cash balance: cash also depends on the opening balance, loans, asset purchases, "
        "taxes and owner drawings.",
    ]
    unclassified = sorted(
        set(df.loc[df["cls"].isin(("unclassified_out", "unclassified_in")), "category"].astype(str))
    )
    if unclassified:
        limitations.append(
            "Categories FinPilot doesn't recognise — outflows treated as operating expenses, inflows "
            f"not counted as revenue: {', '.join(unclassified)}."
        )
    if other["capex"]:
        limitations.append(
            f"Asset purchases of {other['capex']:,.0f} are excluded from operating expenses (no depreciation applied)."
        )
    pending_payables = None
    unpaid_invoices = None
    if obligations is not None and as_of is not None and len(obligations):
        o = obligations
        pend = o[(o["kind"] == "payable") & (o["status"] == "pending")]
        if "issue_date" in pend:
            pend = pend[pd.to_datetime(pend["issue_date"]) <= pd.Timestamp(as_of)]
        pending_payables = money(pend["amount"].sum())
        rec = o[(o["kind"] == "receivable") & (o["status"] == "pending")]
        if "issue_date" in rec and len(df):
            iss = pd.to_datetime(rec["issue_date"])
            rec = rec[(iss >= df["date"].min()) & (iss <= df["date"].max())]
            unpaid_invoices = money(rec["amount"].sum())
            if unpaid_invoices:
                limitations.append(f"Invoices raised in this period but not yet paid ({unpaid_invoices:,.0f}) are not counted as revenue.")
        if pending_payables:
            limitations.append(
                f"Bills already received but unpaid ({pending_payables:,.0f}) are not deducted."
            )

    period = (str(df["date"].min().date()), str(df["date"].max().date()))
    return {
        "status": "ok",
        "period": {"start": period[0], "end": period[1], "requested_start": str(start) if start else None, "requested_end": str(end) if end else None},
        "transactions": int(len(df)),
        "revenue": money(revenue),
        "operating_expenses": money(opex),
        "estimated_operating_profit": money(revenue - opex),
        "profit_label": "Net operating cash difference (sales received − running costs paid; estimated, not accounting profit)",
        "pending_payables": pending_payables,
        "unpaid_invoices_in_period": unpaid_invoices,
        "estimated_margin_pct": money(100 * (revenue - opex) / revenue) if revenue else None,
        "total_inflows": money(total_in),
        "total_outflows": money(total_out),
        "net_cash_movement": money(total_in - total_out),
        "other_flows": other,
        "other_flows_labels": {
            "capex": CLASS_LABEL["capex"],
            "financing_in": CLASS_LABEL["financing_in"],
            "loan_repayments": CLASS_LABEL["financing_out"],
            "owner_drawings": CLASS_LABEL["drawings"],
            "tax_remitted": CLASS_LABEL["tax_remittance"],
        },
        "expenses_by_category": by_category,
        "revenue_by_category": revenue_by_category,
        "monthly": monthly.to_dict(orient="records"),
        "unclassified_categories": unclassified,
        "evidence": Evidence(
            method=(
                "Revenue = sum of inflows in revenue categories. Operating expenses = outflows in "
                "operating (and unrecognised) categories, less refunds booked to them. Estimated "
                "operating profit = revenue − operating expenses. Net cash movement = all inflows − "
                "all outflows."
            ),
            assumptions=("Categories are mapped to accounting classes by FinPilot's category table.",),
            limitations=tuple(limitations),
            record_ids=tuple(rev_rows["txn_id"]) + tuple(opex_out["txn_id"]),
            period=period,
        ).to_dict(),
    }
