"""Regression tests for citation, parsing, transport and baseline boundaries."""

import socket
from decimal import Decimal
from email.message import EmailMessage

import pytest

from preflight.checks import amount_anomaly, arithmetic, sender
from preflight.extract.documents import IngestionError, Upload, ingest
from preflight.extract.evidence import evidence_error
from preflight.extract.fake import FakeExtractor
from preflight.extract.openai_compatible import OpenAICompatibleExtractor
from preflight.ledger import Ledger
from preflight.models import ExtractionFailure
from preflight.pipeline import run
from preflight.policy import load_policy
from tests.documents import eml, invoice_pdf
from tests.factories import NOW, context, history, invoice
from tests.test_pipeline import seed


def test_dns_and_datagram_connections_are_prohibited() -> None:
    with pytest.raises(AssertionError, match="network"):
        socket.getaddrinfo("example.com", 443)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        with pytest.raises(AssertionError, match="network"):
            connection.sendto(b"x", ("127.0.0.1", 53))


def test_punycode_confusable_and_transposition() -> None:
    punycode = "acmе.example".encode("idna").decode("ascii")
    assert sender.is_lookalike(punycode, ("acme.example",))
    assert sender.is_lookalike("acme.exampel", ("acme.example",))


def test_printed_value_must_match_cited_value() -> None:
    upload, extraction = invoice_pdf()
    changed = extraction.model_copy(
        update={
            "invoice": extraction.invoice.model_copy(update={"total": Decimal("999")}),
        }
    )
    assert evidence_error(changed, ingest(upload)) == "evidence_invalid"


def test_nonzero_mad_both_sides_of_threshold() -> None:
    ctx = context().model_copy(
        update={
            "history": tuple(
                history(Decimal(value), index)
                for index, value in enumerate(("10", "11", "12", "13", "14"))
            ),
        }
    )
    assert (
        amount_anomaly.check(invoice().model_copy(update={"total": Decimal("12")}), ctx) == []
    )
    assert (
        amount_anomaly.check(invoice().model_copy(update={"total": Decimal("30")}), ctx)[
            0
        ].severity.value
        == "high"
    )


def test_tampered_line_total_is_high() -> None:
    value = invoice()
    assert value.line_items is not None
    item = value.line_items[0].model_copy(update={"total": Decimal("101")})
    findings = arithmetic.check(value.model_copy(update={"line_items": (item,)}), context())
    assert len(findings) == 2
    assert all(finding.severity.value == "high" for finding in findings)


def test_no_original_email_is_an_explicit_gap() -> None:
    upload, extraction = invoice_pdf()
    with Ledger() as ledger:
        seed(ledger)
        report = run(
            upload,
            ledger=ledger,
            policy=load_policy(),
            extractor=FakeExtractor(result=extraction),
            received_at=NOW,
        )
    assert report.verdict == "PASS"
    assert "sender" in report.unverifiable_checks


def test_zero_width_sender_reaches_review_through_email_parser() -> None:
    upload, extraction = invoice_pdf()
    with Ledger() as ledger:
        seed(ledger)
        report = run(
            upload,
            eml("Acme <billing@ac\u200bme.example>"),
            ledger=ledger,
            policy=load_policy(),
            extractor=FakeExtractor(result=extraction),
            received_at=NOW,
        )
    assert report.verdict == "REVIEW"


def test_nested_email_attachment_is_not_executed_or_followed() -> None:
    nested = EmailMessage()
    nested["From"] = "billing@acme.example"
    nested["Subject"] = "Nested invoice"
    nested.set_content("Content")
    outer = EmailMessage()
    outer["From"] = "billing@acme.example"
    outer["Subject"] = "Invoice"
    outer.set_content("See nested email")
    outer.add_attachment(nested)
    with pytest.raises(IngestionError) as error:
        ingest(Upload("nested.eml", outer.as_bytes()))
    assert error.value.code == "unsupported_type"


def test_provider_invalid_image_fails_without_network() -> None:
    provider = OpenAICompatibleExtractor("http://local/v1", "", "model")
    assert isinstance(provider.extract("", [b"bad image"]), ExtractionFailure)
