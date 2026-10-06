"""Annapurna Home Kitchen — a thin-file but financially healthy MSME.

A cloud kitchen in Pune started a year ago by Meera Iyer. It has never borrowed, so a credit
bureau has nothing on it — no score at all. Its bank account tells a clear story: weekly payouts
from two food-delivery platforms, a monthly corporate catering contract and direct UPI orders,
growing quickly, with ingredients and staff paid on time and a growing cash buffer.
"""

from datetime import date

from finpulse.core.money import rupees
from finpulse.synthetic.categories import Category, Channel, CounterpartyKind
from finpulse.synthetic.spec import (
    AccountSpec,
    CounterSalesSpec,
    CustomerSpec,
    EmployeeSpec,
    OwnerSpec,
    RecurringExpenseSpec,
    ScenarioSpec,
    SupplierSpec,
    TaxSpec,
    VariableExpenseSpec,
)

ANNAPURNA_KITCHEN = ScenarioSpec(
    code="annapurna_kitchen",
    display_name="Annapurna Home Kitchen",
    kind="business",
    archetype="thin_file_msme",
    segment="cloud_kitchen",
    narrative=__doc__.split("\n\n", 1)[1].strip().replace("\n", " "),
    start=date(2025, 10, 1),
    months=12,
    seed=2025_10,
    profile={
        "legal_form": "proprietorship",
        "owner": "Meera Iyer",
        "city": "Pune",
        "sector": "Cloud kitchen / tiffin services",
        "years_in_business": 1,
        "employees": 3,
        "gst_registered": True,
    },
    account=AccountSpec(
        institution="Sahyadri Co-operative Bank", opening_balance=rupees(180_000), branch="Baner"
    ),
    owner=OwnerSpec(name="Meera Iyer", monthly_drawings=rupees(55_000), min_buffer=rupees(60_000)),
    invoice_prefix="AHK",
    counter_sales=CounterSalesSpec(
        daily_mean=rupees(3_000),
        cv=0.4,
        upi_share=0.95,
        closed_weekdays=frozenset({0}),
        cash_deposit_weekdays=frozenset({5}),
        settlement_provider="PAYZAP",
    ),
    customers=(
        CustomerSpec(
            "swiggo",
            "Swiggo Food Delivery",
            rupees(220_000),
            4.3,
            terms_days=7,
            pay_delay_mean_days=0,
            pay_delay_sd_days=0.5,
            amount_cv=0.15,
            kind=CounterpartyKind.PLATFORM,
            category=Category.PLATFORM_PAYOUT,
        ),
        CustomerSpec(
            "zesteats",
            "ZestEats",
            rupees(140_000),
            4.3,
            terms_days=7,
            pay_delay_mean_days=1,
            pay_delay_sd_days=0.5,
            amount_cv=0.18,
            kind=CounterpartyKind.PLATFORM,
            category=Category.PLATFORM_PAYOUT,
        ),
        CustomerSpec(
            "brightline",
            "Brightline Tech Park Cafeteria",
            rupees(60_000),
            1,
            terms_days=15,
            amount_cv=0.08,
        ),
    ),
    monthly_growth=0.035,
    cogs_ratio=0.58,
    suppliers=(
        SupplierSpec(
            "veg",
            "Market Yard Vegetable Wholesale",
            0.45,
            bill_every_days=3,
            terms_days=2,
            pay_delay_sd_days=0.5,
            channel=Channel.UPI,
        ),
        SupplierSpec(
            "dairy",
            "Chitale Dairy Distributors",
            0.25,
            bill_every_days=7,
            terms_days=7,
            channel=Channel.UPI,
        ),
        SupplierSpec("grocery", "Pune Grain Traders", 0.20, bill_every_days=10, terms_days=10),
        SupplierSpec("packaging", "EcoPack Containers", 0.10, bill_every_days=15, terms_days=15),
    ),
    employees=(
        EmployeeSpec("e1", "Sunita Pawar", rupees(16_000)),
        EmployeeSpec("e2", "Rekha Jadhav", rupees(14_000)),
        EmployeeSpec("e3", "Ganesh Shinde", rupees(11_000)),
    ),
    recurring_expenses=(
        RecurringExpenseSpec(
            "rent",
            "Deshmukh Properties",
            Category.RENT,
            rupees(28_000),
            5,
            kind=CounterpartyKind.LANDLORD,
            priority=3,
        ),
        RecurringExpenseSpec(
            "power",
            "Maharashtra Power Distribution",
            Category.ELECTRICITY,
            rupees(6_500),
            14,
            cv=0.1,
            channel=Channel.BILLPAY,
            kind=CounterpartyKind.UTILITY,
        ),
        RecurringExpenseSpec(
            "telecom",
            "Skyline Telecom",
            Category.TELECOM,
            rupees(800),
            8,
            channel=Channel.BILLPAY,
            kind=CounterpartyKind.UTILITY,
        ),
    ),
    variable_expenses=(
        VariableExpenseSpec("lpg", "Pune Gas Agency", Category.FUEL, rupees(4_500), 2, cv=0.1),
        VariableExpenseSpec(
            "delivery", "Local delivery partners", Category.FREIGHT, rupees(5_000), 12
        ),
    ),
    tax=TaxSpec(gst_rate=0.05),
)
