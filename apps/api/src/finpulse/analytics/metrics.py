"""The financial metrics. Each function takes a ``Context`` and returns one ``Metric``.

Conventions: months are complete calendar months covered by the data; "trailing N months" ends
with the last complete month on or before ``as_of``; point-in-time values are at the end of the
``as_of`` day. Amounts exclude GST wherever sales or purchases are concerned (GST is collected
for the government, not earned).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from finpulse.analytics import classify
from finpulse.analytics.context import Context, month_label
from finpulse.analytics.inputs import Document
from finpulse.analytics.registry import (
    available,
    coefficient_of_variation,
    define,
    inr,
    months_confidence,
    ratio,
    source,
    unavailable,
)
from finpulse.analytics.schemas import (
    ComponentValue,
    Confidence,
    Metric,
    Period,
    SourceRef,
    SourceTable,
)
from finpulse.core.dates import month_end

NO_MONTH = "No complete calendar month of data on or before as_of."

# --- definitions --------------------------------------------------------------------------------

REVENUE_MONTHLY = define(
    "revenue.monthly",
    "Monthly revenue",
    "revenue",
    "INR",
    """Sales excluding GST in the last complete month: taxable value of invoices issued plus
    walk-in (counter) sales net of GST. If the entity has no sales documents at all, operating
    cash receipts are used instead and confidence is low.""",
)
EXPENSES_MONTHLY = define(
    "expenses.monthly",
    "Monthly expenses",
    "expenses",
    "INR",
    """Operating costs in the last complete month: purchases billed by suppliers (excluding GST)
    plus operating cash expenses (salaries, rent, utilities, freight, bank charges, living costs
    for individuals, unclassified cash withdrawals). Excludes debt service, finance costs, owner
    drawings, GST and income tax payments, and investments.""",
)
NET_CASH_FLOW = define(
    "cashflow.net_monthly",
    "Monthly net cash flow",
    "cash_flow",
    "INR",
    """All money into the bank minus all money out in the last complete month. Includes loan
    disbursements and repayments.""",
)
REVENUE_GROWTH = define(
    "revenue.growth",
    "Revenue growth",
    "revenue",
    "ratio",
    """Revenue in the last 3 complete months divided by revenue in the 3 months before, minus 1.
    Needs 6 complete months.""",
)
REVENUE_VOLATILITY = define(
    "revenue.volatility",
    "Revenue volatility",
    "revenue",
    "ratio",
    """Coefficient of variation (population standard deviation ÷ mean) of monthly revenue over
    up to the last 12 complete months. Needs at least 4; 0 = perfectly steady.""",
)
EXPENSE_GROWTH = define(
    "expenses.growth",
    "Expense growth",
    "expenses",
    "ratio",
    """Expenses in the last 3 complete months divided by expenses in the 3 months before, minus
    1. Needs 6 complete months.""",
)
CASH_BALANCE = define(
    "cash.balance",
    "Cash balance",
    "liquidity",
    "INR",
    """Bank balance at the end of the as_of day across all accounts. Negative means the
    overdraft is in use.""",
)
CASH_RUNWAY = define(
    "cash.runway",
    "Cash runway",
    "liquidity",
    "months",
    """Available funds (balance plus undrawn overdraft) divided by the average monthly net cash
    outflow over the last 3 complete months. Not applicable when the entity is not burning cash.""",
)
RECEIVABLES = define(
    "receivables.outstanding",
    "Receivables outstanding",
    "working_capital",
    "INR",
    """Unpaid invoice balances (including GST) at as_of: invoice totals minus payments received
    by as_of, for invoices issued by as_of. Components age the balance by days past due.""",
)
RECEIVABLE_DAYS = define(
    "receivables.days",
    "Receivable days (DSO)",
    "working_capital",
    "days",
    """Receivables at as_of ÷ invoiced sales (including GST) in the last 90 days × 90: roughly how
    many days of credit sales are waiting to be collected.""",
)
PAYABLE_DAYS = define(
    "payables.days",
    "Payable days (DPO)",
    "working_capital",
    "days",
    """Unpaid supplier bill balances at as_of ÷ supplier bills (including GST) received in the
    last 90 days × 90: roughly how many days of purchases are unpaid.""",
)
DEBT_OUTSTANDING = define(
    "debt.outstanding",
    "Debt outstanding",
    "debt",
    "INR",
    """Loan principal still owed at as_of: principal disbursed minus the principal part of every
    instalment paid by as_of. Overdraft usage is reported under cash balance.""",
)
DEBT_SERVICE_BURDEN = define(
    "debt.service_burden",
    "Debt-service burden",
    "debt",
    "ratio",
    """Loan instalments falling due in the last 3 complete months ÷ operating cash receipts in the
    same months. 0.25 = a quarter of what comes in is committed to repayments.""",
)
CUSTOMER_CONCENTRATION = define(
    "customers.concentration",
    "Customer concentration",
    "concentration",
    "ratio",
    """Largest single customer's share of revenue over the last 6 complete months. Walk-in sales
    count as many small customers. Components include the top-3 share and the
    Herfindahl-Hirschman index over identified customers.""",
)
SUPPLIER_CONCENTRATION = define(
    "suppliers.concentration",
    "Supplier concentration",
    "concentration",
    "ratio",
    """Largest single supplier's share of purchases over the last 6 complete months, with top-3
    share and Herfindahl-Hirschman index as components.""",
)
INCOME_STABILITY = define(
    "income.stability",
    "Income stability",
    "behaviour",
    "score",
    """0–100. Over the last 6 complete months of operating cash receipts:
    100 × (1 − min(CV, 1)) × (months with any receipts ÷ months), where CV is the coefficient of
    variation of monthly receipts. Needs at least 4 months.""",
)
PAYMENT_CONSISTENCY = define(
    "payments.consistency",
    "Payment consistency",
    "behaviour",
    "ratio",
    """Share of obligations paid on time over the last 12 months (or the history, if shorter):
    the average of (a) loan instalments paid on or before the due date with no bounced
    auto-debit and (b) supplier bills fully paid within 5 days of their due date, over whichever
    of the two exist.""",
)
LIQUIDITY_RATIO = define(
    "liquidity.ratio",
    "Liquidity ratio",
    "liquidity",
    "ratio",
    """Current assets ÷ current liabilities at as_of. Assets: positive bank balance plus
    receivables. Liabilities: supplier payables, overdraft drawn, overdue instalments, and loan
    principal due in the next 12 months.""",
)
FINANCIAL_BUFFER = define(
    "buffer.months",
    "Financial buffer",
    "liquidity",
    "months",
    """Own cash (positive balance only, no overdraft) ÷ average total monthly outflows over the
    last 3 complete months: how many months of outgoings could be paid with no money coming in.""",
)
TRANSACTION_CONSISTENCY = define(
    "transactions.consistency",
    "Transaction consistency",
    "behaviour",
    "score",
    """0–100 over the last 13 weeks: 100 × (weeks with at least one operating receipt ÷ weeks) ×
    (1 − 0.5 × min(CV of weekly transaction counts, 1)). Needs 8 covered weeks.""",
)

# Windows (months)
GROWTH_WINDOW = 3
VOLATILITY_MONTHS, VOLATILITY_MIN = 12, 4
CONCENTRATION_MONTHS, CONCENTRATION_MIN = 6, 3
STABILITY_MONTHS, STABILITY_MIN = 6, 4
RECENT_MONTHS = 3
TURNOVER_DAYS = 90
BILL_GRACE_DAYS = 5
CONSISTENCY_WEEKS, CONSISTENCY_MIN_WEEKS = 13, 8


# --- revenue & expenses ------------------------------------------------------------------------


def revenue_monthly(ctx: Context) -> Metric:
    if not ctx.months:
        return unavailable(REVENUE_MONTHLY, ctx.as_of_period(), "insufficient_data", NO_MONTH)
    m = ctx.months[-1]
    period = Period(start=m, end=month_end(m), label=month_label(m))
    if ctx.has_sales_documents:
        invoices = [i for i in ctx.invoices if m <= i.issued_on <= month_end(m)]
        sales = [s for s in ctx.counter_sales if m <= s.sold_on <= month_end(m)]
        return available(
            REVENUE_MONTHLY,
            inr(ctx.revenue(m)),
            period,
            components={
                "invoiced_excl_gst": inr(ctx.invoiced_taxable[m]),
                "walk_in_excl_gst": inr(ctx.counter_taxable[m]),
                "basis": ctx.revenue_basis,
            },
            sources=[
                source("invoices", invoices, "Invoices issued in the month (taxable value)"),
                source("counter_sales", sales, "Daily walk-in sales register (net of GST)"),
            ],
        )
    receipts = [t for t in ctx.txns_in([m]) if classify.is_operating_inflow(t.category)]
    return available(
        REVENUE_MONTHLY,
        inr(ctx.revenue(m)),
        period,
        confidence="low",
        components={"basis": ctx.revenue_basis},
        sources=[source("transactions", receipts, "Operating receipts (income.*)")],
        notes=["No sales documents: revenue approximated by bank receipts, which may include tax."],
    )


def expenses_monthly(ctx: Context) -> Metric:
    if not ctx.months:
        return unavailable(EXPENSES_MONTHLY, ctx.as_of_period(), "insufficient_data", NO_MONTH)
    m = ctx.months[-1]
    end = month_end(m)
    bills = [b for b in ctx.bills if m <= b.issued_on <= end]
    spend = [
        t
        for t in ctx.txns_in([m])
        if t.amount_minor < 0
        and classify.is_operating_expense(t.category, include_supplier_payments=not ctx.has_bills)
    ]
    return available(
        EXPENSES_MONTHLY,
        inr(ctx.expenses(m)),
        Period(start=m, end=end, label=month_label(m)),
        components={
            "purchases_excl_gst": inr(ctx.purchases_taxable[m]),
            "operating_cash_expenses": inr(ctx.opex_cash[m]),
        },
        sources=[
            source("bills", bills, "Supplier bills received in the month (taxable value)"),
            source("transactions", spend, "Operating expense debits"),
        ],
    )


def net_cash_flow(ctx: Context) -> Metric:
    if not ctx.months:
        return unavailable(NET_CASH_FLOW, ctx.as_of_period(), "insufficient_data", NO_MONTH)
    m = ctx.months[-1]
    recent = ctx.window(RECENT_MONTHS)
    avg = Decimal(sum(ctx.net_cash_flow(x) for x in recent)) / len(recent)
    return available(
        NET_CASH_FLOW,
        inr(ctx.net_cash_flow(m)),
        Period(start=m, end=month_end(m), label=month_label(m)),
        components={
            "money_in": inr(ctx.credits[m]),
            "money_out": inr(ctx.debits[m]),
            "average_last_3_months": inr(int(avg)),
        },
        sources=[source("transactions", ctx.txns_in([m]), "All bank transactions in the month")],
    )


def _growth(ctx: Context, d_name: str, series: str) -> Metric:
    d = REVENUE_GROWTH if d_name == "revenue" else EXPENSE_GROWTH
    months = ctx.window(2 * GROWTH_WINDOW)
    if len(months) < 2 * GROWTH_WINDOW:
        period = ctx.months_period(months, "insufficient") if months else ctx.as_of_period()
        return unavailable(
            d,
            period,
            "insufficient_data",
            f"Needs {2 * GROWTH_WINDOW} complete months; have {len(ctx.months)}.",
        )
    value_of = ctx.revenue if series == "revenue" else ctx.expenses
    prior = sum(value_of(m) for m in months[:GROWTH_WINDOW])
    recent = sum(value_of(m) for m in months[GROWTH_WINDOW:])
    period = ctx.months_period(months, "last_3_months_vs_previous_3_months")
    components: dict[str, ComponentValue] = {
        "last_3_months": inr(recent),
        "previous_3_months": inr(prior),
    }
    if prior <= 0:
        return unavailable(
            d,
            period,
            "insufficient_data",
            "No activity in the earlier 3 months to compare against.",
            components=components,
        )
    confidence: Confidence = "high"
    notes: list[str] = []
    if series == "revenue" and not ctx.has_sales_documents:
        confidence, notes = "low", ["Revenue approximated by bank receipts."]
    return available(
        d,
        ratio(recent, prior) - 1,
        period,
        confidence=confidence,
        components=components,
        notes=notes,
    )


def revenue_growth(ctx: Context) -> Metric:
    return _growth(ctx, "revenue", "revenue")


def expense_growth(ctx: Context) -> Metric:
    return _growth(ctx, "expenses", "expenses")


def revenue_volatility(ctx: Context) -> Metric:
    months = ctx.window(VOLATILITY_MONTHS)
    confidence = months_confidence(len(months), 6, VOLATILITY_MIN)
    if confidence is None:
        return unavailable(
            REVENUE_VOLATILITY,
            ctx.months_period(months, "insufficient") if months else ctx.as_of_period(),
            "insufficient_data",
            f"Needs at least {VOLATILITY_MIN} complete months; have {len(months)}.",
        )
    values = [ctx.revenue(m) for m in months]
    period = ctx.months_period(months, f"last_{len(months)}_months")
    cv = coefficient_of_variation(values)
    if cv is None:
        return unavailable(REVENUE_VOLATILITY, period, "insufficient_data", "No revenue recorded.")
    mean = sum(values) // len(values)
    return available(
        REVENUE_VOLATILITY,
        cv,
        period,
        confidence=confidence if ctx.has_sales_documents else "low",
        components={
            "months": len(months),
            "mean_monthly_revenue": inr(mean),
            "lowest_month": inr(min(values)),
            "highest_month": inr(max(values)),
        },
    )


# --- cash & liquidity ---------------------------------------------------------------------------


def cash_balance(ctx: Context) -> Metric:
    if not ctx.txns:
        return unavailable(
            CASH_BALANCE,
            ctx.as_of_period(),
            "insufficient_data",
            "No transactions on or before as_of.",
        )
    balance = ctx.balance_at(ctx.as_of)
    return available(
        CASH_BALANCE,
        inr(balance),
        ctx.as_of_period(),
        components={
            "overdraft_limit": inr(ctx.overdraft_limit),
            "overdraft_drawn": inr(max(0, -balance)),
            "available_funds": inr(balance + ctx.overdraft_limit),
        },
        sources=[
            source("accounts", ctx.data.accounts, "Accounts (opening balance, overdraft limit)"),
            source("transactions", ctx.txns[-1:], "Latest transaction (running balance)"),
        ],
    )


def cash_runway(ctx: Context) -> Metric:
    months = ctx.window(RECENT_MONTHS)
    confidence = months_confidence(len(months), RECENT_MONTHS, 1)
    if confidence is None or not ctx.txns:
        return unavailable(CASH_RUNWAY, ctx.as_of_period(), "insufficient_data", NO_MONTH)
    average_net = Decimal(sum(ctx.net_cash_flow(m) for m in months)) / len(months)
    balance = ctx.balance_at(ctx.as_of)
    funds = balance + ctx.overdraft_limit
    period = ctx.months_period(months, f"last_{len(months)}_months_burn_to_as_of")
    components: dict[str, ComponentValue] = {
        "available_funds": inr(funds),
        "average_monthly_net_cash_flow": inr(int(average_net)),
    }
    if average_net >= 0:
        return unavailable(
            CASH_RUNWAY,
            period,
            "not_applicable",
            "Cash-generative over the period: no burn to run out of.",
            components=components,
        )
    value = Decimal(0) if funds <= 0 else Decimal(funds) / -average_net
    return available(CASH_RUNWAY, value, period, confidence=confidence, components=components)


def financial_buffer(ctx: Context) -> Metric:
    months = ctx.window(RECENT_MONTHS)
    confidence = months_confidence(len(months), RECENT_MONTHS, 1)
    if confidence is None or not ctx.txns:
        return unavailable(FINANCIAL_BUFFER, ctx.as_of_period(), "insufficient_data", NO_MONTH)
    outflow = Decimal(sum(ctx.debits[m] for m in months)) / len(months)
    cash = max(0, ctx.balance_at(ctx.as_of))
    period = ctx.months_period(months, f"last_{len(months)}_months_outflows_to_as_of")
    components: dict[str, ComponentValue] = {
        "own_cash": inr(cash),
        "average_monthly_outflows": inr(int(outflow)),
    }
    if outflow <= 0:
        return unavailable(
            FINANCIAL_BUFFER,
            period,
            "not_applicable",
            "No outflows recorded.",
            components=components,
        )
    return available(
        FINANCIAL_BUFFER, cash / outflow, period, confidence=confidence, components=components
    )


def liquidity_ratio(ctx: Context) -> Metric:
    if not ctx.txns:
        return unavailable(
            LIQUIDITY_RATIO,
            ctx.as_of_period(),
            "insufficient_data",
            "No transactions on or before as_of.",
        )
    as_of = ctx.as_of
    balance = ctx.balance_at(as_of)
    receivables = ctx.receivables_at(as_of)
    payables = ctx.payables_at(as_of)
    unpaid = [i for i in ctx.installments if i.paid_on is None or i.paid_on > as_of]
    overdue = sum(i.amount_minor for i in unpaid if i.due_on <= as_of)
    horizon = as_of + timedelta(days=365)
    principal_due = sum(i.principal_minor for i in unpaid if as_of < i.due_on <= horizon)
    assets = max(0, balance) + receivables
    liabilities = payables + max(0, -balance) + overdue + principal_due
    components: dict[str, ComponentValue] = {
        "cash": inr(max(0, balance)),
        "receivables": inr(receivables),
        "payables": inr(payables),
        "overdraft_drawn": inr(max(0, -balance)),
        "overdue_instalments": inr(overdue),
        "loan_principal_due_12_months": inr(principal_due),
    }
    if liabilities == 0:
        return unavailable(
            LIQUIDITY_RATIO,
            ctx.as_of_period(),
            "not_applicable",
            "No current liabilities.",
            components=components,
        )
    return available(
        LIQUIDITY_RATIO, ratio(assets, liabilities), ctx.as_of_period(), components=components
    )


# --- working capital ----------------------------------------------------------------------------


def _aging(ctx: Context, open_docs: list[tuple[Document, int]]) -> dict[str, ComponentValue]:
    buckets = {
        "not_yet_due": 0,
        "overdue_1_30_days": 0,
        "overdue_31_60_days": 0,
        "overdue_61_90_days": 0,
        "overdue_over_90_days": 0,
    }
    for doc, balance in open_docs:
        late = (ctx.as_of - doc.due_on).days
        key = (
            "not_yet_due"
            if late <= 0
            else "overdue_1_30_days"
            if late <= 30
            else "overdue_31_60_days"
            if late <= 60
            else "overdue_61_90_days"
            if late <= 90
            else "overdue_over_90_days"
        )
        buckets[key] += balance
    total = sum(buckets.values())
    out: dict[str, ComponentValue] = {k: inr(v) for k, v in buckets.items()}
    out["overdue_share"] = (
        (ratio(total - buckets["not_yet_due"], total)).quantize(Decimal("0.0001"))
        if total
        else Decimal(0)
    )
    out["open_documents"] = len(open_docs)
    return out


def receivables_outstanding(ctx: Context) -> Metric:
    if not ctx.invoices:
        return unavailable(
            RECEIVABLES,
            ctx.as_of_period(),
            "not_applicable",
            "No sales invoices: sales are settled immediately.",
        )
    open_docs = ctx.open_documents(ctx.invoices, ctx.invoice_payments, ctx.as_of)
    return available(
        RECEIVABLES,
        inr(sum(b for _, b in open_docs)),
        ctx.as_of_period(),
        components=_aging(ctx, open_docs),
        sources=[
            source("invoices", [d for d, _ in open_docs], "Invoices with an unpaid balance"),
            source("invoice_payments", ctx.invoice_payments, "Payments received by as_of"),
        ],
    )


def _turnover_days(ctx: Context, d_receivable: bool) -> Metric:
    d = RECEIVABLE_DAYS if d_receivable else PAYABLE_DAYS
    docs = ctx.invoices if d_receivable else ctx.bills
    if not docs:
        what = "sales invoices" if d_receivable else "supplier bills"
        return unavailable(d, ctx.as_of_period(), "not_applicable", f"No {what}.")
    days = ctx.covered_days(TURNOVER_DAYS)
    period = ctx.days_period(TURNOVER_DAYS)
    if days < 30:
        return unavailable(d, period, "insufficient_data", "Needs at least 30 days of history.")
    start = ctx.as_of - timedelta(days=days - 1)
    flow_docs = [x for x in docs if start <= x.issued_on <= ctx.as_of]
    flow = sum(x.total_minor for x in flow_docs)
    balance = ctx.receivables_at(ctx.as_of) if d_receivable else ctx.payables_at(ctx.as_of)
    components: dict[str, ComponentValue] = {
        "outstanding": inr(balance),
        "issued_in_period": inr(flow),
        "days_in_period": days,
    }
    label = "credit sales" if d_receivable else "purchases"
    table: SourceTable = "invoices" if d_receivable else "bills"
    sources = [source(table, flow_docs, f"Documents issued in the period ({label})")]
    if flow == 0:
        return unavailable(
            d,
            period,
            "insufficient_data",
            f"No {label} in the period.",
            components=components,
            sources=sources,
        )
    return available(
        d,
        ratio(balance, flow) * days,
        period,
        confidence="high" if days >= TURNOVER_DAYS else "medium",
        components=components,
        sources=sources,
    )


def receivable_days(ctx: Context) -> Metric:
    return _turnover_days(ctx, d_receivable=True)


def payable_days(ctx: Context) -> Metric:
    return _turnover_days(ctx, d_receivable=False)


# --- debt ---------------------------------------------------------------------------------------


def debt_outstanding(ctx: Context) -> Metric:
    as_of = ctx.as_of
    by_lender: dict[str, int] = defaultdict(int)
    total = 0
    for loan in ctx.loans:
        repaid = sum(
            i.principal_minor
            for i in ctx.installments
            if i.loan_id == loan.id and i.paid_on is not None and i.paid_on <= as_of
        )
        owed = loan.principal_minor - repaid
        total += owed
        party = ctx.parties.get(loan.lender_id)
        by_lender[party.name if party else str(loan.lender_id)] += owed
    components: dict[str, ComponentValue] = {"loans": len(ctx.loans)}
    components.update({f"lender:{name}": inr(v) for name, v in sorted(by_lender.items())})
    notes = [] if ctx.loans else ["No loans on record."]
    return available(
        DEBT_OUTSTANDING,
        inr(total),
        ctx.as_of_period(),
        components=components,
        sources=[
            source("loans", ctx.loans, "Loans disbursed by as_of"),
            source(
                "loan_installments",
                [i for i in ctx.installments if i.paid_on and i.paid_on <= as_of],
                "Instalments paid by as_of",
            ),
        ],
        notes=notes,
    )


def debt_service_burden(ctx: Context) -> Metric:
    months = ctx.window(RECENT_MONTHS)
    confidence = months_confidence(len(months), RECENT_MONTHS, 1)
    if confidence is None:
        return unavailable(DEBT_SERVICE_BURDEN, ctx.as_of_period(), "insufficient_data", NO_MONTH)
    start, end = months[0], month_end(months[-1])
    due = [i for i in ctx.installments if start <= i.due_on <= end]
    due_total = sum(i.amount_minor for i in due)
    receipts = sum(ctx.operating_inflows[m] for m in months)
    period = ctx.months_period(months, f"last_{len(months)}_months")
    components: dict[str, ComponentValue] = {
        "instalments_due": inr(due_total),
        "operating_receipts": inr(receipts),
        "instalments_paid": inr(sum(ctx.debt_service_paid[m] for m in months)),
    }
    sources = [source("loan_installments", due, "Instalments due in the period")]
    if receipts <= 0:
        return unavailable(
            DEBT_SERVICE_BURDEN,
            period,
            "insufficient_data",
            "No operating receipts in the period.",
            components=components,
            sources=sources,
        )
    notes = [] if ctx.loans else ["No loans on record."]
    return available(
        DEBT_SERVICE_BURDEN,
        ratio(due_total, receipts),
        period,
        confidence=confidence,
        components=components,
        sources=sources,
        notes=notes,
    )


# --- concentration ------------------------------------------------------------------------------


def _concentration(
    ctx: Context,
    d_customers: bool,
    amounts: dict[uuid.UUID, int],
    pooled: int,
    period: Period,
    confidence: Confidence,
    sources: list[SourceRef],
) -> Metric:
    d = CUSTOMER_CONCENTRATION if d_customers else SUPPLIER_CONCENTRATION
    total = sum(amounts.values()) + pooled
    if total <= 0:
        return unavailable(d, period, "insufficient_data", "No activity in the period.")
    ranked = sorted(amounts.items(), key=lambda kv: (-kv[1], str(kv[0])))
    top_id, top_amount = ranked[0] if ranked else (None, 0)
    party = ctx.parties.get(top_id) if top_id else None
    hhi = sum((ratio(v, total) ** 2 for _, v in ranked), Decimal(0))
    components: dict[str, ComponentValue] = {
        "largest": party.name if party else None,
        "top_3_share": ratio(sum(v for _, v in ranked[:3]), total).quantize(Decimal("0.0001")),
        "hhi": hhi.quantize(Decimal("0.0001")),
        "identified_count": len(ranked),
        "total": inr(total),
    }
    if d_customers:
        components["walk_in_share"] = ratio(pooled, total).quantize(Decimal("0.0001"))
    return available(
        d,
        ratio(top_amount, total),
        period,
        confidence=confidence,
        components=components,
        sources=sources,
    )


def customer_concentration(ctx: Context) -> Metric:
    months = ctx.window(CONCENTRATION_MONTHS)
    confidence = months_confidence(len(months), CONCENTRATION_MONTHS, CONCENTRATION_MIN)
    if confidence is None:
        return unavailable(
            CUSTOMER_CONCENTRATION,
            ctx.as_of_period(),
            "insufficient_data",
            f"Needs at least {CONCENTRATION_MIN} complete months.",
        )
    start, end = months[0], month_end(months[-1])
    period = ctx.months_period(months, f"last_{len(months)}_months")
    amounts: dict[uuid.UUID, int] = defaultdict(int)
    confidence_used: Confidence = confidence
    if ctx.has_sales_documents:
        invoices = [i for i in ctx.invoices if start <= i.issued_on <= end]
        for inv in invoices:
            amounts[inv.party_id] += inv.taxable_minor
        sales = [s for s in ctx.counter_sales if start <= s.sold_on <= end]
        pooled = sum(s.gross_minor - s.tax_minor for s in sales)
        sources = [
            source("invoices", invoices, "Invoices issued in the period"),
            source("counter_sales", sales, "Walk-in sales (pooled)"),
        ]
    else:
        receipts = [t for t in ctx.txns_in(months) if classify.is_operating_inflow(t.category)]
        pooled = 0
        for t in receipts:
            if t.counterparty_id is None:
                pooled += t.amount_minor
            else:
                amounts[t.counterparty_id] += t.amount_minor
        sources = [source("transactions", receipts, "Operating receipts by payer")]
        confidence_used = "low"
    return _concentration(ctx, True, amounts, pooled, period, confidence_used, sources)


def supplier_concentration(ctx: Context) -> Metric:
    months = ctx.window(CONCENTRATION_MONTHS)
    confidence = months_confidence(len(months), CONCENTRATION_MONTHS, CONCENTRATION_MIN)
    if confidence is None:
        return unavailable(
            SUPPLIER_CONCENTRATION,
            ctx.as_of_period(),
            "insufficient_data",
            f"Needs at least {CONCENTRATION_MIN} complete months.",
        )
    start, end = months[0], month_end(months[-1])
    period = ctx.months_period(months, f"last_{len(months)}_months")
    amounts: dict[uuid.UUID, int] = defaultdict(int)
    if ctx.has_bills:
        bills = [b for b in ctx.bills if start <= b.issued_on <= end]
        for b in bills:
            amounts[b.party_id] += b.taxable_minor
        sources = [source("bills", bills, "Supplier bills received in the period")]
    else:
        paid = [t for t in ctx.txns_in(months) if t.category == classify.SUPPLIER_PAYMENT]
        if not paid:
            return unavailable(
                SUPPLIER_CONCENTRATION,
                period,
                "not_applicable",
                "No suppliers: no supplier bills or supplier payments.",
            )
        unidentified = 0
        for t in paid:
            if t.counterparty_id is None:
                unidentified += -t.amount_minor
            else:
                amounts[t.counterparty_id] += -t.amount_minor
        sources = [source("transactions", paid, "Supplier payments by payee")]
        return _concentration(ctx, False, amounts, unidentified, period, confidence, sources)
    return _concentration(ctx, False, amounts, 0, period, confidence, sources)


# --- behaviour ----------------------------------------------------------------------------------


def income_stability(ctx: Context) -> Metric:
    months = ctx.window(STABILITY_MONTHS)
    confidence = months_confidence(len(months), STABILITY_MONTHS, STABILITY_MIN)
    if confidence is None:
        return unavailable(
            INCOME_STABILITY,
            ctx.as_of_period(),
            "insufficient_data",
            f"Needs at least {STABILITY_MIN} complete months.",
        )
    values = [ctx.operating_inflows[m] for m in months]
    period = ctx.months_period(months, f"last_{len(months)}_months")
    with_income = sum(1 for v in values if v > 0)
    cv = coefficient_of_variation(values)
    score = (
        Decimal(0)
        if cv is None
        else 100 * (1 - min(cv, Decimal(1))) * Decimal(with_income) / len(values)
    )
    return available(
        INCOME_STABILITY,
        score,
        period,
        confidence=confidence,
        components={
            "coefficient_of_variation": None if cv is None else cv.quantize(Decimal("0.0001")),
            "months_with_receipts": with_income,
            "months": len(values),
            "mean_monthly_receipts": inr(sum(values) // len(values)),
            "lowest_month": inr(min(values)),
            "highest_month": inr(max(values)),
        },
    )


def payment_consistency(ctx: Context) -> Metric:
    as_of = ctx.as_of
    if ctx.first_date is None:
        return unavailable(
            PAYMENT_CONSISTENCY,
            ctx.as_of_period(),
            "insufficient_data",
            "No transactions on or before as_of.",
        )
    start = max(ctx.first_date, as_of - timedelta(days=364))
    period = Period(start=start, end=as_of, label="last_12_months")

    instalments = [i for i in ctx.installments if start <= i.due_on <= as_of]
    emi_on_time = sum(
        1 for i in instalments if i.paid_on is not None and i.paid_on <= i.due_on and not i.bounces
    )
    emi_overdue = sum(1 for i in instalments if i.paid_on is None or i.paid_on > as_of)
    grace = timedelta(days=BILL_GRACE_DAYS)
    bills = [b for b in ctx.bills if start <= b.due_on and b.due_on + grace <= as_of]
    bills_on_time = 0
    for b in bills:
        deadline = b.due_on + grace
        paid = sum(
            p.amount_minor
            for p in ctx.bill_payments
            if p.document_id == b.id and p.paid_on <= deadline
        )
        bills_on_time += paid >= b.total_minor
    bounces = [t for t in ctx.txns if t.posted_on >= start and t.category == classify.BOUNCE_CHARGE]

    rates = []
    if instalments:
        rates.append(ratio(emi_on_time, len(instalments)))
    if bills:
        rates.append(ratio(bills_on_time, len(bills)))
    components: dict[str, ComponentValue] = {
        "instalments_due": len(instalments),
        "instalments_on_time": emi_on_time,
        "instalments_paid_late": len(instalments) - emi_on_time - emi_overdue,
        "instalments_overdue": emi_overdue,
        "bounce_charges": len(bounces),
        "bills_due": len(bills),
        "bills_paid_on_time": bills_on_time,
    }
    sources = [
        source("loan_installments", instalments, "Instalments due in the period"),
        source("bills", bills, "Supplier bills due in the period"),
    ]
    if not rates:
        return unavailable(
            PAYMENT_CONSISTENCY,
            period,
            "not_applicable",
            "No scheduled obligations (loan instalments or supplier bills).",
            components=components,
        )
    covered_months = (as_of - start).days / 30.4
    return available(
        PAYMENT_CONSISTENCY,
        sum(rates, Decimal(0)) / len(rates),
        period,
        confidence="high" if covered_months >= 6 else "medium",
        components=components,
        sources=sources,
    )


def transaction_consistency(ctx: Context) -> Metric:
    if ctx.first_date is None:
        return unavailable(
            TRANSACTION_CONSISTENCY,
            ctx.as_of_period(),
            "insufficient_data",
            "No transactions on or before as_of.",
        )
    weeks: list[tuple[date, date]] = []
    for k in range(CONSISTENCY_WEEKS):
        end = ctx.as_of - timedelta(days=7 * k)
        start = end - timedelta(days=6)
        if start < ctx.first_date:
            break
        weeks.append((start, end))
    weeks.reverse()
    period = ctx.days_period(7 * CONSISTENCY_WEEKS)
    if len(weeks) < CONSISTENCY_MIN_WEEKS:
        return unavailable(
            TRANSACTION_CONSISTENCY,
            period,
            "insufficient_data",
            f"Needs {CONSISTENCY_MIN_WEEKS} full weeks of history.",
        )
    window_start = weeks[0][0]
    txns = [t for t in ctx.txns if t.posted_on >= window_start]
    counts = [sum(1 for t in txns if s <= t.posted_on <= e) for s, e in weeks]
    receipts = sorted({t.posted_on for t in txns if classify.is_operating_inflow(t.category)})
    active = sum(1 for s, e in weeks if any(s <= d <= e for d in receipts))
    weekly_cv = coefficient_of_variation(counts)
    # No transactions at all → treat as maximally irregular (note: a CV of exactly 0 is valid).
    cv = Decimal(1) if weekly_cv is None else weekly_cv
    gaps = [
        (b - a).days for a, b in zip([window_start, *receipts], [*receipts, ctx.as_of], strict=True)
    ]
    score = 100 * Decimal(active) / len(weeks) * (1 - Decimal("0.5") * min(cv, Decimal(1)))
    return available(
        TRANSACTION_CONSISTENCY,
        score,
        Period(start=window_start, end=ctx.as_of, label=f"last_{len(weeks)}_weeks"),
        confidence="high" if len(weeks) == CONSISTENCY_WEEKS else "medium",
        components={
            "weeks": len(weeks),
            "weeks_with_receipts": active,
            "transactions": len(txns),
            "weekly_count_cv": cv.quantize(Decimal("0.0001")),
            "longest_gap_without_receipts_days": max(gaps),
        },
        sources=[source("transactions", txns, "Transactions in the window")],
    )


ALL_METRICS = (
    revenue_monthly,
    expenses_monthly,
    net_cash_flow,
    revenue_growth,
    revenue_volatility,
    expense_growth,
    cash_balance,
    cash_runway,
    receivables_outstanding,
    receivable_days,
    payable_days,
    debt_outstanding,
    debt_service_burden,
    customer_concentration,
    supplier_concentration,
    income_stability,
    payment_consistency,
    liquidity_ratio,
    financial_buffer,
    transaction_consistency,
)
