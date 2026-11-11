"""Robust amount anomaly detection with Decimal medians and MAD."""

from decimal import Decimal
from statistics import median

from preflight.checks.common import finding
from preflight.context import Context
from preflight.models import Finding, Invoice, Severity


def robust_score(amount: Decimal, history: tuple[Decimal, ...]) -> Decimal | None:
    """Return absolute robust z-score; zero MAD with a change is unbounded."""
    if len(history) < 5:
        return None
    center = median(history)
    deviation = median(tuple(abs(value - center) for value in history))
    if deviation == 0:
        return Decimal(0) if amount == center else None
    return abs(amount - center) / (Decimal("1.4826") * deviation)


def check(invoice: Invoice, context: Context) -> list[Finding]:
    """Use at least five prior same-currency PASS invoices for the vendor."""
    values = tuple(
        item.amount
        for item in context.history
        if context.vendor is not None
        and item.vendor_id == context.vendor.id
        and item.currency == invoice.currency
        and item.verdict == "PASS"
        and item.received_at < context.received_at
    )
    if invoice.total is None or len(values) < 5:
        return [
            finding(
                context,
                "amount_anomaly",
                "total",
                "unverifiable: fewer than 5 baseline invoices",
                unverifiable=True,
            )
        ]
    score = robust_score(invoice.total, values)
    if score is None or score >= context.anomaly_threshold:
        return [
            finding(
                context,
                "amount_anomaly",
                "total",
                "Amount deviates from history (zero MAD)"
                if score is None
                else f"Robust amount z-score {score:.2f} exceeds threshold",
                Severity.HIGH,
            )
        ]
    return []
