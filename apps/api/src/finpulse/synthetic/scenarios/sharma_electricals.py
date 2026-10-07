"""Sharma Electricals — the primary demo entity: an MSME whose growth is quietly draining its cash.

An electrical goods shop in Lucknow that also supplies contractors and builders. It has little
traditional credit history: one small equipment loan from its bank, always paid on time, is all a
credit bureau would see. Through 2025 it is a sound, steadily growing business with about ₹12–13
lakh in the bank. From December 2025 its largest customer, Shree Ganesh Builders, scales up a
housing project and more than doubles its orders over the next ten months, so revenue keeps
growing (about ₹9.5 lakh a month in 2025, ₹13.4 lakh by September 2026) and the builder becomes
more than a third of sales. But the builder pays a little later every two months — by August 2026
about 15 days past its 30-day terms — and from June the other customers drift a few days later
too. Receivables more than double, collection time stretches from about 30 to about 46 days, and
cash falls to about ₹7.4 lakh as the business funds its customers' working capital. Nothing has
gone wrong yet: every instalment and supplier bill is paid, and the six-month outlook is
comfortable unless the builder stops paying.
"""

from datetime import date

from finpulse.core.money import rupees
from finpulse.synthetic.categories import Category, Channel, CounterpartyKind
from finpulse.synthetic.spec import (
    AccountSpec,
    CounterSalesSpec,
    CustomerSpec,
    CustomerVolumeShock,
    EmployeeSpec,
    LoanSpec,
    OwnerSpec,
    PaymentDelayShock,
    RecurringExpenseSpec,
    ScenarioSpec,
    SupplierSpec,
    TaxSpec,
    VariableExpenseSpec,
)

# Lucknow electricals: a mild summer peak (fans, coolers), monsoon dip and festive peak (Diwali).
SEASONALITY = (0.96, 0.95, 1.00, 1.04, 1.08, 1.06, 0.97, 0.95, 0.98, 1.05, 1.08, 0.98)
SUMMER_POWER = (0.8, 0.8, 0.9, 1.1, 1.4, 1.5, 1.3, 1.2, 1.1, 0.9, 0.8, 0.8)

