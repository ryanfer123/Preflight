"""Evidence construction and canonical bank identifiers."""

import unicodedata

from preflight.context import Context
from preflight.models import BankDetails, Evidence, Finding, Severity


def finding(
    context: Context,
    check_id: str,
    field: str,
    message: str,
    severity: Severity = Severity.INFO,
    *,
    unverifiable: bool = False,
) -> Finding:
    """Cite a matching field, or a real document excerpt for absent observations."""
    citations = tuple(item for item in context.evidence if item.field == field)
    if not citations:
        source = (
            context.email.source_text
            if field.startswith("email.") and context.email
            else (context.source_text)
        )
        citations = (Evidence(field="document", source_snippet=source[:500], page=None),)
    return Finding(
        check_id=check_id,
        severity=severity,
        message=message,
        evidence=citations,
        status="unverifiable" if unverifiable else "observed",
    )


def normalise_identifier(value: str) -> str:
    """Normalize case and spacing without dropping punctuation or routing fields."""
    return "".join(unicodedata.normalize("NFKC", value).split()).casefold()


def bank_identifiers(bank: BankDetails) -> tuple[tuple[str, str], ...]:
    """Bind domestic account numbers to routing codes and keep other rails separate."""
    values: list[tuple[str, str]] = []
    if bank.account_number:
        identifier = f"account:{bank.account_number}|ifsc:{bank.ifsc or ''}"
        values.append(("bank.account_number", normalise_identifier(identifier)))
    if bank.iban:
        values.append(("bank.iban", normalise_identifier("iban:" + bank.iban)))
    if bank.upi_vpa:
        values.append(("bank.upi_vpa", normalise_identifier("upi:" + bank.upi_vpa)))
    return tuple(values)
