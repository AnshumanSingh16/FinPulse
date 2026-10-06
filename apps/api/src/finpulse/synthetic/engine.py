"""Day-by-day simulation that turns a ``ScenarioSpec`` into a ``Dataset``.

The point of simulating, rather than drawing each table independently, is that every
relationship holds *by construction*:

* sales create invoices (receivables); customer payments are bank credits allocated to invoices;
* purchases create bills (payables); supplier payments are bank debits allocated to bills;
* loans are bank credits; every instalment that is paid is a bank debit;
* the running balance is the sum of every posting, and an outflow only happens if the account
  can afford it (balance + overdraft limit). When it can't, bills wait (payables stretch),
  auto-debits bounce (with a charge) and are presented again, and the owner draws less.

So a cash squeeze in the data is an emergent result of the scenario's shocks, not something
painted on afterwards. Each day runs in a fixed order:

1. money in: loan disbursements, yesterday's UPI settlement, customer payments due today;
2. business activity (open days): the day's counter sales, new customer invoices, cash deposit;
0. loan auto-debits (NACH) are presented first, against the overnight balance;
3. new supplier bills; scheduled outflows join the payment queue;
4. the payment queue is worked through in priority order against available funds
   (a bounced auto-debit is only presented again after its re-presentment interval);
5. owner drawings, if the buffer allows; overdraft interest accrues on a negative balance.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from finpulse.core.money import round_minor, rupees
from finpulse.synthetic import calendar as cal
from finpulse.synthetic.bureau import derive_bureau_events
from finpulse.synthetic.categories import Category, Channel, CounterpartyKind
from finpulse.synthetic.ids import IdFactory
from finpulse.synthetic.loans import amortize, emi
from finpulse.synthetic.model import (
    Account,
    Bill,
    Counterparty,
    CounterSale,
    Dataset,
    GroundTruth,
    Installment,
    InstallmentStatus,
    Invoice,
    InvoiceStatus,
    Loan,
    Settlement,
    Subject,
    Transaction,
)
from finpulse.synthetic.sampling import Sampler
from finpulse.synthetic.spec import (
    CostInflationShock,
    CustomerSpec,
    CustomerVolumeShock,
    LoanSpec,
    PaymentDelayShock,
    SalesTrendShock,
    ScenarioSpec,
)

GENERATOR_VERSION = 1
# Months simulated before the visible history so it opens mid-stream, with customers already
# owing money, suppliers already owed, and a bank balance shaped by real activity — rather than
# every pipeline starting empty on day one.
WARMUP_MONTHS = 2
BOUNCE_CHARGE = rupees(590)  # ₹500 + 18% GST, a typical NACH return charge
MONTH_ABBR = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
ADVANCE_TAX_MONTHS = {6: 15, 9: 15, 12: 15, 3: 15}  # month → day

# Payment priorities: lower is paid first when money is short.
P_BANK, P_EMI, P_SALARY, P_STATUTORY, P_UTILITY, P_SUPPLIER, P_OTHER = 0, 1, 2, 3, 4, 5, 6


@dataclass
class _Outflow:
    due_on: date
    retry_on: date
    priority: int
    amount: int
    payee: uuid.UUID | None
    description: str
    category: Category
    channel: Channel
    order: int
    on_paid: Callable[[Transaction], None] | None = None
    on_bounce: Callable[[date], None] | None = None  # set for auto-debits (EMIs)
    represent_after_days: int = 1


@dataclass
class _InstallmentState:
    id: uuid.UUID
    loan_id: uuid.UUID
    seq: int
    due_on: date
    amount: int
    principal: int
    interest: int
    paid_on: date | None = None
    transaction_id: uuid.UUID | None = None
    bounces: int = 0


@dataclass
class _Document:
    """Invoice or bill under construction; settlements accumulate until the end."""

    id: uuid.UUID
    number: str
    party: uuid.UUID
    issued_on: date
    due_on: date
    taxable: int
    tax: int
    total: int
    settlements: list[Settlement] = field(default_factory=list)


class _Simulation:
    def __init__(self, spec: ScenarioSpec) -> None:
        self.spec = spec
        self.ids = IdFactory(spec.code, spec.seed)
        self.start = spec.start  # first day of the visible history
        self.sim_start = cal.add_months(spec.start, -WARMUP_MONTHS)
        self.end = cal.add_months(spec.start, spec.months) - timedelta(days=1)
        self.gst = spec.tax.gst_rate

        acct = spec.account
        refs = Sampler(spec.seed, "account")
        self.account = Account(
            id=self.ids("account", "primary"),
            kind=acct.kind,
            institution=acct.institution,
            masked_number="XXXXXX" + refs.digits(4),
            currency=spec.currency,
            opened_on=cal.add_months(spec.start, -refs.integer(20, 60)),
            opening_balance_minor=acct.opening_balance,
            overdraft_limit_minor=acct.overdraft_limit,
        )
        self.balance = acct.opening_balance
        self.window_opening = (acct.opening_balance, 0, 0)
        self.seq = 0
        self.transactions: list[Transaction] = []
        self.refs = Sampler(spec.seed, "references")

        self.counterparties: dict[str, Counterparty] = {}
        self.queue: list[_Outflow] = []
        self.queue_order = 0

        self.counter_sales: list[CounterSale] = []
        self.pending_upi: dict[date, int] = defaultdict(int)
        self.cash_drawer = 0

        self.invoices: list[_Document] = []
        self.next_order: dict[str, date] = {}
        self.customer_rng = {c.key: Sampler(spec.seed, f"customer:{c.key}") for c in spec.customers}
        self.bills: list[_Document] = []
        self.invoice_seq = 0
        self.planned_receipts: dict[date, list[tuple[_Document, int, CustomerSpec]]] = defaultdict(
            list
        )

        self.output_tax: dict[int, int] = defaultdict(int)  # month index → GST collected
        self.input_tax: dict[int, int] = defaultdict(int)  # month index → GST paid on purchases
        self.gst_credit = 0
        self.collections: dict[int, int] = defaultdict(int)  # month index → invoice receipts

        self.od_interest_accrued = 0.0
        self.loans: list[Loan] = []
        self.installments: list[_InstallmentState] = []
        self.disbursements: dict[date, list[tuple[LoanSpec, uuid.UUID]]] = defaultdict(list)
        self.variable_days: dict[str, list[date]] = {}

        closed = spec.counter_sales.closed_weekdays if spec.counter_sales else frozenset({6})
        if spec.kind == "individual" and not spec.counter_sales:
            closed = frozenset({5, 6})
        self.closed_weekdays = closed

        self._plan_loans()

    # --- helpers -------------------------------------------------------------------------

    def party(self, key: str, name: str, kind: CounterpartyKind) -> uuid.UUID:
        if key not in self.counterparties:
            self.counterparties[key] = Counterparty(
                id=self.ids("counterparty", key), name=name, kind=kind
            )
        return self.counterparties[key].id

    def available(self) -> int:
        return self.balance + self.account.overdraft_limit_minor

    def post(
        self,
        day: date,
        amount: int,
        description: str,
        channel: Channel,
        category: Category,
        payee: uuid.UUID | None,
    ) -> Transaction:
        if amount == 0:
            raise ValueError("zero-amount transaction")
        self.seq += 1
        self.balance += amount
        tx = Transaction(
            id=self.ids("transaction", self.seq),
            account_id=self.account.id,
            posted_on=day,
            seq=self.seq,
            amount_minor=amount,
            balance_after_minor=self.balance,
            description=description,
            channel=channel,
            category=category,
            counterparty_id=payee,
            external_ref=f"{self.account.masked_number[-4:]}{self.seq:07d}",
        )
        self.transactions.append(tx)
        return tx

    def enqueue(self, outflow: _Outflow) -> None:
        self.queue.append(outflow)

    def new_outflow(
        self,
        due_on: date,
        priority: int,
        amount: int,
        payee: uuid.UUID | None,
        description: str,
        category: Category,
        channel: Channel,
        on_paid: Callable[[Transaction], None] | None = None,
    ) -> _Outflow:
        self.queue_order += 1
        return _Outflow(
            due_on,
            due_on,
            priority,
            amount,
            payee,
            description,
            category,
            channel,
            self.queue_order,
            on_paid,
        )

    def utr(self) -> str:
        return "GVBK" + self.refs.digits(11)

    def is_open(self, day: date) -> bool:
        return day.weekday() not in self.closed_weekdays

    def open_days_in_month(self, day: date) -> int:
        return sum(1 for d in cal.days(cal.month_start(day), cal.month_end(day)) if self.is_open(d))

    # --- scenario dynamics ---------------------------------------------------------------

    def month(self, day: date) -> int:
        return cal.month_index(self.start, day)

    def level(self, day: date) -> float:
        """Underlying demand level from seasonality and growth."""
        return self.spec.seasonality[day.month - 1] * (1 + self.spec.monthly_growth) ** self.month(
            day
        )

    def customer_factor(self, key: str, m: int) -> float:
        factor = 1.0
        for s in self.spec.shocks:
            if isinstance(s, CustomerVolumeShock) and s.customer == key and m >= s.start_month:
                progress = min(1.0, (m - s.start_month + 1) / max(1, s.ramp_months))
                factor *= 1 + (s.factor - 1) * progress
        return factor

    def extra_delay(self, key: str, m: int) -> float:
        return sum(
            s.extra_days
            for s in self.spec.shocks
            if isinstance(s, PaymentDelayShock)
            and m >= s.start_month
            and (s.customer is None or s.customer == key)
        )

    def counter_trend(self, m: int) -> float:
        factor = 1.0
        for s in self.spec.shocks:
            if isinstance(s, SalesTrendShock) and m >= s.start_month:
                factor *= (1 + s.monthly_change) ** (m - s.start_month + 1)
        return factor

    def cogs_ratio(self, m: int) -> float:
        return self.spec.cogs_ratio + sum(
            s.cogs_ratio_delta
            for s in self.spec.shocks
            if isinstance(s, CostInflationShock) and m >= s.start_month
        )

    def expected_monthly_sales(self, day: date) -> float:
        """Expected gross sales for the month containing ``day`` (no noise). Drives purchasing."""
        m = self.month(day)
        b2b = sum(c.monthly_volume * self.customer_factor(c.key, m) for c in self.spec.customers)
        counter = 0.0
        if self.spec.counter_sales:
            counter = (
                self.spec.counter_sales.daily_mean
                * self.counter_trend(m)
                * self.open_days_in_month(day)
            )
        return (b2b + counter) * self.level(day)

    # --- loans ---------------------------------------------------------------------------

    def _plan_loans(self) -> None:
        for spec in self.spec.loans:
            lender = self.party(f"lender:{spec.lender}", spec.lender, CounterpartyKind.LENDER)
            disbursed_on = cal.clamp_day(
                *_year_month(cal.add_months(self.start, spec.disburse_month)), spec.disburse_day
            )
            loan_id = self.ids("loan", spec.key)
            schedule = amortize(spec.principal, spec.annual_rate, spec.tenor_months)
            for item in schedule:
                due = cal.clamp_day(
                    *_year_month(cal.add_months(disbursed_on, item.seq)), spec.emi_day
                )
                state = _InstallmentState(
                    id=self.ids("installment", f"{spec.key}/{item.seq}"),
                    loan_id=loan_id,
                    seq=item.seq,
                    due_on=due,
                    amount=item.amount_minor,
                    principal=item.principal_minor,
                    interest=item.interest_minor,
                )
                if due < self.sim_start:
                    # Before the simulation: assume paid on time (no bank record of it).
                    state.paid_on = due
                self.installments.append(state)
            if disbursed_on >= self.sim_start:
                self.disbursements[disbursed_on].append((spec, lender))
            else:
                self.loans.append(self._loan_record(spec, lender, disbursed_on, None))

    def _loan_record(
        self, spec: LoanSpec, lender: uuid.UUID, disbursed_on: date, tx_id: uuid.UUID | None
    ) -> Loan:
        return Loan(
            id=self.ids("loan", spec.key),
            lender_id=lender,
            account_id=self.account.id,
            kind=spec.kind,
            principal_minor=spec.principal,
            annual_rate_bps=round(spec.annual_rate * 10_000),
            tenor_months=spec.tenor_months,
            disbursed_on=disbursed_on,
            emi_minor=emi(spec.principal, spec.annual_rate, spec.tenor_months),
            reports_to_bureau=spec.reports_to_bureau,
            disbursement_transaction_id=tx_id,
        )

    def disburse(self, day: date) -> None:
        for spec, lender in self.disbursements.get(day, []):
            loan_ref = "LN" + self.refs.digits(8)
            tx = self.post(
                day,
                spec.principal,
                f"LOAN DISB {spec.lender.upper()} {loan_ref}",
                Channel.INTERNAL,
                Category.LOAN_DISBURSEMENT,
                lender,
            )
            self.loans.append(self._loan_record(spec, lender, day, tx.id))
            fee = round_minor(spec.principal * spec.processing_fee_rate)
            if fee:
                self.post(
                    day,
                    -fee,
                    f"PROC FEE {spec.lender.upper()} {loan_ref}",
                    Channel.INTERNAL,
                    Category.LOAN_PROCESSING_FEE,
                    lender,
                )

    def schedule_emis(self, day: date) -> None:
        by_key = {self.ids("loan", s.key): s for s in self.spec.loans}
        for inst in self.installments:
            if inst.due_on != day or inst.paid_on is not None:
                continue
            spec = by_key[inst.loan_id]
            lender = self.counterparties[f"lender:{spec.lender}"].id

            def paid(tx: Transaction, inst: _InstallmentState = inst) -> None:
                inst.paid_on, inst.transaction_id = tx.posted_on, tx.id

            def bounced(
                on: date,
                inst: _InstallmentState = inst,
                spec: LoanSpec = spec,
                lender: uuid.UUID = lender,
            ) -> None:
                inst.bounces += 1
                self.enqueue(
                    self.new_outflow(
                        on,
                        P_BANK,
                        BOUNCE_CHARGE,
                        lender,
                        f"NACH RTN CHG {spec.lender.upper()}",
                        Category.BOUNCE_CHARGE,
                        Channel.INTERNAL,
                    )
                )

            outflow = self.new_outflow(
                day,
                P_EMI,
                inst.amount,
                lender,
                f"NACH DR {spec.lender.upper()} EMI {inst.seq}/{spec.tenor_months}",
                Category.LOAN_REPAYMENT,
                Channel.NACH,
                paid,
            )
            outflow.on_bounce = bounced
            outflow.represent_after_days = spec.represent_after_days
            self.enqueue(outflow)

    # --- sales & receivables -------------------------------------------------------------

    def counter_sale(self, day: date) -> None:
        cs = self.spec.counter_sales
        if cs is None or not self.is_open(day):
            return
        rng = Sampler(self.spec.seed, f"counter:{day.isoformat()}")
        mean = cs.daily_mean * self.level(day) * self.counter_trend(self.month(day))
        gross = round_minor(rng.lognormal_mean(mean, cs.cv), step_major=10)
        if gross <= 0:
            return
        upi = min(gross, round_minor(gross * cs.upi_share * rng.lognormal_mean(1, 0.1)))
        tax = gross - round_minor(gross / (1 + self.gst)) if self.gst else 0
        self.counter_sales.append(
            CounterSale(
                self.ids("counter_sale", day.isoformat()), day, gross, tax, upi, gross - upi
            )
        )
        self.output_tax[self.month(day)] += tax
        if upi:
            self.pending_upi[day + timedelta(days=1)] += upi
        self.cash_drawer += gross - upi
        if day.weekday() in cs.cash_deposit_weekdays and self.cash_drawer >= rupees(1000):
            deposit = (self.cash_drawer // rupees(100)) * rupees(100)
            self.cash_drawer -= deposit
            self.post(
                day,
                deposit,
                "CASH DEP BY SELF " + self.spec.account.branch.upper(),
                Channel.CASH,
                Category.SALES_CASH_DEPOSIT,
                None,
            )

    def settle_upi(self, day: date) -> None:
        amount = self.pending_upi.pop(day, 0)
        if amount and self.spec.counter_sales:
            provider = self.spec.counter_sales.settlement_provider
            payee = self.party(f"psp:{provider}", provider, CounterpartyKind.PLATFORM)
            self.post(
                day,
                amount,
                f"UPI SETTL {provider} {day:%d%m%y}",
                Channel.UPI,
                Category.SALES_UPI_SETTLEMENT,
                payee,
            )

    def next_order_gap(self, c: CustomerSpec, day: date, rng: Sampler) -> timedelta | None:
        """Days until this customer's next order. Customers order at fairly regular intervals
        (a renewal process with ±30% jitter), not independently every day, so month-to-month
        order counts are realistic rather than Poisson-noisy. ``None`` means no further orders."""
        rate = c.orders_per_month * self.customer_factor(c.key, self.month(day))
        if rate <= 0:
            return None
        return timedelta(days=max(1, round(rng.lognormal_mean(30.4 / rate, 0.3))))

    def issue_invoices(self, day: date) -> None:
        if not self.is_open(day):
            return
        m = self.month(day)
        for c in self.spec.customers:
            rng = self.customer_rng[c.key]
            if c.key not in self.next_order:
                first_gap = self.next_order_gap(c, day, rng)
                if first_gap is None:
                    continue
                # Stagger the first order so customers don't all order on day one.
                self.next_order[c.key] = day + timedelta(
                    days=rng.integer(0, max(0, first_gap.days - 1))
                )
            if self.next_order[c.key] > day:
                continue
            gap = self.next_order_gap(c, day, rng)
            self.next_order[c.key] = day + gap if gap else self.end + timedelta(days=1)
            mean = c.monthly_volume / c.orders_per_month * self.level(day)
            total = round_minor(rng.lognormal_mean(mean, c.amount_cv))
            if total <= 0:
                continue
            taxable = round_minor(total / (1 + self.gst)) if self.gst else total
            self.invoice_seq += 1
            number = (
                f"{self.spec.invoice_prefix}/{cal.financial_year_label(day)}/{self.invoice_seq:04d}"
            )
            doc = _Document(
                id=self.ids("invoice", number),
                number=number,
                party=self.party(f"customer:{c.key}", c.name, c.kind),
                issued_on=day,
                due_on=day + timedelta(days=c.terms_days),
                taxable=taxable,
                tax=total - taxable,
                total=total,
            )
            self.invoices.append(doc)
            self.output_tax[m] += doc.tax
            self.plan_receipt(doc, c, rng, m)

    def plan_receipt(self, doc: _Document, c: CustomerSpec, rng: Sampler, m: int) -> None:
        delay = rng.normal(c.pay_delay_mean_days + self.extra_delay(c.key, m), c.pay_delay_sd_days)
        pay_on = max(doc.issued_on + timedelta(days=1), doc.due_on + timedelta(days=round(delay)))
        if rng.chance(c.partial_payment_prob):
            first = round_minor(doc.total * rng.uniform(0.4, 0.7))
            self.planned_receipts[pay_on].append((doc, first, c))
            later = pay_on + timedelta(days=rng.integer(15, 40))
            self.planned_receipts[later].append((doc, doc.total - first, c))
        else:
            self.planned_receipts[pay_on].append((doc, doc.total, c))

    def receive_payments(self, day: date) -> None:
        for doc, amount, c in self.planned_receipts.pop(day, []):
            tx = self.post(
                day,
                amount,
                f"{c.channel.upper()} CR {self.utr()} {c.name.upper()}",
                c.channel,
                c.category,
                doc.party,
            )
            doc.settlements.append(
                Settlement(self.ids("invoice_payment", tx.seq), doc.id, tx.id, day, amount)
            )
            self.collections[self.month(day)] += amount

    # --- purchases & payables ------------------------------------------------------------

    def issue_bills(self, day: date) -> None:
        offset = (day - self.sim_start).days
        m = self.month(day)
        for index, s in enumerate(self.spec.suppliers):
            if (offset - index * 2) % s.bill_every_days != 0 or offset < index * 2:
                continue
            rng = Sampler(self.spec.seed, f"supplier:{s.key}:{day.isoformat()}")
            period_share = s.bill_every_days / cal.month_end(day).day
            sales_taxable = self.expected_monthly_sales(day) / (1 + self.gst)
            taxable = round_minor(
                sales_taxable
                * self.cogs_ratio(m)
                * s.share
                * period_share
                * rng.lognormal_mean(1, 0.12)
            )
            if taxable <= 0:
                continue
            tax = round_minor(taxable * self.gst) if self.gst else 0
            supplier = self.party(f"supplier:{s.key}", s.name, CounterpartyKind.SUPPLIER)
            number = f"{s.key.upper()[:4]}-{day:%y%m%d}"
            doc = _Document(
                self.ids("bill", f"{s.key}/{number}"),
                number,
                supplier,
                day,
                day + timedelta(days=s.terms_days),
                taxable,
                tax,
                taxable + tax,
            )
            self.bills.append(doc)
            self.input_tax[m] += tax
            delay = round(rng.normal(s.pay_delay_mean_days, s.pay_delay_sd_days))
            pay_on = max(day, doc.due_on + timedelta(days=delay))

            def paid(tx: Transaction, doc: _Document = doc) -> None:
                doc.settlements.append(
                    Settlement(
                        self.ids("bill_payment", tx.seq),
                        doc.id,
                        tx.id,
                        tx.posted_on,
                        -tx.amount_minor,
                    )
                )

            self.enqueue(
                self.new_outflow(
                    pay_on,
                    P_SUPPLIER,
                    doc.total,
                    supplier,
                    f"{s.channel.upper()} DR {{utr}} {s.name.upper()} {number}",
                    Category.SUPPLIER_PAYMENT,
                    s.channel,
                    paid,
                )
            )

    # --- operating outflows --------------------------------------------------------------

    def schedule_operating(self, day: date) -> None:
        spec, m = self.spec, self.month(day)
        prev = cal.add_months(day, -1)
        if day.day == spec.payroll_day:
            for e in spec.employees:
                payee = self.party(f"employee:{e.key}", e.name, CounterpartyKind.EMPLOYEE)
                self.enqueue(
                    self.new_outflow(
                        day,
                        P_SALARY,
                        e.monthly_salary,
                        payee,
                        f"NEFT DR {{utr}} SAL {MONTH_ABBR[prev.month - 1]} {e.name.upper()}",
                        Category.SALARY,
                        Channel.NEFT,
                    )
                )

        for r in spec.recurring_expenses:
            if day != cal.clamp_day(day.year, day.month, r.day_of_month):
                continue
            rng = Sampler(spec.seed, f"recurring:{r.key}:{day.isoformat()}")
            amount = round_minor(
                r.monthly_amount * r.month_multipliers[day.month - 1] * rng.lognormal_mean(1, r.cv)
            )
            payee = self.party(f"{r.kind}:{r.key}", r.payee, r.kind)
            self.enqueue(
                self.new_outflow(
                    day,
                    r.priority,
                    amount,
                    payee,
                    f"{r.channel.upper()} DR {{utr}} {r.payee.upper()} {MONTH_ABBR[day.month - 1]}",
                    r.category,
                    r.channel,
                )
            )

        if day.day == 1:
            for v in spec.variable_expenses:
                rng = Sampler(spec.seed, f"variable:{v.key}:{day:%Y-%m}")
                open_days = [d for d in cal.days(day, cal.month_end(day)) if self.is_open(d)]
                count = rng.poisson(v.times_per_month)
                self.variable_days[v.key] = sorted(rng.choice(open_days) for _ in range(count))
        for v in spec.variable_expenses:
            for index, when in enumerate(self.variable_days.get(v.key, [])):
                if when != day:
                    continue
                rng = Sampler(spec.seed, f"variable:{v.key}:{day.isoformat()}:{index}")
                amount = round_minor(
                    rng.lognormal_mean(v.monthly_amount / v.times_per_month, v.cv), v.round_to
                )
                if amount <= 0:
                    continue
                payee = self.party(f"{v.kind}:{v.key}", v.payee, v.kind)
                self.enqueue(
                    self.new_outflow(
                        day,
                        P_OTHER,
                        amount,
                        payee,
                        f"{v.channel.upper()} DR {{utr}} {v.payee.upper()}",
                        v.category,
                        v.channel,
                    )
                )

        if self.gst and day.day == spec.tax.gst_due_day and m - 1 >= -WARMUP_MONTHS:
            liability = self.output_tax[m - 1] - self.input_tax[m - 1] - self.gst_credit
            if liability > 0:
                self.gst_credit = 0
                amount = round_minor(liability)
                authority = self.party("tax:gst", "GST", CounterpartyKind.TAX_AUTHORITY)
                self.enqueue(
                    self.new_outflow(
                        day,
                        P_STATUTORY,
                        amount,
                        authority,
                        f"GST CHALLAN CPIN {self.refs.digits(14)} {MONTH_ABBR[prev.month - 1]}",
                        Category.GST,
                        Channel.NEFT,
                    )
                )
            else:
                self.gst_credit = -liability

        if spec.tax.advance_tax_rate and ADVANCE_TAX_MONTHS.get(day.month) == day.day:
            base = sum(self.collections[i] for i in range(m - 3, m) if i >= -WARMUP_MONTHS)
            amount = round_minor(base * spec.tax.advance_tax_rate, step_major=100)
            if amount > 0:
                authority = self.party(
                    "tax:income", "Income Tax Department", CounterpartyKind.TAX_AUTHORITY
                )
                self.enqueue(
                    self.new_outflow(
                        day,
                        P_STATUTORY,
                        amount,
                        authority,
                        f"ADV TAX CHALLAN {self.refs.digits(10)}",
                        Category.ADVANCE_TAX,
                        Channel.NEFT,
                    )
                )

        if day.day == 1 and self.od_interest_accrued >= 50:  # ≥ ₹0.50 of interest
            amount = round_minor(self.od_interest_accrued)
            self.od_interest_accrued = 0.0
            if amount:
                bank = self.party("bank:primary", spec.account.institution, CounterpartyKind.BANK)
                self.enqueue(
                    self.new_outflow(
                        day,
                        P_BANK,
                        amount,
                        bank,
                        f"INT ON OD {MONTH_ABBR[prev.month - 1]}",
                        Category.OVERDRAFT_INTEREST,
                        Channel.INTERNAL,
                    )
                )

    def work_queue(self, day: date, auto_debits_only: bool = False) -> None:
        ready = sorted(
            (
                o
                for o in self.queue
                if o.retry_on <= day and (not auto_debits_only or o.on_bounce is not None)
            ),
            key=lambda o: (o.priority, o.due_on, o.order),
        )
        for o in ready:
            if o.amount <= self.available():
                description = o.description.replace("{utr}", self.utr())
                if o.retry_on > o.due_on and o.on_bounce is not None:
                    description += " RE-PRESENTED"
                tx = self.post(day, -o.amount, description, o.channel, o.category, o.payee)
                if o.on_paid:
                    o.on_paid(tx)
                self.queue.remove(o)
            elif o.on_bounce is not None:
                o.on_bounce(day)
                o.retry_on = day + timedelta(days=o.represent_after_days)
            else:
                o.retry_on = day + timedelta(days=1)  # wait for money to come in

    def owner_drawings(self, day: date) -> None:
        owner = self.spec.owner
        if not owner.monthly_drawings or day.day != owner.drawings_day:
            return
        headroom = self.balance - owner.min_buffer
        amount = min(owner.monthly_drawings, (headroom // rupees(1000)) * rupees(1000))
        if amount > 0:
            payee = self.party("owner", owner.name, CounterpartyKind.OWNER)
            self.post(
                day,
                -amount,
                f"IMPS DR {self.utr()} SELF {owner.name.upper()}",
                Channel.IMPS,
                Category.OWNER_DRAWINGS,
                payee,
            )

    # --- run -----------------------------------------------------------------------------

    def run(self) -> Dataset:
        for day in cal.days(self.sim_start, self.end):
            if day == self.start:
                self.window_opening = (
                    self.balance,
                    self.cash_drawer,
                    sum(self.pending_upi.values()),
                )
            # Auto-debits (NACH) are presented at the start of the day, before any money comes
            # in, against whatever balance was left overnight.
            self.schedule_emis(day)
            self.work_queue(day, auto_debits_only=True)
            self.disburse(day)
            self.settle_upi(day)
            self.receive_payments(day)
            self.counter_sale(day)
            self.issue_invoices(day)
            self.issue_bills(day)
            self.schedule_operating(day)
            self.work_queue(day)
            self.owner_drawings(day)
            if self.balance < 0:
                self.od_interest_accrued += -self.balance * self.spec.account.overdraft_rate / 365
        return self._dataset()

    def _dataset(self) -> Dataset:
        """Cut the warm-up away. References to bank transactions before the window become
        ``None`` (the activity happened, but predates the statement), and invoices or bills
        issued during the warm-up are kept only if they were still open when the window began —
        they are the opening receivables and payables."""
        spec, start, as_of = self.spec, self.start, self.end
        transactions = tuple(t for t in self.transactions if t.posted_on >= start)
        kept = {t.id for t in transactions}

        def in_window(tx_id: uuid.UUID | None) -> uuid.UUID | None:
            return tx_id if tx_id in kept else None

        def open_at_start(doc: _Document) -> bool:
            if doc.issued_on >= start:
                return True
            return sum(x.amount_minor for x in doc.settlements if x.paid_on < start) < doc.total

        def settlements(doc: _Document) -> list[Settlement]:
            return [replace(x, transaction_id=in_window(x.transaction_id)) for x in doc.settlements]

        invoices = [d for d in self.invoices if open_at_start(d)]
        bills = [d for d in self.bills if open_at_start(d)]
        installments = [
            replace(_installment(i, as_of), transaction_id=in_window(i.transaction_id))
            for i in self.installments
        ]
        loans = sorted(
            (
                replace(
                    loan, disbursement_transaction_id=in_window(loan.disbursement_transaction_id)
                )
                for loan in self.loans
            ),
            key=lambda loan: (loan.disbursed_on, str(loan.id)),
        )
        opening_balance, opening_cash, opening_upi = self.window_opening
        deteriorating = [s for s in spec.shocks if s.deterioration]
        onset = (
            cal.add_months(start, min(s.start_month for s in deteriorating))
            if deteriorating
            else None
        )
        used = {t.counterparty_id for t in transactions}
        used |= {d.party for d in [*invoices, *bills]} | {loan.lender_id for loan in loans}
        return Dataset(
            scenario_code=spec.code,
            generator_version=GENERATOR_VERSION,
            seed=spec.seed,
            start_date=start,
            as_of=as_of,
            currency=spec.currency,
            subject=Subject(
                id=self.ids("subject", "subject"),
                kind=spec.kind,
                display_name=spec.display_name,
                segment=spec.segment,
                profile=dict(spec.profile),
            ),
            accounts=(replace(self.account, opening_balance_minor=opening_balance),),
            counterparties=tuple(c for c in self.counterparties.values() if c.id in used),
            transactions=transactions,
            counter_sales=tuple(c for c in self.counter_sales if c.sold_on >= start),
            invoices=tuple(_invoice(d, as_of) for d in invoices),
            invoice_payments=tuple(x for d in invoices for x in settlements(d)),
            bills=tuple(_bill(d, as_of) for d in bills),
            bill_payments=tuple(x for d in bills for x in settlements(d)),
            loans=tuple(loans),
            installments=tuple(installments),
            bureau_events=tuple(derive_bureau_events(loans, installments, as_of, self.ids)),
            ground_truth=GroundTruth(
                archetype=spec.archetype,
                deteriorates=bool(deteriorating),
                onset_date=onset,
                mechanisms=tuple(sorted({s.mechanism for s in deteriorating})),
                narrative=spec.narrative,
            ),
            opening_cash_on_hand_minor=opening_cash,
            opening_unsettled_upi_minor=opening_upi,
            cash_on_hand_minor=self.cash_drawer,
            unsettled_upi_minor=sum(self.pending_upi.values()),
            params={
                "months": spec.months,
                "archetype": spec.archetype,
                "warmup_months": WARMUP_MONTHS,
            },
        )


def _year_month(d: date) -> tuple[int, int]:
    return d.year, d.month


def _status(doc: _Document, as_of: date) -> InvoiceStatus:
    paid = sum(s.amount_minor for s in doc.settlements if s.paid_on <= as_of)
    if paid >= doc.total:
        return "paid"
    if doc.due_on < as_of:
        return "overdue"
    return "partially_paid" if paid else "open"


def _invoice(doc: _Document, as_of: date) -> Invoice:
    return Invoice(
        doc.id,
        doc.number,
        doc.party,
        doc.issued_on,
        doc.due_on,
        doc.taxable,
        doc.tax,
        doc.total,
        _status(doc, as_of),
    )


def _bill(doc: _Document, as_of: date) -> Bill:
    return Bill(
        doc.id,
        doc.number,
        doc.party,
        doc.issued_on,
        doc.due_on,
        doc.taxable,
        doc.tax,
        doc.total,
        _status(doc, as_of),
    )


def _installment(i: _InstallmentState, as_of: date) -> Installment:
    status: InstallmentStatus
    if i.paid_on is not None:
        status = "paid_on_time" if i.paid_on <= i.due_on else "paid_late"
    elif i.due_on <= as_of:
        status = "overdue"
    else:
        status = "scheduled"
    return Installment(
        i.id,
        i.loan_id,
        i.seq,
        i.due_on,
        i.amount,
        i.principal,
        i.interest,
        i.paid_on,
        i.transaction_id,
        i.bounces,
        status,
    )


def generate(spec: ScenarioSpec) -> Dataset:
    """Run the scenario. Pure and deterministic: same spec ⇒ identical dataset."""
    return _Simulation(spec).run()
