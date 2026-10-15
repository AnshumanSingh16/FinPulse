"""Uploads: parsing Indian amounts and dates, mapping, validation, missing values and duplicates."""

import io

import pandas as pd
import pytest

from finpilot.data.loader import (
    build_balances,
    build_ledger,
    build_obligations,
    parse_amount,
    parse_date,
    read_table,
    suggest_mapping,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("₹1,23,456.50", (123456.5, None)),
        ("Rs. 2,500", (2500.0, None)),
        ("INR 99", (99.0, None)),
        ("(1,234)", (-1234.0, None)),
        ("1,234-", (-1234.0, None)),
        ("-500", (-500.0, None)),
        ("2.5 lakh", (250000.0, None)),
        ("1.2 crore", (12000000.0, None)),
        # "Cr"/"Dr" after an amount are the bank-statement credit/debit markers, not crore.
        ("1.2 cr", (1.2, "in")),
        ("15k", (15000.0, None)),
        ("4,500.00 Dr", (4500.0, "out")),
        ("4500 Cr", (4500.0, "in")),
        ("", (None, None)),
        ("-", (None, None)),
        ("abc", (None, None)),
        (1200, (1200.0, None)),
    ],
)
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("05/04/2026", "2026-04-05"),  # day first
        ("2026-04-05", "2026-04-05"),
        ("5-Apr-2026", "2026-04-05"),
        ("05.04.2026", "2026-04-05"),
        ("46117", "2026-04-05"),  # Excel serial
        ("31/02/2026", None),
        ("", None),
        ("not a date", None),
    ],
)
def test_parse_date(raw, expected):
    d = parse_date(raw)
    assert (str(d.date()) if d is not None else None) == expected


def test_suggest_mapping_for_a_bank_statement():
    m = suggest_mapping(["Txn Date", "Narration", "Withdrawal Amt", "Deposit Amt", "Chq/Ref No", "Closing Balance"], "ledger")
    assert m["date"] == "Txn Date"
    assert m["description"] == "Narration"
    assert m["debit"] == "Withdrawal Amt"
    assert m["credit"] == "Deposit Amt"
    assert m["reference"] == "Chq/Ref No"


def _raw(rows, cols):
    return pd.DataFrame(rows, columns=cols, dtype=str)


def test_debit_credit_columns():
    raw = _raw(
        [["01/04/2026", "Sale", "", "10,000", "Sales"], ["02/04/2026", "Rent", "5,000", "", "Rent"]],
        ["Date", "Narration", "Debit", "Credit", "Category"],
    )
    led, rep = build_ledger(raw, suggest_mapping(list(raw.columns), "ledger"))
    assert rep.rows_ok == 2 and not rep.rejected
    assert list(led["direction"]) == ["in", "out"]
    assert list(led["amount"]) == [10000.0, 5000.0]


def test_signed_amount_and_direction_column():
    raw = _raw(
        [["2026-04-01", "A", "-2,000", "Rent"], ["2026-04-02", "B", "3000", "Sales"], ["2026-04-03", "C", "700", "Sales", ]],
        ["Date", "Description", "Amount", "Category"],
    )
    led, _ = build_ledger(raw, {"date": "Date", "description": "Description", "amount": "Amount", "category": "Category"})
    assert list(led["direction"]) == ["out", "in", "in"]
    raw2 = raw.assign(Type=["Debit", "Credit", "Debit"])
    led2, _ = build_ledger(raw2, {"date": "Date", "description": "Description", "amount": "Amount", "category": "Category", "direction": "Type"})
    assert list(led2["direction"]) == ["out", "in", "out"]


