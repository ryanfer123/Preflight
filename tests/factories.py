"""Typed fixture factories shared by unit and integration tests."""

from datetime import UTC, datetime
from decimal import Decimal

from preflight.context import Context, HistoricalInvoice, Vendor
from preflight.models import BankDetails, Invoice, LineItem

NOW = datetime(2026, 1, 10, tzinfo=UTC)
SOURCE = "Acme INV-100 INR 27AAPFU0939F1ZV 27 123456 SBIN0001234 2 50.00 100.00 18.00 118.00"


def invoice() -> Invoice:
    """Return a reconcilable domestic invoice."""
    return Invoice(
        vendor_name="Acme",
        invoice_number="INV-100",
        currency="INR",
        gstin="27AAPFU0939F1ZV",
        registration_state="27",
        bank=BankDetails(account_number="123456", ifsc="SBIN0001234"),
        line_items=(
            LineItem(
                description="Parts",
                quantity=Decimal("2"),
                unit_price=Decimal("50.00"),
                total=Decimal("100.00"),
            ),
        ),
        subtotal=Decimal("100.00"),
        tax=Decimal("18.00"),
        total=Decimal("118.00"),
    )


def vendor() -> Vendor:
    """Return a separately established local vendor."""
    return Vendor(id=1, name="Acme", known_domains=("acme.example",), created_at=NOW)


def context() -> Context:
    """Return an immutable context with an approved payment baseline."""
    return Context(
        source_text=SOURCE,
        vendor=vendor(),
        approved_accounts=("account:123456|ifsc:sbin0001234",),
        received_at=NOW,
        tolerance=Decimal("0.01"),
        anomaly_threshold=Decimal("3.5"),
    )


def history(amount: Decimal, index: int = 1, verdict: str = "PASS") -> HistoricalInvoice:
    """Return one prior same-currency invoice."""
    return HistoricalInvoice(
        id=index,
        vendor_id=1,
        invoice_number=f"OLD-{index}",
        amount=amount,
        currency="INR",
        content_hash=f"hash-{index}",
        received_at=datetime(2026, 1, 8, tzinfo=UTC),
        verdict=verdict,
    )
