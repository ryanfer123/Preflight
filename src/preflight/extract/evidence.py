"""Validate citation grounding before model output can enter deterministic checks."""

from preflight.extract.documents import Document
from preflight.models import Invoice, InvoiceExtraction


def invoice_fields(invoice: Invoice) -> dict[str, str]:
    """Enumerate populated scalar paths; no model-provided path is trusted."""
    fields: dict[str, str] = {}
    for name in (
        "vendor_name",
        "invoice_number",
        "currency",
        "gstin",
        "registration_state",
        "subtotal",
        "tax",
        "total",
    ):
        value = getattr(invoice, name)
        if value is not None:
            fields[name] = str(value)
    for name in ("account_number", "ifsc", "upi_vpa", "iban"):
        value = getattr(invoice.bank, name)
        if value is not None:
            fields["bank." + name] = str(value)
    for index, item in enumerate(invoice.line_items or ()):
        for name in ("description", "quantity", "unit_price", "total"):
            value = getattr(item, name)
            if value is not None:
                fields[f"line_items.{index}.{name}"] = str(value)
    return fields


def evidence_error(extraction: InvoiceExtraction, document: Document) -> str | None:
    """Require every populated field to have an actual, value-bearing source citation."""
    if not document.text:
        return "visual_evidence_unverifiable"
    fields = invoice_fields(extraction.invoice)
    grounded: set[str] = set()
    for evidence in extraction.evidence:
        if evidence.field not in fields:
            return "evidence_invalid"
        if evidence.page is not None:
            if not 1 <= evidence.page <= len(document.pages):
                return "evidence_invalid"
            source = document.pages[evidence.page - 1]
        else:
            source = document.text
        if evidence.source_snippet not in source:
            return "evidence_invalid"
        if fields[evidence.field] not in evidence.source_snippet:
            return "evidence_invalid"
        grounded.add(evidence.field)
    if set(fields) - grounded:
        return "evidence_missing"
    return None
