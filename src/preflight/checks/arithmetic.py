"""Decimal-only reconciliation with an explicit absolute tolerance."""

from decimal import Decimal

from preflight.checks.common import finding
from preflight.context import Context
from preflight.models import Finding, Invoice, Severity


def check(invoice: Invoice, context: Context) -> list[Finding]:
    """Compare every printed line, subtotal and subtotal plus tax with total."""
    items = invoice.line_items
    if (
        not items
        or any(
            item.quantity is None or item.unit_price is None or item.total is None
            for item in items
        )
        or any(value is None for value in (invoice.subtotal, invoice.tax, invoice.total))
    ):
        return [
            finding(
                context,
                "arithmetic",
                "total",
                "unverifiable: incomplete arithmetic inputs",
                unverifiable=True,
            )
        ]
    results: list[Finding] = []
    summed = Decimal(0)
    for index, item in enumerate(items):
        assert (
            item.quantity is not None and item.unit_price is not None and item.total is not None
        )
        summed += item.total
        if abs(item.quantity * item.unit_price - item.total) > context.tolerance:
            results.append(
                finding(
                    context,
                    "arithmetic",
                    f"line_items.{index}.total",
                    f"Line {index + 1} quantity × unit price differs from line total",
                    Severity.HIGH,
                )
            )
    assert (
        invoice.subtotal is not None and invoice.tax is not None and invoice.total is not None
    )
    if abs(summed - invoice.subtotal) > context.tolerance:
        results.append(
            finding(
                context,
                "arithmetic",
                "subtotal",
                "Line totals differ from subtotal",
                Severity.HIGH,
            )
        )
    if abs(invoice.subtotal + invoice.tax - invoice.total) > context.tolerance:
        results.append(
            finding(
                context,
                "arithmetic",
                "total",
                "Subtotal plus tax differs from total",
                Severity.HIGH,
            )
        )
    return results
