"""Strict domain contracts; extraction data contains no decision authority."""

from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationInfo


class StrictModel(BaseModel):
    """Reject unknown fields, coercion and mutation."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


Text = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]


def _reject_numeric_input(value: object, info: ValidationInfo) -> object:
    if not isinstance(value, (Decimal, str)):
        raise ValueError("Use Decimal in Python or a decimal string in JSON")
    if info.mode == "json" and isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as error:
            raise ValueError("Invalid decimal string") from error
    return value


Money = Annotated[Decimal, BeforeValidator(_reject_numeric_input), Field(allow_inf_nan=False)]
PositiveDecimal = Annotated[
    Decimal, BeforeValidator(_reject_numeric_input), Field(gt=0, allow_inf_nan=False)
]


class Evidence(StrictModel):
    """A field citation into the original document or email."""

    field: Text
    source_snippet: Text
    page: Annotated[int, Field(ge=1)] | None


class Severity(StrEnum):
    """Finding impact for deterministic policy evaluation."""

    INFO = "info"
    LOW = "low"
    HIGH = "high"
    CRITICAL = "critical"


class Finding(StrictModel):
    """A deterministic observation supported by one or more citations."""

    check_id: Text
    status: Literal["observed", "unverifiable"] = "observed"
    severity: Severity
    message: Text
    evidence: Annotated[tuple[Evidence, ...], Field(min_length=1)]


class VerificationStatus(StrEnum):
    """Validation is separate from a payment verdict."""

    VALID = "valid"
    INVALID = "invalid"
    UNVERIFIABLE = "unverifiable"


class IdentifierResult(StrictModel):
    """An offline identifier observation with an explicit reason."""

    status: VerificationStatus
    reason: Text


class LineItem(StrictModel):
    """Amounts as printed; reconciliation belongs to a later pure check."""

    description: Text | None
    quantity: PositiveDecimal | None
    unit_price: Money | None
    total: Money | None


class BankDetails(StrictModel):
    """Untrusted extracted payment identifiers; absence stays explicit."""

    account_number: Text | None = None
    ifsc: Text | None = None
    upi_vpa: Text | None = None
    iban: Text | None = None


class Invoice(StrictModel):
    """Normalized invoice data without inferred defaults for missing amounts."""

    vendor_name: Text | None
    invoice_number: Text | None
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None
    gstin: Text | None
    registration_state: Annotated[str, Field(pattern=r"^[0-9]{2}$")] | None
    bank: BankDetails
    line_items: tuple[LineItem, ...] | None
    subtotal: Money | None
    tax: Money | None
    total: Money | None


class InvoiceExtraction(StrictModel):
    """Model output is data and citations, never a verdict or severity."""

    invoice: Invoice
    evidence: tuple[Evidence, ...]


class ExtractionFailure(StrictModel):
    """Terminal schema/provider failure after bounded attempts."""

    status: Literal["extraction_failed"] = "extraction_failed"
    reason: Text
