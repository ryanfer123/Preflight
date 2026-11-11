"""Generate small genuine documents in memory; fixtures never use the network."""

from email.message import EmailMessage

import pymupdf

from preflight.extract.documents import Upload
from preflight.extract.evidence import invoice_fields
from preflight.models import Evidence, Invoice, InvoiceExtraction
from tests.factories import invoice


def pdf(text: str) -> Upload:
    """Create a text-layer PDF without storing files."""
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_textbox(pymupdf.Rect(30, 30, 560, 800), text, fontsize=10)
        return Upload("invoice.pdf", document.tobytes())


def invoice_pdf(
    value: Invoice | None = None, extra: str = ""
) -> tuple[Upload, InvoiceExtraction]:
    """Create an invoice with value-bearing, page-grounded citations."""
    value = value or invoice()
    fields = invoice_fields(value)
    text = "\n".join(fields.values()) + "\n" + extra
    document = pdf(text)
    extraction = InvoiceExtraction(
        invoice=value,
        evidence=tuple(
            Evidence(field=field, source_snippet=content, page=1)
            for field, content in fields.items()
        ),
    )
    return document, extraction


def eml(
    sender: str = "Acme <billing@acme.example>",
    reply_to: str | None = None,
    auth: str = "receiver.example; spf=pass; dkim=pass; dmarc=pass",
    attachments: tuple[Upload, ...] = (),
) -> Upload:
    """Build an original email with optional explicitly typed attachments."""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "owner@buyer.example"
    message["Subject"] = "Invoice"
    if reply_to:
        message["Reply-To"] = reply_to
    if auth:
        message["Authentication-Results"] = auth
    message.set_content("Please see the invoice.")
    for upload in attachments:
        kind = {
            ".pdf": ("application", "pdf"),
            ".png": ("image", "png"),
            ".jpg": ("image", "jpeg"),
        }.get(upload.name[-4:], ("application", "octet-stream"))
        message.add_attachment(
            upload.data, maintype=kind[0], subtype=kind[1], filename=upload.name
        )
    return Upload("invoice.eml", message.as_bytes())


def image(extension: str = "png") -> Upload:
    """Create a real small PNG or JPEG."""
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False)
    pixmap.clear_with(255)
    return Upload("invoice." + extension, pixmap.tobytes(extension))
