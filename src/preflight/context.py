"""Immutable inputs for pure checks; no check opens a database or network."""

from datetime import datetime
from typing import Annotated

from pydantic import Field

from preflight.models import Evidence, Money, StrictModel, Text


class Vendor(StrictModel):
    """A local vendor identity established separately from model output."""

    id: int
    name: Text
    known_domains: tuple[str, ...]
    created_at: datetime


class HistoricalInvoice(StrictModel):
    """A persisted observation; only prior PASS records feed anomaly baselines."""

    id: int
    vendor_id: int
    invoice_number: Text
    amount: Money
    currency: str
    content_hash: str
    received_at: datetime
    verdict: str


class EmailData(StrictModel):
    """Parsed email with raw header citations, never an authenticated identity."""

    from_address: str
    display_name: str
    reply_to: str | None
    authentication_results: tuple[str, ...]
    body: str
    source_text: Text


class Context(StrictModel):
    """All context a pure check needs, supplied by the application boundary."""

    source_text: Text
    evidence: tuple[Evidence, ...] = ()
    vendor: Vendor | None = None
    approved_accounts: tuple[str, ...] = ()
    history: tuple[HistoricalInvoice, ...] = ()
    all_history: tuple[HistoricalInvoice, ...] = ()
    email: EmailData | None = None
    content_hash: str = ""
    received_at: datetime
    tolerance: Annotated[Money, Field(ge=0)]
    anomaly_threshold: Annotated[Money, Field(gt=0)]
    pressure_patterns: tuple[str, ...] = ()
