"""Ananya Rao — an independent UX design consultant (freelancer).

A Bengaluru-based designer with one steady monthly retainer, a UK studio that sends occasional
larger projects and pays slowly, and a start-up client that sometimes pays in parts. Income is
lumpy month to month but adequate; she rents, invests through a monthly SIP, pays advance tax
each quarter and repays a small laptop loan on time. Not GST-registered (below the threshold).
"""

from datetime import date

from finpulse.core.money import rupees
from finpulse.synthetic.categories import Category, Channel, CounterpartyKind
from finpulse.synthetic.spec import (
    AccountSpec,
    CustomerSpec,
    LoanSpec,
    OwnerSpec,
    RecurringExpenseSpec,
    ScenarioSpec,
    TaxSpec,
    VariableExpenseSpec,
)

ANANYA_RAO_DESIGN = ScenarioSpec(
    code="ananya_rao_design",
    display_name="Ananya Rao (UX design consultant)",
    kind="individual",
    archetype="freelancer",
    segment="independent_professional",
    narrative=__doc__.split("\n\n", 1)[1].strip().replace("\n", " "),
    start=date(2025, 8, 1),
    months=14,
    seed=2025_08,
    profile={
        "occupation": "UX design consultant",
        "city": "Bengaluru",
        "years_freelancing": 4,
        "gst_registered": False,
    },
    account=AccountSpec(
        institution="Nandi Savings Bank",
        kind="bank_savings",
        opening_balance=rupees(240_000),
        branch="Indiranagar",
    ),
    owner=OwnerSpec(name="Ananya Rao"),
    invoice_prefix="AR",
    customers=(
        CustomerSpec(
            "northwind",
            "Northwind Fintech",
            rupees(75_000),
            1,
            terms_days=15,
            pay_delay_mean_days=3,
            amount_cv=0.02,
            category=Category.CLIENT_PAYMENT,
        ),
        CustomerSpec(
            "bluepeak",
            "Bluepeak Studio Ltd",
            rupees(45_000),
            0.5,
            terms_days=30,
            pay_delay_mean_days=10,
            pay_delay_sd_days=10,
            amount_cv=0.5,
            category=Category.CLIENT_PAYMENT,
        ),
        CustomerSpec(
            "kirana_cloud",
            "Kirana Cloud",
            rupees(25_000),
            0.7,
            terms_days=30,
            pay_delay_mean_days=15,
            pay_delay_sd_days=8,
            amount_cv=0.4,
            partial_payment_prob=0.2,
            channel=Channel.IMPS,
            category=Category.CLIENT_PAYMENT,
        ),
    ),
    recurring_expenses=(
        RecurringExpenseSpec(
            "rent",
            "Prakash Reddy",
            Category.HOUSING_RENT,
            rupees(32_000),
            3,
            kind=CounterpartyKind.LANDLORD,
            priority=3,
        ),
        RecurringExpenseSpec(
            "power",
            "Bengaluru Electricity Supply",
            Category.ELECTRICITY,
            rupees(1_800),
            12,
            cv=0.15,
            channel=Channel.BILLPAY,
            kind=CounterpartyKind.UTILITY,
        ),
        RecurringExpenseSpec(
            "internet",
            "Skyline Telecom",
            Category.TELECOM,
            rupees(1_500),
            8,
            channel=Channel.BILLPAY,
            kind=CounterpartyKind.UTILITY,
        ),
        RecurringExpenseSpec(
            "sip",
            "Horizon Mutual Fund SIP",
            Category.INVESTMENT,
            rupees(15_000),
            10,
            channel=Channel.NACH,
            priority=5,
        ),
        RecurringExpenseSpec(
            "software",
            "DesignTools Subscription",
            Category.SOFTWARE,
            rupees(3_500),
            18,
            channel=Channel.CARD,
        ),
    ),
    variable_expenses=(
        VariableExpenseSpec("groceries", "FreshBasket", Category.GROCERIES, rupees(9_000), 8),
        VariableExpenseSpec("dining", "Restaurants & cafés", Category.DINING, rupees(6_000), 6),
        VariableExpenseSpec(
            "transport", "Ride-hailing & metro", Category.TRANSPORT, rupees(4_000), 10
        ),
        VariableExpenseSpec(
            "shopping",
            "Online shopping",
            Category.SHOPPING,
            rupees(7_000),
            3,
            cv=0.7,
            channel=Channel.CARD,
        ),
        VariableExpenseSpec(
            "health", "Pharmacy & clinic", Category.HEALTH, rupees(2_000), 1, cv=0.6
        ),
    ),
    loans=(
        LoanSpec(
            "laptop",
            "Zenith Consumer Finance",
            "consumer_durable",
            rupees(120_000),
            0.14,
            12,
            disburse_month=3,
            disburse_day=12,
            emi_day=5,
            processing_fee_rate=0.0,
        ),
    ),
    tax=TaxSpec(advance_tax_rate=0.08),
)
