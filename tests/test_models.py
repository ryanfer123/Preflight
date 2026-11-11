"""Strict contracts preserve absence and reject decision-bearing model output."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from preflight.models import (
    BankDetails,
    Evidence,
    ExtractionFailure,
    Finding,
    Invoice,
    InvoiceExtraction,
    LineItem,
    Severity,
)


def invoice() -> Invoice:
    return Invoice(
        vendor_name=None,
        invoice_number=None,
        currency=None,
        gstin=None,
        registration_state=None,
        bank=BankDetails(),
        line_items=None,
        subtotal=None,
        tax=None,
        total=None,
    )


def test_missing_fields_stay_missing() -> None:
    value = invoice()
    assert value.total is None
    assert value.line_items is None
    assert value.bank.account_number is None
    assert InvoiceExtraction(invoice=value, evidence=()).invoice == value


def test_decimal_round_trip() -> None:
    item = LineItem(
        description="Parts",
        quantity=Decimal("3"),
        unit_price=Decimal("0.10"),
        total=Decimal("0.30"),
    )
    assert item.quantity is not None and item.unit_price is not None
    assert item.quantity * item.unit_price == item.total
    assert LineItem.model_validate_json(item.model_dump_json()) == item


@pytest.mark.parametrize("value", [0.1, "0.1", 1, True, Decimal("NaN"), Decimal("Infinity")])
def test_money_rejects_coercion_and_nonfinite(value: object) -> None:
    data: dict[str, object] = {
        "description": None,
        "quantity": None,
        "unit_price": value,
        "total": None,
    }
    with pytest.raises(ValidationError):
        LineItem.model_validate(data)


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("-1"), Decimal("-Infinity")])
def test_quantity_must_be_positive(value: Decimal) -> None:
    with pytest.raises(ValidationError):
        LineItem(description=None, quantity=value, unit_price=None, total=None)


def test_arithmetic_is_not_hidden_in_schema() -> None:
    # Preserve tampered numbers for the deterministic arithmetic check in M2.
    item = LineItem(
        description=None, quantity=Decimal("2"), unit_price=Decimal("10"), total=Decimal("999")
    )
    assert item.total == Decimal("999")


def test_evidence_and_finding_require_citations() -> None:
    evidence = Evidence(field="gstin", source_snippet="27AAPFU0939F1ZO", page=1)
    finding = Finding(
        check_id="identifier.gstin",
        severity=Severity.HIGH,
        message="Checksum mismatch",
        evidence=(evidence,),
    )
    assert finding.evidence[0].page == 1
    with pytest.raises(ValidationError):
        Finding(check_id="x", severity=Severity.HIGH, message="x", evidence=())


@pytest.mark.parametrize("page", [0, -1, True, "1"])
def test_invalid_page(page: object) -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate({"field": "x", "source_snippet": "x", "page": page})


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_evidence_rejected(text: str) -> None:
    with pytest.raises(ValidationError):
        Evidence(field="x", source_snippet=text, page=None)


def test_no_model_verdict_or_unknown_fields() -> None:
    data = {"invoice": invoice(), "evidence": (), "verdict": "PASS"}
    with pytest.raises(ValidationError, match="Extra inputs"):
        InvoiceExtraction.model_validate(data)
    with pytest.raises(ValidationError, match="Extra inputs"):
        BankDetails.model_validate({"approved": True})


@pytest.mark.parametrize("value", ["0.1", "1", "true", '"invalid"', '"NaN"', '"Infinity"'])
def test_json_money_rejects_numbers_and_invalid_strings(value: str) -> None:
    with pytest.raises(ValidationError):
        LineItem.model_validate_json(
            '{"description":null,"quantity":null,"unit_price":' + value + ',"total":null}'
        )


def test_failure_is_explicit_and_models_immutable() -> None:
    assert ExtractionFailure(reason="Invalid schema").status == "extraction_failed"
    value = invoice()
    with pytest.raises(ValidationError):
        value.total = Decimal("0")
