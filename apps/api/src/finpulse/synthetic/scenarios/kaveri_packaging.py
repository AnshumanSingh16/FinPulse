"""Kaveri Packaging Solutions — a healthy MSME.

A corrugated-box maker in Coimbatore selling to a diversified set of FMCG, textile and
pharmaceutical customers on 30–45 day terms. Steady growth, punctual customers, a bank equipment
loan that is always paid on time and an overdraft line it rarely touches.
"""

from datetime import date

from finpulse.core.money import rupees
from finpulse.synthetic.categories import Category, Channel, CounterpartyKind
from finpulse.synthetic.spec import (
    AccountSpec,
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

KAVERI_PACKAGING = ScenarioSpec(
    code="kaveri_packaging",
    display_name="Kaveri Packaging Solutions",
    kind="business",
    archetype="healthy_msme",
    segment="packaging_manufacturer",
    narrative=__doc__.split("\n\n", 1)[1].strip().replace("\n", " "),
    start=date(2025, 7, 1),
    months=15,
    seed=2025_07,
    profile={
        "legal_form": "partnership",
        "owner": "S. Lakshmi & R. Venkatesh",
        "city": "Coimbatore",
        "sector": "Corrugated packaging manufacturing",
        "years_in_business": 12,
        "employees": 9,
        "gst_registered": True,
    },
    account=AccountSpec(
        institution="Cauvery Commercial Bank",
        opening_balance=rupees(2_000_000),
        overdraft_limit=rupees(1_000_000),
        overdraft_rate=0.105,
        branch="Peelamedu",
    ),
    owner=OwnerSpec(
        name="Kaveri Partners", monthly_drawings=rupees(120_000), min_buffer=rupees(600_000)
    ),
    invoice_prefix="KPS",
    customers=(
        CustomerSpec("annam_foods", "Annam Foods Pvt Ltd", rupees(650_000), 4, terms_days=30),
        CustomerSpec(
            "tirupur_knits",
            "Tirupur Knit Exports",
            rupees(520_000),
            3,
            terms_days=45,
            pay_delay_mean_days=2,
        ),
        CustomerSpec(
            "medipharm",
            "MediPharm Laboratories",
            rupees(480_000),
            4,
            terms_days=30,
            channel=Channel.RTGS,
        ),
        CustomerSpec(
            "sri_ganga_dairy",
            "Sri Ganga Dairy",
            rupees(420_000),
            6,
            terms_days=30,
            pay_delay_mean_days=-2,
        ),
        CustomerSpec(
            "velan_spices", "Velan Spices", rupees(360_000), 3, terms_days=30, pay_delay_mean_days=1
        ),
        CustomerSpec("kovai_pumps", "Kovai Pumps & Motors", rupees(330_000), 2, terms_days=45),
        CustomerSpec(
            "southern_ceramics",
            "Southern Ceramics",
            rupees(240_000),
            2,
            terms_days=30,
            pay_delay_mean_days=4,
        ),
        CustomerSpec("green_leaf_tea", "Green Leaf Tea Co.", rupees(200_000), 2, terms_days=30),
    ),
    seasonality=(1.0, 0.95, 1.05, 0.95, 0.95, 1.0, 1.0, 1.05, 1.05, 1.1, 1.05, 0.9),
    monthly_growth=0.01,
    cogs_ratio=0.74,
    suppliers=(
        SupplierSpec(
            "paper_mill",
            "Bhavani Kraft Paper Mills",
            0.70,
            bill_every_days=7,
            terms_days=30,
            channel=Channel.RTGS,
        ),
        SupplierSpec("starch", "Erode Starch & Adhesives", 0.15, bill_every_days=14, terms_days=30),
        SupplierSpec("inks", "Prime Inks & Coatings", 0.15, bill_every_days=15, terms_days=45),
    ),
    employees=tuple(
        EmployeeSpec(f"e{i}", name, rupees(salary))
        for i, (name, salary) in enumerate(
            [
                ("M. Karthik", 32_000),
                ("P. Selvi", 26_000),
                ("R. Murugan", 22_000),
                ("A. Prakash", 20_000),
                ("K. Devi", 18_000),
                ("S. Arun", 18_000),
                ("V. Ganesan", 17_000),
                ("T. Mani", 16_000),
                ("J. Ravi", 16_000),
            ],
            start=1,
        )
    ),
    recurring_expenses=(
        RecurringExpenseSpec(
            "rent",
            "Ramaswamy Estates",
            Category.RENT,
            rupees(85_000),
            5,
            kind=CounterpartyKind.LANDLORD,
            priority=3,
        ),
        RecurringExpenseSpec(
            "power",
            "Tamil Nadu Power Distribution",
            Category.ELECTRICITY,
            rupees(45_000),
            15,
            cv=0.08,
            channel=Channel.BILLPAY,
            kind=CounterpartyKind.UTILITY,
        ),
        RecurringExpenseSpec(
            "telecom",
            "Skyline Telecom",
            Category.TELECOM,
            rupees(3_000),
            8,
            channel=Channel.BILLPAY,
            kind=CounterpartyKind.UTILITY,
        ),
        RecurringExpenseSpec(
            "auditor",
            "Natarajan & Co. Chartered Accountants",
            Category.PROFESSIONAL_FEES,
            rupees(15_000),
            10,
        ),
    ),
    variable_expenses=(
        VariableExpenseSpec(
            "freight", "KPN Logistics", Category.FREIGHT, rupees(60_000), 8, channel=Channel.NEFT
        ),
        VariableExpenseSpec(
            "maintenance",
            "Coimbatore Machine Works",
            Category.MAINTENANCE,
            rupees(25_000),
            2,
            cv=0.6,
            channel=Channel.NEFT,
        ),
        VariableExpenseSpec("fuel", "City Fuels", Category.FUEL, rupees(12_000), 6),
    ),
    loans=(
        LoanSpec(
            "equipment",
            "Cauvery Commercial Bank",
            "equipment_loan",
            rupees(1_500_000),
            0.105,
            60,
            disburse_month=-14,
            emi_day=7,
        ),
    ),
    tax=TaxSpec(gst_rate=0.12),
)
