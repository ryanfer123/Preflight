"""Pure checks, boundaries and property invariants."""

from datetime import timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from preflight.checks import (
    amount_anomaly,
    arithmetic,
    bank_change,
    duplicates,
    identifiers,
    pressure_language,
    sender,
)
from preflight.context import EmailData
from preflight.models import Severity
from tests.factories import NOW, context, history, invoice


def test_identifier_wrapper_surfaces_missing_and_invalid() -> None:
    value = invoice().model_copy(update={"gstin": "27AAPFU0939F1ZO"})
    findings = identifiers.check(value, context())
    assert any(item.severity == Severity.HIGH for item in findings)
    assert any(item.status == "unverifiable" for item in findings)
    assert all(item.evidence for item in findings)


def test_arithmetic_boundaries_and_missing() -> None:
    assert arithmetic.check(invoice(), context()) == []
    for difference, count in ((Decimal("0.01"), 0), (Decimal("0.02"), 1)):
        value = invoice().model_copy(update={"total": Decimal("118") + difference})
        assert len(arithmetic.check(value, context())) == count
    assert arithmetic.check(invoice().model_copy(update={"tax": None}), context())[
        0
    ].status == ("unverifiable")
    value = invoice().model_copy(update={"subtotal": Decimal("99")})
    assert len(arithmetic.check(value, context())) == 2


@given(
    quantity=st.integers(min_value=1, max_value=10000),
    cents=st.integers(min_value=1, max_value=1000000),
    tax_cents=st.integers(min_value=0, max_value=100000),
)
def test_arithmetic_property(quantity: int, cents: int, tax_cents: int) -> None:
    value = invoice()
    item = value.line_items[0] if value.line_items else None
    assert item is not None
    price, tax = Decimal(cents) / 100, Decimal(tax_cents) / 100
    subtotal = quantity * price
    item = item.model_copy(
        update={
            "quantity": Decimal(quantity),
            "unit_price": price,
            "total": subtotal,
        }
    )
    value = value.model_copy(
        update={
            "line_items": (item,),
            "subtotal": subtotal,
            "tax": tax,
            "total": subtotal + tax,
        }
    )
    assert arithmetic.check(value, context()) == []
    tampered = value.model_copy(update={"total": subtotal + tax + Decimal("0.02")})
    assert arithmetic.check(tampered, context())[0].severity == Severity.HIGH


def test_bank_baseline_and_routing_change() -> None:
    assert bank_change.check(invoice(), context()) == []
    changed = invoice().model_copy(
        update={
            "bank": invoice().bank.model_copy(update={"ifsc": "HDFC0001234"}),
        }
    )
    assert bank_change.check(changed, context())[0].severity == Severity.CRITICAL
    assert bank_change.check(changed, context().model_copy(update={"vendor": None}))[
        0
    ].status == ("unverifiable")
    blank = invoice().model_copy(
        update={
            "bank": invoice().bank.model_copy(update={"account_number": None, "ifsc": None})
        }
    )
    assert bank_change.check(blank, context())[0].status == "unverifiable"


def test_duplicate_scopes_and_three_day_boundary() -> None:
    old = history(Decimal("118"))
    ctx = context().model_copy(update={"history": (old,), "all_history": (old,)})
    assert duplicates.check(invoice(), ctx)[0].severity == Severity.LOW
    same = invoice().model_copy(update={"invoice_number": old.invoice_number})
    assert duplicates.check(same, ctx)[0].severity == Severity.HIGH
    hashed = ctx.model_copy(update={"content_hash": old.content_hash})
    assert duplicates.check(invoice(), hashed)[0].severity == Severity.HIGH
    for days, expected in ((3, 1), (4, 0)):
        changed = old.model_copy(update={"received_at": NOW - timedelta(days=days)})
        assert len(
            duplicates.check(invoice(), ctx.model_copy(update={"history": (changed,)}))
        ) == (expected)
    other_currency = old.model_copy(update={"currency": "USD"})
    assert (
        duplicates.check(invoice(), ctx.model_copy(update={"history": (other_currency,)})) == []
    )


def test_anomaly_zero_mad_and_minimum_history() -> None:
    values = tuple(history(Decimal("118"), index) for index in range(5))
    ctx = context().model_copy(update={"history": values})
    assert amount_anomaly.check(invoice(), ctx) == []
    assert amount_anomaly.check(invoice().model_copy(update={"total": Decimal("119")}), ctx)[
        0
    ].severity == (Severity.HIGH)
    assert amount_anomaly.check(invoice(), ctx.model_copy(update={"history": values[:4]}))[
        0
    ].status == ("unverifiable")
    blocked = tuple(item.model_copy(update={"verdict": "BLOCK"}) for item in values)
    assert amount_anomaly.check(invoice(), ctx.model_copy(update={"history": blocked}))[
        0
    ].status == ("unverifiable")


@given(
    center=st.integers(min_value=20, max_value=100000),
    scale=st.integers(min_value=1, max_value=100),
)
def test_anomaly_translation_and_scale_invariance(center: int, scale: int) -> None:
    baseline = tuple(Decimal(value) for value in (10, 11, 12, 13, 14))
    score = amount_anomaly.robust_score(Decimal(20), baseline)
    transformed = tuple(value * scale + center for value in baseline)
    assert amount_anomaly.robust_score(Decimal(20) * scale + center, transformed) == score


@pytest.mark.parametrize(
    "candidate",
    [
        "acrne.example",
        "acmе.example",
        "acme.examp1e",
        "acme.exampel",
        "ac\u200bme.example",
        "ａｃｍｅ.example",
    ],
)
def test_lookalikes(candidate: str) -> None:
    assert sender.is_lookalike(candidate, ("acme.example",))


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=30))
def test_exact_domain_never_lookalike(label: str) -> None:
    value = label + ".example"
    assert not sender.is_lookalike(value, (value,))


@given(
    st.text(alphabet="abc", max_size=8),
    st.text(alphabet="abc", max_size=8),
)
def test_distance_symmetric(left: str, right: str) -> None:
    assert sender.damerau_levenshtein(left, right) == sender.damerau_levenshtein(right, left)
    assert sender.damerau_levenshtein(left, left) == 0


def test_unrestricted_transposition() -> None:
    assert sender.damerau_levenshtein("CA", "ABC") == 2


def test_sender_hijack_and_auth_failures() -> None:
    email = EmailData(
        from_address="billing@acrne.example",
        display_name="Acme",
        reply_to="x@evil.example",
        authentication_results=("mx; spf=fail; dkim=none; dmarc=fail",),
        body="Invoice",
        source_text="From: Acme <billing@acrne.example>",
    )
    findings = sender.check(invoice(), context().model_copy(update={"email": email}))
    ids = {item.check_id for item in findings if item.severity == Severity.HIGH}
    assert ids == {
        "sender.lookalike",
        "sender.reply_to",
        "sender.spf",
        "sender.dkim",
        "sender.dmarc",
    }
    assert sender.check(invoice(), context())[0].status == "unverifiable"


def test_pressure_is_low_only() -> None:
    ctx = context().model_copy(
        update={
            "source_text": "Pay immediately. URGENT PAYMENT",
            "pressure_patterns": (r"pay immediately", r"urgent payment"),
        }
    )
    assert len(pressure_language.check(invoice(), ctx)) == 2
    assert all(
        item.severity == Severity.LOW for item in pressure_language.check(invoice(), ctx)
    )
