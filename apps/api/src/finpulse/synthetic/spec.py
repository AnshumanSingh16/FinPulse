"""Scenario specifications: the knobs that describe a fictional entity.

A scenario is pure data. The engine (``engine.py``) turns it into a day-by-day simulation, so
every number in the output is a consequence of these parameters plus the seed. Amounts are in
minor units (use ``finpulse.core.money.rupees``); rates are fractions (0.18 = 18%).

Months are counted from the scenario start: month 0 is the first month of history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from finpulse.synthetic.categories import Category, Channel, CounterpartyKind

FLAT_SEASONALITY: tuple[float, ...] = (1.0,) * 12


@dataclass(frozen=True)
class AccountSpec:
    institution: str
    kind: Literal["bank_current", "bank_savings"] = "bank_current"
    opening_balance: int = 0  # balance when the simulation (incl. its 2-month warm-up) starts
    overdraft_limit: int = 0
    overdraft_rate: float = 0.12  # annual, charged monthly on the daily negative balance
    branch: str = ""


@dataclass(frozen=True)
class CustomerSpec:
    """A customer billed by invoice (B2B, a delivery platform, or a freelancer's client).

    For a delivery platform the "invoice" is the weekly payout statement, net of the platform's
    commission, so the amount invoiced equals the amount eventually paid.
    """

    key: str
    name: str
    monthly_volume: int  # expected invoiced value per month incl. tax, before seasonality/growth
    orders_per_month: float
    terms_days: int  # due date = issue date + terms
    pay_delay_mean_days: float = 0.0  # relative to due date; negative pays early
    pay_delay_sd_days: float = 3.0
    partial_payment_prob: float = 0.0  # pays in two parts, the second 15–40 days later
    amount_cv: float = 0.3
    channel: Channel = Channel.NEFT
    kind: Literal[CounterpartyKind.CUSTOMER, CounterpartyKind.PLATFORM] = CounterpartyKind.CUSTOMER
    category: Category = Category.CUSTOMER_PAYMENT


@dataclass(frozen=True)
class CounterSalesSpec:
    """Walk-in sales recorded in a daily register; UPI settles next day, cash is deposited."""

    daily_mean: int  # gross takings on an average open day
    cv: float = 0.3
    upi_share: float = 0.6
    closed_weekdays: frozenset[int] = frozenset({6})  # Monday=0 … Sunday=6
    cash_deposit_weekdays: frozenset[int] = frozenset({1, 4})
    settlement_provider: str = "PAYZAP"


@dataclass(frozen=True)
class SupplierSpec:
    key: str
    name: str
    share: float  # share of total purchases
    bill_every_days: int = 7
    terms_days: int = 30
    pay_delay_mean_days: float = 0.0
    pay_delay_sd_days: float = 2.0
    channel: Channel = Channel.NEFT


@dataclass(frozen=True)
class EmployeeSpec:
    key: str
    name: str
    monthly_salary: int


@dataclass(frozen=True)
class RecurringExpenseSpec:
    """A bill paid on (about) the same day every month."""

    key: str
    payee: str
    category: Category
    monthly_amount: int
    day_of_month: int
    cv: float = 0.0
    channel: Channel = Channel.IMPS
    kind: CounterpartyKind = CounterpartyKind.MERCHANT
    # Multiplier by calendar month (Jan … Dec), e.g. summer electricity.
    month_multipliers: tuple[float, ...] = FLAT_SEASONALITY
    priority: int = 4


@dataclass(frozen=True)
class VariableExpenseSpec:
    """Irregular spending: a number of payments per month at random open days."""

    key: str
    payee: str
    category: Category
    monthly_amount: int
    times_per_month: float
    cv: float = 0.4
    channel: Channel = Channel.UPI
    kind: CounterpartyKind = CounterpartyKind.MERCHANT
    round_to: int = 1  # rupees, e.g. 500 for ATM withdrawals


@dataclass(frozen=True)
class LoanSpec:
    key: str
    lender: str
    kind: Literal[
        "term_loan", "equipment_loan", "digital_unsecured", "personal_loan", "consumer_durable"
    ]
    principal: int
    annual_rate: float
    tenor_months: int
    disburse_month: int  # month index; may be negative for loans taken before the history starts
    disburse_day: int = 10
    emi_day: int = 5
    reports_to_bureau: bool = True
    processing_fee_rate: float = 0.01
    represent_after_days: int = 5  # a bounced auto-debit is presented again after this many days


@dataclass(frozen=True)
class TaxSpec:
    gst_rate: float = 0.0  # 0 → not GST-registered
    gst_due_day: int = 20
    advance_tax_rate: float = 0.0  # share of the previous quarter's collections, paid quarterly


@dataclass(frozen=True)
class OwnerSpec:
    name: str
    monthly_drawings: int = 0
    drawings_day: int = 7
    min_buffer: int = 0  # never draw below this balance; draw less (or nothing) instead


# --- shocks: changes to behaviour from a given month onwards -------------------------------


@dataclass(frozen=True)
class CustomerVolumeShock:
    customer: str
    start_month: int
    factor: float  # multiplier on order volume once fully ramped (0 = customer lost)
    ramp_months: int = 1
    deterioration: bool = True
    mechanism: str = "customer_concentration_loss"


@dataclass(frozen=True)
class PaymentDelayShock:
    start_month: int
    extra_days: float
    customer: str | None = None  # None → every customer
    deterioration: bool = True
    mechanism: str = "receivables_stretch"


@dataclass(frozen=True)
class SalesTrendShock:
    start_month: int
    monthly_change: float  # compounding, e.g. -0.04 = 4% fewer walk-in sales each month
    deterioration: bool = True
    mechanism: str = "revenue_decline"


@dataclass(frozen=True)
class CostInflationShock:
    start_month: int
    cogs_ratio_delta: float  # added to the purchase/sales ratio (margin squeeze)
    deterioration: bool = True
    mechanism: str = "margin_squeeze"


Shock = CustomerVolumeShock | PaymentDelayShock | SalesTrendShock | CostInflationShock


@dataclass(frozen=True)
class ScenarioSpec:
    code: str
    display_name: str
    kind: Literal["business", "individual"]
    archetype: Literal[
        "healthy_msme",
        "thin_file_msme",
        "strained_msme",  # growing, but growth is draining cash (early-stage deterioration)
        "deteriorating_msme",
        "high_risk_msme",
        "freelancer",
    ]
    segment: str
    narrative: str  # what happens in this scenario, in plain words (the ground-truth story)
    start: date
    months: int
    seed: int
    account: AccountSpec
    owner: OwnerSpec
    profile: dict[str, str | int | bool] = field(default_factory=dict)
    invoice_prefix: str = "INV"
    customers: tuple[CustomerSpec, ...] = ()
    counter_sales: CounterSalesSpec | None = None
    seasonality: tuple[float, ...] = FLAT_SEASONALITY  # by calendar month, Jan … Dec
    monthly_growth: float = 0.0  # compounding underlying growth of all sales
    cogs_ratio: float = 0.0  # purchases (ex-tax) as a share of sales (ex-tax)
    suppliers: tuple[SupplierSpec, ...] = ()
    employees: tuple[EmployeeSpec, ...] = ()
    payroll_day: int = 1  # salaries for the previous month are paid on this day
    recurring_expenses: tuple[RecurringExpenseSpec, ...] = ()
    variable_expenses: tuple[VariableExpenseSpec, ...] = ()
    loans: tuple[LoanSpec, ...] = ()
    tax: TaxSpec = TaxSpec()
    shocks: tuple[Shock, ...] = ()
    currency: str = "INR"

    def __post_init__(self) -> None:
        if not 1 <= self.months <= 36:
            raise ValueError(f"{self.code}: months must be 1-36")
        if self.start.day != 1:
            raise ValueError(f"{self.code}: start must be the first day of a month")
        if len(self.seasonality) != 12:
            raise ValueError(f"{self.code}: seasonality needs 12 monthly multipliers")
        if self.suppliers and abs(sum(s.share for s in self.suppliers) - 1.0) > 1e-6:
            raise ValueError(f"{self.code}: supplier shares must sum to 1")
        keys = [c.key for c in self.customers] + [s.key for s in self.suppliers]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{self.code}: customer/supplier keys must be unique")
        known = {c.key for c in self.customers}
        for shock in self.shocks:
            target = getattr(shock, "customer", None)
            if target is not None and target not in known:
                raise ValueError(f"{self.code}: shock targets unknown customer {target!r}")
