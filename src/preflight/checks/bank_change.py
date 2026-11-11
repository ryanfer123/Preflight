"""Compare every supplied payment rail with human-approved ledger entries."""

from preflight.checks.common import bank_identifiers, finding
from preflight.context import Context
from preflight.models import Finding, Invoice, Severity


def check(invoice: Invoice, context: Context) -> list[Finding]:
    """Flag changed accounts, and surface absent or unapproved baselines."""
    accounts = bank_identifiers(invoice.bank)
    if not accounts:
        return [
            finding(
                context,
                "bank_change",
                "bank",
                "unverifiable: payment account missing",
                unverifiable=True,
            )
        ]
    if context.vendor is None or not context.approved_accounts:
        return [
            finding(
                context,
                "bank_change",
                accounts[0][0],
                "unverifiable: first sighting or no approved bank baseline",
                unverifiable=True,
            )
        ]
    return [
        finding(
            context,
            "bank_change",
            field,
            "Payment details differ from approved accounts",
            Severity.CRITICAL,
        )
        for field, account in accounts
        if account not in context.approved_accounts
    ]
