"""SQLite money fidelity, approval and transaction boundaries."""

import sqlite3
from decimal import Decimal

import pytest

from preflight.ledger import Ledger
from tests.factories import NOW


def test_ledger_roundtrip_and_parameterisation() -> None:
    with Ledger() as ledger:
        vendor = ledger.add_vendor("Acme'); DROP TABLE vendors; --", ("acme.example",))
        assert ledger.get_vendor(vendor.id) == vendor
        assert ledger.find_vendor(vendor.name) == vendor
        assert ledger.get_vendor(999) is None
        assert ledger.find_vendor("unknown") is None
        ledger.approve_bank_account(vendor.id, " ACCOUNT:123 456|IFSC:SBIN0001234 ")
        ledger.approve_bank_account(vendor.id, "account:123456|ifsc:sbin0001234")
        assert ledger.approved_accounts(vendor.id) == ("account:123456|ifsc:sbin0001234",)
        amount = Decimal("999999999999.123456789")
        ledger.record_invoice(vendor.id, "INV-1", amount, "INR", "hash", NOW, "PASS")
        row = ledger.connection.execute(
            "SELECT amount, typeof(amount) FROM invoices"
        ).fetchone()
        assert tuple(row) == (str(amount), "text")
        assert ledger.list_history(vendor.id)[0].amount == amount
        assert ledger.list_history() == ledger.list_history(vendor.id)
        with pytest.raises(sqlite3.IntegrityError):
            ledger.approve_bank_account(999, "account:unknown")
        assert ledger.get_vendor(vendor.id) is not None
    with pytest.raises(RuntimeError):
        ledger.list_history()


@pytest.mark.parametrize("amount", [Decimal("NaN"), Decimal("Infinity"), "1.2"])
def test_invalid_money(amount: object) -> None:
    with Ledger() as ledger:
        vendor = ledger.add_vendor("Acme")
        with pytest.raises(ValueError):
            ledger.record_invoice(vendor.id, "INV", amount, "INR", "hash", NOW, "PASS")  # type: ignore[arg-type]


def test_invalid_inputs_and_rollback() -> None:
    with Ledger() as ledger:
        with pytest.raises(ValueError):
            ledger.add_vendor("")
        vendor = ledger.add_vendor("Acme")
        with pytest.raises(ValueError):
            ledger.approve_bank_account(vendor.id, " ")
        with pytest.raises(ValueError):
            ledger.record_invoice(
                vendor.id, "INV", Decimal("1"), "INR", "hash", NOW.replace(tzinfo=None), "PASS"
            )
        with pytest.raises(sqlite3.IntegrityError):
            ledger.record_invoice(vendor.id, "INV", Decimal("1"), "INR", "hash", NOW, "WRONG")
        assert ledger.list_history() == ()
