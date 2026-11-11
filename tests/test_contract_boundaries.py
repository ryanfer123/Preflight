"""External structured-output and unapproved-ledger contracts."""

from datetime import datetime

import pytest

from preflight.checks.common import bank_identifiers
from preflight.extract.fake import FakeExtractor
from preflight.extract.openai_compatible import extraction_schema
from preflight.ledger import Ledger
from preflight.pipeline import run
from preflight.policy import load_policy
from tests.documents import invoice_pdf
from tests.factories import NOW, invoice
from tests.test_pipeline import seed


def test_wire_schema_requires_nullable_bank_fields_and_string_money() -> None:
    schema = extraction_schema()
    definitions = schema["$defs"]
    bank = definitions["BankDetails"]
    assert set(bank["required"]) == {"account_number", "ifsc", "upi_vpa", "iban"}
    assert bank["additionalProperties"] is False
    for definition in definitions.values():
        if definition.get("type") == "object":
            assert set(definition["required"]) == set(definition["properties"])
            for field in definition["properties"].values():
                assert "default" not in field
    total = definitions["Invoice"]["properties"]["total"]
    assert {branch["type"] for branch in total["anyOf"]} == {"string", "null"}


def test_observed_model_bank_never_becomes_an_approved_baseline() -> None:
    value = invoice().model_copy(
        update={
            "bank": invoice().bank.model_copy(update={"account_number": "654321"}),
        }
    )
    identifier = bank_identifiers(value.bank)[0][1]
    upload, extraction = invoice_pdf(value)
    with Ledger() as ledger:
        vendor_id = seed(ledger)
        kwargs = {
            "ledger": ledger,
            "policy": load_policy(),
            "extractor": FakeExtractor(result=extraction),
            "received_at": NOW,
        }
        assert run(upload, **kwargs).verdict == "BLOCK"
        assert identifier not in ledger.approved_accounts(vendor_id)
        row = ledger.connection.execute(
            """SELECT first_seen, approved_by_user, approved_at FROM vendor_bank_accounts
            WHERE vendor_id = ? AND account_identifier_normalised = ?""",
            (vendor_id, identifier),
        ).fetchone()
        assert tuple(row) == (NOW.isoformat(), 0, None)
        assert run(upload, **kwargs).verdict == "BLOCK"
        ledger.approve_bank_account(vendor_id, identifier)
        row = ledger.connection.execute(
            """SELECT first_seen, approved_by_user, approved_at FROM vendor_bank_accounts
            WHERE vendor_id = ? AND account_identifier_normalised = ?""",
            (vendor_id, identifier),
        ).fetchone()
        assert row["first_seen"] == NOW.isoformat()
        assert row["approved_by_user"] == 1 and row["approved_at"] is not None


def test_bad_bank_observation_is_rejected() -> None:
    with Ledger() as ledger:
        vendor = ledger.add_vendor("Acme")
        for identifier, timestamp in (("", NOW), ("account:x", datetime(2026, 1, 1))):
            with pytest.raises(ValueError):
                ledger.observe_bank_account(vendor.id, identifier, timestamp)
