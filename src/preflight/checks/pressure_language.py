"""Low-weight pressure cues from locally configured expressions."""

import re

from preflight.checks.common import finding
from preflight.context import Context
from preflight.models import Finding, Invoice, Severity


def check(invoice: Invoice, context: Context) -> list[Finding]:
    """Return at most one low finding per configured pressure expression."""
    del invoice
    return [
        finding(
            context,
            "pressure_language",
            "document",
            f"Pressure language: {match.group(0)}",
            Severity.LOW,
        )
        for pattern in context.pressure_patterns
        if (match := re.search(pattern, context.source_text, flags=re.IGNORECASE))
    ]
