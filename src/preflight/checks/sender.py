"""Conservative sender signals; headers are never proof of authenticity."""

import re
import unicodedata
from email.utils import parseaddr

from preflight.checks.common import finding
from preflight.context import Context
from preflight.models import Finding, Invoice, Severity

_CONFUSABLES = str.maketrans(
    {
        "0": "o",
        "1": "l",
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "і": "i",
        "ј": "j",
        "ӏ": "l",
    }
)


def normalise_domain(value: str) -> str:
    """NFKC/casefold, strip format characters, fold common confusables and rn."""
    labels: list[str] = []
    for label in value.split("."):
        try:
            labels.append(label.encode("ascii").decode("idna"))
        except UnicodeError:
            labels.append(label)
    value = unicodedata.normalize("NFKC", ".".join(labels)).casefold()
    value = "".join(char for char in value if unicodedata.category(char) != "Cf")
    return value.translate(_CONFUSABLES).replace("rn", "m")


def domain(address: str) -> str:
    """Extract the exact domain; preserve suspicious invisible characters."""
    _, parsed = parseaddr(address)
    return parsed.rsplit("@", 1)[-1].lower().rstrip(".") if "@" in parsed else ""


def damerau_levenshtein(left: str, right: str) -> int:
    """Compute unrestricted Damerau-Levenshtein distance, including transpositions."""
    size = len(left) + len(right)
    matrix = [[0] * (len(right) + 2) for _ in range(len(left) + 2)]
    matrix[0][0] = size
    for i in range(len(left) + 1):
        matrix[i + 1][0], matrix[i + 1][1] = size, i
    for j in range(len(right) + 1):
        matrix[0][j + 1], matrix[1][j + 1] = size, j
    last: dict[str, int] = {}
    for i, a in enumerate(left, 1):
        matched = 0
        for j, b in enumerate(right, 1):
            previous_i, previous_j = last.get(b, 0), matched
            cost = 1
            if a == b:
                cost, matched = 0, j
            matrix[i + 1][j + 1] = min(
                matrix[i][j] + cost,
                matrix[i + 1][j] + 1,
                matrix[i][j + 1] + 1,
                matrix[previous_i][previous_j]
                + (i - previous_i - 1)
                + 1
                + (j - previous_j - 1),
            )
        last[a] = i
    return matrix[-1][-1]


def is_lookalike(candidate: str, known: tuple[str, ...]) -> bool:
    """Exclude exact domains before comparing normalized domains at distance <= 2."""
    candidate = candidate.lower().rstrip(".")
    known = tuple(value.lower().rstrip(".") for value in known)
    if candidate in known or not candidate or len(candidate) > 253:
        return False
    normalized = normalise_domain(candidate)
    return any(
        len(value) <= 253
        and abs(len(normalized) - len(normalise_domain(value))) <= 2
        and damerau_levenshtein(normalized, normalise_domain(value)) <= 2
        for value in known
    )


def check(invoice: Invoice, context: Context) -> list[Finding]:
    """Inspect display claims, reply routing, lookalikes and reported authentication."""
    del invoice
    email = context.email
    if email is None:
        return [
            finding(
                context,
                "sender",
                "email.from",
                "unverifiable: no original email",
                unverifiable=True,
            )
        ]
    results: list[Finding] = []
    from_domain = domain(email.from_address)
    if not from_domain:
        return [
            finding(
                context,
                "sender",
                "email.from",
                "unverifiable: From address invalid",
                unverifiable=True,
            )
        ]
    known = context.vendor.known_domains if context.vendor else ()
    if known and is_lookalike(from_domain, known):
        results.append(
            finding(
                context,
                "sender.lookalike",
                "email.from",
                "Sender domain resembles a known vendor",
                Severity.HIGH,
            )
        )
    if email.reply_to and domain(email.reply_to) != from_domain:
        results.append(
            finding(
                context,
                "sender.reply_to",
                "email.reply_to",
                "Reply-To domain differs from From",
                Severity.HIGH,
            )
        )
    display_domain = domain(email.display_name)
    vendor_claim = (
        context.vendor and context.vendor.name.casefold() in email.display_name.casefold()
    )
    if (display_domain and display_domain != from_domain) or (
        vendor_claim and known and from_domain not in known
    ):
        results.append(
            finding(
                context,
                "sender.display_name",
                "email.from",
                "Display-name identity differs from domain",
                Severity.LOW,
            )
        )
    auth = " ".join(email.authentication_results)
    for mechanism in ("spf", "dkim", "dmarc"):
        values = re.findall(rf"\b{mechanism}\s*=\s*([a-z]+)", auth, flags=re.IGNORECASE)
        if any(
            value.lower() in {"fail", "softfail", "none", "permerror", "temperror"}
            for value in values
        ):
            results.append(
                finding(
                    context,
                    f"sender.{mechanism}",
                    "email.authentication_results",
                    f"Authentication-Results reports {mechanism} failure or absence",
                    Severity.HIGH,
                )
            )
        elif not values:
            results.append(
                finding(
                    context,
                    f"sender.{mechanism}",
                    "email.authentication_results",
                    f"unverifiable: {mechanism} result missing",
                    unverifiable=True,
                )
            )
    results.append(
        finding(
            context,
            "sender.authentication_trust",
            "email.authentication_results",
            "unverifiable: uploaded Authentication-Results lack a trusted receiver attestation",
            unverifiable=True,
        )
    )
    if not known:
        results.append(
            finding(
                context,
                "sender.baseline",
                "email.from",
                "unverifiable: no known vendor domains",
                unverifiable=True,
            )
        )
    return results
