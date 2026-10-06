"""Rapid Mobile Hub — a high-risk MSME.

A mobile-phone and accessories shop in Delhi's Laxmi Nagar running on thin margins and volatile
sales. It lives in its overdraft, regularly withdraws large amounts of cash, sells on credit to
resellers who pay late and in parts, and keeps itself going by taking one digital loan after
another. Auto-debits bounce throughout. This is chronic risk rather than a sudden decline.
"""

from datetime import date

from finpulse.core.money import rupees
from finpulse.synthetic.categories import Category, Channel, CounterpartyKind
from finpulse.synthetic.spec import (
    AccountSpec,
    CounterSalesSpec,
    CustomerSpec,
    EmployeeSpec,
    LoanSpec,
    OwnerSpec,
    RecurringExpenseSpec,
    ScenarioSpec,
    SupplierSpec,
    TaxSpec,
    VariableExpenseSpec,
)

RAPID_MOBILE_HUB = ScenarioSpec(
    code="rapid_mobile_hub",
    display_name="Rapid Mobile Hub",
    kind="business",
    archetype="high_risk_msme",
    segment="mobile_phone_retail",
    narrative=__doc__.split("\n\n", 1)[1].strip().replace("\n", " "),
    start=date(2025, 7, 1),
    months=15,
    seed=2025_0701,
    profile={
        "legal_form": "proprietorship",
        "owner": "Vikas Malhotra",
        "city": "Delhi",
        "sector": "Mobile phones & accessories retail",
        "years_in_business": 3,
        "employees": 4,
        "gst_registered": True,
    },
    account=AccountSpec(
        institution="Yamuna Urban Bank",
        opening_balance=rupees(40_000),
        overdraft_limit=rupees(250_000),
        overdraft_rate=0.15,
        branch="Laxmi Nagar",
    ),
    owner=OwnerSpec(name="Vikas Malhotra", monthly_drawings=rupees(40_000), min_buffer=0),
    invoice_prefix="RMH",
    counter_sales=CounterSalesSpec(daily_mean=rupees(55_000), cv=0.55, upi_share=0.5),
    customers=(
        CustomerSpec(
            "phone_point",
            "Phone Point Resellers",
            rupees(90_000),
            3,
            terms_days=15,
            pay_delay_mean_days=20,
            pay_delay_sd_days=15,
            partial_payment_prob=0.4,
        ),
        CustomerSpec(
            "galaxy_mobiles",
            "Galaxy Mobiles Shahdara",
            rupees(60_000),
            2,
            terms_days=15,
            pay_delay_mean_days=25,
            pay_delay_sd_days=20,
            partial_payment_prob=0.5,
        ),
    ),
    seasonality=(0.85, 0.85, 0.95, 0.95, 1.0, 1.0, 0.95, 1.0, 1.05, 1.25, 1.3, 0.95),
    cogs_ratio=0.87,
    suppliers=(
        SupplierSpec(
            "distributor",
            "Metro Mobile Distributors",
            0.75,
            bill_every_days=5,
            terms_days=10,
            pay_delay_mean_days=4,
            pay_delay_sd_days=4,
        ),
        SupplierSpec(
            "accessories",
            "Gaffar Market Accessories",
            0.25,
            bill_every_days=7,
            terms_days=7,
            channel=Channel.UPI,
        ),
    ),
    employees=tuple(
        EmployeeSpec(f"e{i}", name, rupees(14_000))
        for i, name in enumerate(["Rohit Kumar", "Aman Gupta", "Sahil Khan", "Deepak Rawat"], 1)
    ),
    recurring_expenses=(
        RecurringExpenseSpec(
            "rent",
            "Bansal Market Association",
            Category.RENT,
            rupees(70_000),
            5,
            kind=CounterpartyKind.LANDLORD,
            priority=3,
        ),
        RecurringExpenseSpec(
            "power",
            "Delhi Power Distribution",
            Category.ELECTRICITY,
            rupees(12_000),
            12,
            cv=0.15,
            channel=Channel.BILLPAY,
            kind=CounterpartyKind.UTILITY,
        ),
    ),
    variable_expenses=(
        VariableExpenseSpec(
            "atm",
            "ATM cash withdrawal",
            Category.CASH_WITHDRAWAL,
            rupees(110_000),
            8,
            cv=0.5,
            channel=Channel.CASH,
            kind=CounterpartyKind.SELF,
            round_to=500,
        ),
        VariableExpenseSpec(
            "gaming", "FantasyKing Gaming", Category.BETTING, rupees(15_000), 5, cv=0.8
        ),
        VariableExpenseSpec("courier", "Swift Couriers", Category.FREIGHT, rupees(6_000), 6),
    ),
    loans=(
        LoanSpec(
            "bank_loan",
            "Yamuna Urban Bank",
            "term_loan",
            rupees(600_000),
            0.16,
            36,
            disburse_month=-6,
            emi_day=10,
            represent_after_days=3,
        ),
        LoanSpec(
            "quickcred",
            "QuickCred Finance",
            "digital_unsecured",
            rupees(200_000),
            0.28,
            9,
            disburse_month=2,
            disburse_day=14,
            emi_day=4,
            reports_to_bureau=False,
            processing_fee_rate=0.03,
        ),
        LoanSpec(
            "paisa_turant",
            "Paisa Turant NBFC",
            "digital_unsecured",
            rupees(150_000),
            0.32,
            6,
            disburse_month=6,
            disburse_day=9,
            emi_day=8,
            processing_fee_rate=0.03,
        ),
        LoanSpec(
            "loanjet",
            "LoanJet",
            "digital_unsecured",
            rupees(250_000),
            0.30,
            12,
            disburse_month=9,
            disburse_day=20,
            emi_day=1,
            reports_to_bureau=False,
            processing_fee_rate=0.035,
        ),
    ),
    tax=TaxSpec(gst_rate=0.18),
)
