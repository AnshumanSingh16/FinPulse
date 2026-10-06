"""Flatten a dataset into table-shaped records, fingerprint it, and write it out as CSV/JSON.

The record layout matches the database tables (``finpulse.persistence.models``), so the same
rows feed the database loader, the CSV export and the reproducibility fingerprint.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from finpulse.synthetic.model import Dataset

Row = dict[str, Any]


def _row(obj: object, **extra: Any) -> Row:
    assert dataclasses.is_dataclass(obj) and not isinstance(obj, type)  # noqa: S101
    data = {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
    data.update(extra)
    return data


def to_records(ds: Dataset) -> dict[str, list[Row]]:
    """Table name → rows, in dependency order (parents before children)."""
    subject_id = ds.subject.id
    owned = {"subject_id": subject_id}
    return {
        "subjects": [_row(ds.subject)],
        "synthetic_generations": [generation_record(ds)],
        "accounts": [_row(a, **owned) for a in ds.accounts],
        "counterparties": [_row(c, **owned) for c in ds.counterparties],
        "transactions": [_row(t, **owned) for t in ds.transactions],
        "counter_sales": [_row(s, **owned) for s in ds.counter_sales],
        "invoices": [_row(i, **owned) for i in ds.invoices],
        "invoice_payments": [_row(p, **owned) for p in ds.invoice_payments],
        "bills": [_row(b, **owned) for b in ds.bills],
        "bill_payments": [_row(p, **owned) for p in ds.bill_payments],
        "loans": [_row(loan, **owned) for loan in ds.loans],
        "loan_installments": [_row(i, **owned) for i in ds.installments],
        "simulated_bureau_events": [_row(e, **owned) for e in ds.bureau_events],
    }


def generation_record(ds: Dataset) -> Row:
    gt = ds.ground_truth
    return {
        "id": uuid.uuid5(ds.subject.id, "generation"),
        "subject_id": ds.subject.id,
        "scenario_code": ds.scenario_code,
        "generator_version": ds.generator_version,
        "seed": ds.seed,
        "start_date": ds.start_date,
        "as_of": ds.as_of,
        "currency": ds.currency,
        "params": ds.params,
        "ground_truth": {
            "archetype": gt.archetype,
            "deteriorates": gt.deteriorates,
            "onset_date": gt.onset_date.isoformat() if gt.onset_date else None,
            "mechanisms": list(gt.mechanisms),
            "narrative": gt.narrative,
        },
        "cash_positions": {
            "opening_cash_on_hand_minor": ds.opening_cash_on_hand_minor,
            "opening_unsettled_upi_minor": ds.opening_unsettled_upi_minor,
            "closing_cash_on_hand_minor": ds.cash_on_hand_minor,
            "closing_unsettled_upi_minor": ds.unsettled_upi_minor,
        },
        "dataset_fingerprint": fingerprint(ds),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID | date):
        return str(value)
    if isinstance(value, frozenset | set):
        return sorted(value)
    raise TypeError(f"not serialisable: {type(value).__name__}")


def fingerprint(ds: Dataset) -> str:
    """SHA-256 of the dataset's canonical JSON. Equal fingerprints ⇒ identical data."""
    payload = json.dumps(dataclasses.asdict(ds), default=_jsonable, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def write_csv(ds: Dataset, directory: Path) -> list[Path]:
    """One CSV per table plus ``ground_truth.json``. Returns the files written."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table, rows in to_records(ds).items():
        if table == "synthetic_generations":
            path = directory / "ground_truth.json"
            path.write_text(json.dumps(rows[0], default=_jsonable, indent=2) + "\n")
            written.append(path)
            continue
        path = directory / f"{table}.csv"
        fields = list(rows[0]) if rows else []
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {k: json.dumps(v) if isinstance(v, dict) else v for k, v in row.items()}
                )
        written.append(path)
    return written
