"""Hostile ingestion boundaries, real PDF parsing and safe email attachments."""

from email.message import EmailMessage

import pymupdf
import pytest

from preflight.extract.documents import (
    MAX_BYTES,
    IngestionError,
    Upload,
    ingest,
    sniff_mime,
)
from tests.documents import eml, image, invoice_pdf, pdf


def test_real_pdf_text_and_hash() -> None:
    upload, _ = invoice_pdf()
    document = ingest(upload)
    assert "Acme" in document.text
    assert len(document.pages) == 1
    assert len(document.content_hash) == 64
    assert document.mime == "application/pdf"


@pytest.mark.parametrize("extension", ["png", "jpg"])
def test_images_are_validated_without_ocr(extension: str) -> None:
    upload = image(extension)
    document = ingest(upload)
    assert document.images == (upload.data,)
    assert document.text == ""


@pytest.mark.parametrize(
    ("upload", "code"),
    [
        (Upload("big.pdf", b"x" * (MAX_BYTES + 1)), "file_too_large"),
        (Upload("invoice.pdf", b"not a PDF"), "unsupported_type"),
        (Upload("invoice.png", b"%PDF-1.7 fake"), "mime_mismatch"),
        (Upload("invoice.exe", b"%PDF-1.7 fake"), "mime_mismatch"),
        (Upload("invoice.pdf", b"%PDF-1.7 fake", "image/png"), "mime_mismatch"),
        (Upload("invoice.pdf", b"%PDF-1.7 fake"), "invalid_document"),
        (Upload("invoice.png", b"\x89PNG\r\n\x1a\ninvalid"), "invalid_document"),
    ],
)
def test_typed_ingestion_errors(upload: Upload, code: str) -> None:
    with pytest.raises(IngestionError) as error:
        ingest(upload)
    assert error.value.code == code


def test_signature_limit_boundary() -> None:
    assert sniff_mime(b"%PDF-" + b"x" * (MAX_BYTES - 5)) == "application/pdf"


def test_no_text_pdf_is_ocr_unavailable() -> None:
    with pymupdf.open() as document:
        document.new_page()
        upload = Upload("scan.pdf", document.tobytes())
    with pytest.raises(IngestionError) as error:
        ingest(upload)
    assert error.value.code == "ocr_unavailable"


def test_mixed_blank_page_cannot_be_ignored() -> None:
    with pymupdf.open(stream=pdf("Invoice").data, filetype="pdf") as document:
        document.new_page()
        upload = Upload("mixed.pdf", document.tobytes())
    with pytest.raises(IngestionError) as error:
        ingest(upload)
    assert error.value.code == "ocr_unavailable"


def test_pdf_page_and_text_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("preflight.extract.documents.MAX_PAGES", 0)
    with pytest.raises(IngestionError, match="page limit"):
        ingest(pdf("Invoice"))
    monkeypatch.setattr("preflight.extract.documents.MAX_PAGES", 100)
    monkeypatch.setattr("preflight.extract.documents.MAX_TEXT", 5)
    with pytest.raises(IngestionError, match="text limit"):
        ingest(pdf("Invoice is longer than five characters"))


def test_email_body_headers_and_safe_attachments() -> None:
    upload, _ = invoice_pdf()
    suspicious_name = Upload("../../escape.pdf", upload.data)
    document = ingest(eml(reply_to="accounts@acme.example", attachments=(suspicious_name,)))
    assert document.email is not None
    assert document.email.from_address == "billing@acme.example"
    assert document.email.reply_to == "accounts@acme.example"
    assert "Please see" in document.email.body
    assert document.attachments[0].name == "escape.pdf"
    assert document.attachments[0].data == upload.data


def test_attachment_count_is_capped() -> None:
    upload, _ = invoice_pdf()
    with pytest.raises(IngestionError) as error:
        ingest(eml(attachments=(upload,) * 11))
    assert error.value.code == "too_many_attachments"


def test_html_email_is_text_only() -> None:
    message = EmailMessage()
    message["From"] = "billing@acme.example"
    message["Subject"] = "Invoice"
    message.set_content('<p>Invoice</p><img src="https://example.com/tracker">', subtype="html")
    document = ingest(Upload("invoice.eml", message.as_bytes()))
    assert document.email is not None
    assert "Invoice" in document.email.body


def test_malformed_multiple_senders_are_rejected() -> None:
    data = b"From: a@a.example, b@b.example\nSubject: Invoice\n\nBody"
    with pytest.raises(IngestionError, match="one valid From"):
        ingest(Upload("invoice.eml", data))


def test_attachment_mime_mismatch_is_not_silently_ignored() -> None:
    message = EmailMessage()
    message["From"] = "billing@acme.example"
    message["Subject"] = "Invoice"
    message.set_content("Invoice")
    message.add_attachment(
        b"%PDF-1.7 fake",
        maintype="image",
        subtype="png",
        filename="invoice.png",
    )
    with pytest.raises(IngestionError) as error:
        ingest(Upload("invoice.eml", message.as_bytes()))
    assert error.value.code == "mime_mismatch"
