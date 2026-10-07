"""Mehra Lighting & Electricals — a deteriorating MSME (sudden collapse).

An electrical goods shop in Kanpur that also supplies contractors and builders. For its first
seven months (April–October 2025) it is a sound business. From November 2025 its largest
customer, a builder whose project has stalled, first pays much later and then all but stops
ordering; copper-linked purchase costs rise; from February 2026 walk-in sales drift down as a
large-format store opens nearby, and other customers start paying later too. The owner bridges
the gap with two digital loans (February and May 2026) that do not report to the credit bureau,
stops taking drawings, stretches suppliers and lives in the overdraft. By September 2026 the
digital-loan auto-debits are bouncing. The credit bureau, which only sees the bank term loan —
still paid on time — shows a clean record throughout.
"""

from datetime import date

from finpulse.core.money import rupees
from finpulse.synthetic.categories import Category, Channel, CounterpartyKind
from finpulse.synthetic.spec import (
    AccountSpec,
    CostInflationShock,
    CounterSalesSpec,
    CustomerSpec,
    CustomerVolumeShock,
    EmployeeSpec,
    LoanSpec,
    OwnerSpec,
    PaymentDelayShock,
    RecurringExpenseSpec,
    SalesTrendShock,
    ScenarioSpec,
    SupplierSpec,
    TaxSpec,
    VariableExpenseSpec,
)

# Kanpur electricals: summer peak (fans, coolers), monsoon dip, festive peak (Diwali lighting).
SEASONALITY = (0.90, 0.90, 1.00, 1.10, 1.25, 1.20, 0.90, 0.85, 0.95, 1.15, 1.20, 0.95)
SUMMER_POWER = (0.8, 0.8, 0.9, 1.1, 1.4, 1.5, 1.3, 1.2, 1.1, 0.9, 0.8, 0.8)

MEHRA_LIGHTING = ScenarioSpec(
    code="mehra_lighting",
    display_name="Mehra Lighting & Electricals",
    kind="business",
    archetype="deteriorating_msme",
    segment="electrical_retail_and_contract_supply",
    narrative=__doc__.split("\n\n", 1)[1].strip().replace("\n", " "),
    start=date(2025, 4, 1),
    months=18,
    seed=2025_04,
    profile={
        "legal_form": "proprietorship",
        "owner": "Vikas Mehra",
        "city": "Kanpur",
        "sector": "Electrical goods retail & contractor supply",
        "years_in_business": 9,
        "employees": 3,
        "gst_registered": True,
    },
    account=AccountSpec(
        institution="Ganga Valley Bank",
        opening_balance=rupees(300_000),
        overdraft_limit=rupees(200_000),
        overdraft_rate=0.13,
        branch="Naveen Market",
    ),
    owner=OwnerSpec(
        name="Vikas Mehra", monthly_drawings=rupees(65_000), min_buffer=rupees(100_000)
    ),
    invoice_prefix="ML",
    counter_sales=CounterSalesSpec(daily_mean=rupees(18_000), cv=0.35, upi_share=0.62),
    customers=(
        CustomerSpec(
            "shree_ganesh",
            "Shree Ganesh Builders",
            rupees(320_000),
            5,
            terms_days=30,
            pay_delay_mean_days=3,
            pay_delay_sd_days=4,
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
    monthly_growth=0.006,
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
            "term_loan",
            "Ganga Valley Bank",
            "term_loan",
            rupees(800_000),
            0.115,
            48,
            disburse_month=-10,
            emi_day=5,
            represent_after_days=4,
        ),
        LoanSpec(
            "quickcred",
            "QuickCred Finance",
            "digital_unsecured",
            rupees(300_000),
            0.26,
            12,
            disburse_month=10,
            disburse_day=18,
            emi_day=3,
            reports_to_bureau=False,
            processing_fee_rate=0.025,
        ),
        LoanSpec(
            "rupiya_now",
            "Rupiya Now",
            "digital_unsecured",
            rupees(150_000),
            0.30,
            9,
            disburse_month=13,
            disburse_day=22,
            emi_day=2,
            reports_to_bureau=False,
            processing_fee_rate=0.03,
        ),
    ),
    tax=TaxSpec(gst_rate=0.18),
    shocks=(
        PaymentDelayShock(start_month=7, extra_days=45, customer="shree_ganesh"),
        CostInflationShock(start_month=8, cogs_ratio_delta=0.05),
        CustomerVolumeShock("shree_ganesh", start_month=9, factor=0.1, ramp_months=3),
        SalesTrendShock(start_month=10, monthly_change=-0.05),
        PaymentDelayShock(start_month=11, extra_days=15),
    ),
)
