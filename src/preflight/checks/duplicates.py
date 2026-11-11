"""Exact and nearby duplicate observations using prior ledger records."""

from datetime import timedelta

from preflight.checks.common import finding
from preflight.context import Context
from preflight.models import Finding, Invoice, Severity


def check(invoice: Invoice, context: Context) -> list[Finding]:
    """Detect global hash reuse and vendor/currency scoped financial duplicates."""
    results: list[Finding] = []
    if context.content_hash and any(
        item.content_hash == context.content_hash for item in context.all_history
    ):
        results.append(
            finding(
                context,
                "duplicates",
                "document",
                "Identical document content hash",
                Severity.HIGH,
            )
        )
    if context.vendor is None or invoice.invoice_number is None or invoice.total is None:
        results.append(
            finding(
                context,
                "duplicates",
                "invoice_number",
                "unverifiable: vendor, number or amount missing",
                unverifiable=True,
            )
        )
        return results
    history = [
        item
        for item in context.history
        if item.vendor_id == context.vendor.id and item.currency == invoice.currency
    ]
    if any(
        item.invoice_number == invoice.invoice_number and item.amount == invoice.total
        for item in history
    ):
        results.append(
            finding(
                context,
                "duplicates",
                "invoice_number",
                "Same vendor, invoice number and amount already recorded",
                Severity.HIGH,
            )
        )
    elif any(
        item.invoice_number != invoice.invoice_number
        and item.amount == invoice.total
        and timedelta(0) <= context.received_at - item.received_at <= timedelta(days=3)
        for item in history
    ):
        results.append(
            finding(
                context,
                "duplicates",
                "total",
                "Same amount with a different number within 3 days",
                Severity.LOW,
            )
        )
    return results
