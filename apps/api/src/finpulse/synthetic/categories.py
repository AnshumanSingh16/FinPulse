"""Labels the generator attaches to what it creates.

Transaction categories here are *ground-truth labels* from the simulation
(``category_source = "synthetic_label"``). The Phase 2 categoriser must work them out from the
narration alone; these labels are what it will be evaluated against.
"""

from __future__ import annotations

from enum import StrEnum


class Category(StrEnum):
    # inflows
    SALES_UPI_SETTLEMENT = "income.sales_upi_settlement"
    SALES_CASH_DEPOSIT = "income.sales_cash_deposit"
    CUSTOMER_PAYMENT = "income.customer_payment"
    PLATFORM_PAYOUT = "income.platform_payout"
    CLIENT_PAYMENT = "income.client_payment"
    LOAN_DISBURSEMENT = "debt.loan_disbursement"
    # business outflows
    SUPPLIER_PAYMENT = "expense.supplier"
    SALARY = "expense.salary"
    RENT = "expense.rent"
    ELECTRICITY = "expense.electricity"
    TELECOM = "expense.telecom"
    FUEL = "expense.fuel"
    FREIGHT = "expense.freight"
    MAINTENANCE = "expense.maintenance"
    SOFTWARE = "expense.software"
    PROFESSIONAL_FEES = "expense.professional_fees"
    PACKAGING = "expense.packaging"
    PLATFORM_FEES = "expense.platform_fees"
    # tax, debt, bank
    GST = "tax.gst"
    ADVANCE_TAX = "tax.advance_tax"
    LOAN_REPAYMENT = "debt.emi"
    LOAN_PROCESSING_FEE = "debt.processing_fee"
    BOUNCE_CHARGE = "bank.bounce_charge"
    OVERDRAFT_INTEREST = "bank.overdraft_interest"
    BANK_CHARGES = "bank.charges"
    # owner / personal
    OWNER_DRAWINGS = "owner.drawings"
    CASH_WITHDRAWAL = "cash.withdrawal"
    HOUSING_RENT = "personal.rent"
    GROCERIES = "personal.groceries"
    DINING = "personal.dining"
    TRANSPORT = "personal.transport"
    SHOPPING = "personal.shopping"
    HEALTH = "personal.health"
    INSURANCE = "personal.insurance"
    INVESTMENT = "personal.investment"
    BETTING = "personal.betting"


class CounterpartyKind(StrEnum):
    CUSTOMER = "customer"
    PLATFORM = "platform"
    SUPPLIER = "supplier"
    EMPLOYEE = "employee"
    LANDLORD = "landlord"
    UTILITY = "utility"
    LENDER = "lender"
    TAX_AUTHORITY = "tax_authority"
    BANK = "bank"
    OWNER = "owner"
    MERCHANT = "merchant"
    SELF = "self"


class Channel(StrEnum):
    UPI = "upi"
    NEFT = "neft"
    IMPS = "imps"
    RTGS = "rtgs"
    NACH = "nach"
    CASH = "cash"
    CARD = "card"
    CHEQUE = "cheque"
    BILLPAY = "billpay"
    INTERNAL = "internal"  # bank-initiated: charges, interest, disbursements