SHARMA_ELECTRICALS = ScenarioSpec(
    code="sharma_electricals",
    display_name="Sharma Electricals",
    kind="business",
    archetype="strained_msme",
    segment="electrical_retail_and_contract_supply",
    narrative=__doc__.split("\n\n", 1)[1].strip().replace("\n", " "),
    start=date(2025, 4, 1),
    months=18,
    seed=2025_04,
    profile={
        "legal_form": "proprietorship",
        "owner": "Rakesh Sharma",
        "city": "Lucknow",
        "sector": "Electrical goods retail & contractor supply",
        "years_in_business": 9,
        "employees": 3,
        "gst_registered": True,
        "credit_history": "thin: one bank equipment loan since 2024",
    },
    account=AccountSpec(
        institution="Ganga Valley Bank",
        opening_balance=rupees(1_100_000),
        overdraft_limit=rupees(500_000),
        overdraft_rate=0.13,
        branch="Aminabad",
    ),
    owner=OwnerSpec(
        name="Rakesh Sharma", monthly_drawings=rupees(85_000), min_buffer=rupees(100_000)
    ),
    invoice_prefix="SE",
    counter_sales=CounterSalesSpec(daily_mean=rupees(18_000), cv=0.35, upi_share=0.62),
    customers=(
        CustomerSpec(
            "shree_ganesh",
            "Shree Ganesh Builders",
            rupees(260_000),
            5,
            terms_days=30,
            pay_delay_mean_days=2,
            pay_delay_sd_days=3,
        ),
        CustomerSpec(
            "verma_contractors",
            "Verma Electrical Contractors",
            rupees(140_000),
            6,
            terms_days=15,
            pay_delay_mean_days=2,
        ),
        CustomerSpec(
            "lucknow_public_school",
            "Lucknow Public School",
            rupees(45_000),
            1,
            terms_days=45,
            pay_delay_mean_days=10,
            pay_delay_sd_days=6,
            amount_cv=0.5,
        ),
        CustomerSpec(
            "aakash_interiors",
            "Aakash Interiors",
            rupees(80_000),
            3,
            terms_days=30,
            partial_payment_prob=0.1,
        ),
        CustomerSpec(
            "nirmal_hospital",
            "Nirmal City Hospital",
            rupees(60_000),
            2,
            terms_days=30,
            pay_delay_mean_days=5,
            channel=Channel.RTGS,
        ),
    ),
    seasonality=SEASONALITY,
    monthly_growth=0.010,
    cogs_ratio=0.78,
    suppliers=(
        SupplierSpec(
            "agarwal", "Agarwal Electric Distributors", 0.45, bill_every_days=7, terms_days=30
        ),
        SupplierSpec(
            "mehta_cables", "Mehta Wires & Cables", 0.35, bill_every_days=10, terms_days=45
        ),
        SupplierSpec(
            "northern_switchgear",
            "Northern Switchgear Traders",
            0.20,
            bill_every_days=14,
            terms_days=21,
        ),
    ),
    employees=(
        EmployeeSpec("e1", "Sunil Yadav", rupees(18_000)),
        EmployeeSpec("e2", "Imran Khan", rupees(16_000)),
        EmployeeSpec("e3", "Pappu Verma", rupees(13_000)),
    ),
    recurring_expenses=(
        RecurringExpenseSpec(
            "rent",
            "Kapoor Properties",
            Category.RENT,
            rupees(48_000),
            5,
            kind=CounterpartyKind.LANDLORD,
            priority=3,
        ),
        RecurringExpenseSpec(
            "power",
            "Madhyanchal Power",
            Category.ELECTRICITY,
            rupees(9_000),
            12,
            cv=0.1,
            channel=Channel.BILLPAY,
            kind=CounterpartyKind.UTILITY,
            month_multipliers=SUMMER_POWER,
        ),
        RecurringExpenseSpec(
            "telecom",
            "Skyline Telecom",
            Category.TELECOM,
            rupees(1_200),
            8,
            channel=Channel.BILLPAY,
            kind=CounterpartyKind.UTILITY,
        ),
        RecurringExpenseSpec(
            "accountant", "Tandon & Associates", Category.PROFESSIONAL_FEES, rupees(6_000), 10
        ),
    ),
    variable_expenses=(
        VariableExpenseSpec("fuel", "City Fuels", Category.FUEL, rupees(8_000), 6),
        VariableExpenseSpec(
            "freight", "Shiv Shakti Transport", Category.FREIGHT, rupees(12_000), 4
        ),
        VariableExpenseSpec(
            "repairs", "Local repairs", Category.MAINTENANCE, rupees(4_000), 2, cv=0.6
        ),
    ),
    loans=(
        LoanSpec(
            "equipment_loan",
            "Ganga Valley Bank",
            "equipment_loan",
            rupees(350_000),
            0.11,
            36,
            disburse_month=-6,
            emi_day=5,
            represent_after_days=4,
        ),
    ),
    tax=TaxSpec(gst_rate=0.18),
    shocks=(
        # The builder's housing project: orders ramp up to 2.2× over ten months.
        CustomerVolumeShock(
            "shree_ganesh",
            start_month=8,
            factor=2.2,
            ramp_months=10,
            deterioration=False,
            mechanism="customer_concentration_growth",
        ),
        # ...and it pays a little later every two months (cumulative: 3, 7, 11, 15 days late).
        PaymentDelayShock(start_month=10, extra_days=3, customer="shree_ganesh"),
        PaymentDelayShock(start_month=12, extra_days=4, customer="shree_ganesh"),
        PaymentDelayShock(start_month=14, extra_days=4, customer="shree_ganesh"),
        PaymentDelayShock(start_month=16, extra_days=4, customer="shree_ganesh"),
        # Other customers drift a few days later from June.
        PaymentDelayShock(start_month=14, extra_days=2),
        PaymentDelayShock(start_month=16, extra_days=2),
    ),
)