def test_missing_values_are_rejected_or_filled_with_reasons():
    raw = _raw(
        [
            ["01/04/2026", "Sale", "10000", "Sales", "Shop"],
            ["", "No date", "500", "Rent", "X"],
            ["03/04/2026", "No amount", "", "Rent", "X"],
            ["04/04/2026", "Zero", "0", "Rent", "X"],
            ["05/04/2026", "", "300", "", ""],
        ],
        ["Date", "Description", "Amount", "Category", "Party"],
    )
    led, rep = build_ledger(raw, suggest_mapping(list(raw.columns), "ledger"))
    assert rep.rows_in == 5 and rep.rows_ok == 2
    reasons = {r["row"]: r["reason"] for r in rep.rejected}
    assert "date" in reasons[3] and "amount" in reasons[4] and "zero" in reasons[5]
    assert rep.filled["category"] == 1 and rep.filled["description"] == 1 and rep.filled["counterparty"] == 1
    assert led.iloc[1]["category"] == "Uncategorised"
    assert any("Uncategorised" in w for w in rep.warnings)


def test_foreign_currency_rows_are_not_converted():
    raw = _raw([["01/04/2026", "A", "100", "USD"], ["01/04/2026", "B", "100", "INR"]], ["Date", "Description", "Amount", "Currency"])
    led, rep = build_ledger(raw, {"date": "Date", "description": "Description", "amount": "Amount", "currency": "Currency"})
    assert rep.rows_ok == 1
    assert "not INR" in rep.rejected[0]["reason"]


def test_duplicates_warned_and_optionally_dropped():
    rows = [["01/04/2026", "Freight", "1200", "Logistics", "VRL"]] * 2 + [["02/04/2026", "Freight", "1200", "Logistics", "VRL"]]
    raw = _raw(rows, ["Date", "Description", "Amount", "Category", "Party"])
    m = suggest_mapping(list(raw.columns), "ledger")
    led, rep = build_ledger(raw, m)
    assert rep.rows_ok == 3
    assert rep.duplicate_groups == [["U00001", "U00002"]]
    assert any("possible duplicates" in w for w in rep.warnings)
    led2, rep2 = build_ledger(raw, m, drop_exact_duplicates=True)
    assert rep2.rows_ok == 2 and rep2.exact_duplicates_dropped == 1 and rep2.duplicate_groups == []


def test_no_date_column():
    raw = _raw([["x", "1"]], ["Narration", "Amount"])
    led, rep = build_ledger(raw, {"description": "Narration", "amount": "Amount"})
    assert rep.rows_ok == 0 and "No date column" in rep.warnings[0]


def test_obligations_and_balances():
    raw = _raw(
        [
            ["INV-1", "Receivable", "Acme", "50,000", "15/05/2026", "Unpaid"],
            ["BILL-1", "Payable", "Supplier", "20000", "10/05/2026", "Paid"],
            ["BILL-2", "Bill", "Supplier", "", "10/05/2026", "Pending"],
            ["X", "Something", "S", "100", "10/05/2026", "maybe"],
        ],
        ["Invoice No", "Kind", "Party", "Amount", "Due Date", "Status"],
    )
    m = suggest_mapping(list(raw.columns), "obligations")
    obl, rep = build_obligations(raw, m)
    assert list(obl["item_id"]) == ["INV-1", "BILL-1"]
    assert list(obl["status"]) == ["pending", "paid"]
    assert len(rep.rejected) == 2
    bal, brep = build_balances(_raw([["31/03/2026", "HDFC", "₹2,40,000"], ["", "HDFC", "1"]], ["Date", "Account", "Balance"]),
                               {"as_of": "Date", "account": "Account", "balance": "Balance"})
    assert bal.iloc[0]["balance"] == 240000.0 and str(bal.iloc[0]["as_of"].date()) == "2026-03-31"
    assert len(brep.rejected) == 1


def test_read_csv_and_xlsx_round_trip():
    df = pd.DataFrame({"Date": ["01/04/2026"], "Amount": ["1,000"]})
    csv = df.to_csv(index=False).encode()
    assert read_table(csv, "x.csv").iloc[0]["Amount"] == "1,000"
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    x = read_table(buf.getvalue(), "x.xlsx")
    assert str(x.iloc[0]["Amount"]) == "1,000"
    with pytest.raises(ValueError):
        read_table(b"", "x.pdf")


def test_snake_case_columns_map_too():
    m = suggest_mapping(["item_id", "kind", "due_date", "paid_date", "status", "amount"], "obligations")
    assert m["item_id"] == "item_id" and m["due_date"] == "due_date" and m["paid_date"] == "paid_date"
