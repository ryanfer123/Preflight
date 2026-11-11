"""Offline syntax/checksum validators; none establish identifier ownership."""

import re

from preflight.models import IdentifierResult, VerificationStatus

_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# Includes historical registrations and the NIC other-territory code.
_STATE_CODES = frozenset(f"{state:02}" for state in range(1, 39)) | {"97"}
_GSTIN = re.compile(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]")
_IFSC = re.compile(r"[A-Z]{4}0[A-Z0-9]{6}")
_UPI = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,255}@[A-Za-z][A-Za-z0-9.-]{1,63}")
_IBAN = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}")


def _result(status: VerificationStatus, reason: str) -> IdentifierResult:
    return IdentifierResult(status=status, reason=reason)


def _missing(value: str | None) -> bool:
    return value is None or not value.strip()


def validate_gstin(value: str | None) -> IdentifierResult:
    """Validate canonical GSTIN structure, state and Luhn mod-36 checksum."""
    if _missing(value):
        return _result(VerificationStatus.UNVERIFIABLE, "GSTIN missing")
    assert value is not None
    if not _GSTIN.fullmatch(value) or value[:2] not in _STATE_CODES:
        return _result(VerificationStatus.INVALID, "GSTIN structure or state code invalid")
    checksum = 0
    for index, character in enumerate(reversed(value)):
        product = _ALPHABET.index(character) * (1 if index % 2 == 0 else 2)
        checksum += product // 36 + product % 36
    if checksum % 36:
        return _result(VerificationStatus.INVALID, "GSTIN checksum invalid")
    return _result(VerificationStatus.VALID, "GSTIN syntax and checksum valid")


def validate_gstin_state(value: str | None, expected_state: str | None) -> IdentifierResult:
    """Compare GSTIN registration state with separately supplied state context."""
    base = validate_gstin(value)
    if base.status != VerificationStatus.VALID:
        return base
    if _missing(expected_state):
        return _result(VerificationStatus.UNVERIFIABLE, "Registration state missing")
    if expected_state not in _STATE_CODES:
        return _result(VerificationStatus.INVALID, "Registration state code invalid")
    assert value is not None
    if value[:2] != expected_state:
        return _result(VerificationStatus.INVALID, "GSTIN registration state mismatch")
    return _result(VerificationStatus.VALID, "GSTIN registration state consistent")


def _format(value: str | None, pattern: re.Pattern[str], name: str) -> IdentifierResult:
    if _missing(value):
        return _result(VerificationStatus.UNVERIFIABLE, f"{name} missing")
    assert value is not None
    if not pattern.fullmatch(value):
        return _result(VerificationStatus.INVALID, f"{name} format invalid")
    return _result(VerificationStatus.VALID, f"{name} syntax valid; ownership unverified")


def validate_ifsc(value: str | None) -> IdentifierResult:
    """Check four bank letters, reserved zero and six branch characters."""
    return _format(value, _IFSC, "IFSC")


def validate_upi_vpa(value: str | None) -> IdentifierResult:
    """Check a conservative ASCII user@PSP syntax without a PSP registry."""
    return _format(value, _UPI, "UPI VPA")


def validate_iban(value: str | None) -> IdentifierResult:
    """Check ISO generic shape and mod-97; no country BBAN registry lookup."""
    base = _format(value, _IBAN, "IBAN")
    if base.status != VerificationStatus.VALID:
        return base
    assert value is not None
    if not 2 <= int(value[2:4]) <= 98:
        return _result(VerificationStatus.INVALID, "IBAN check digits outside 02-98")
    remainder = 0
    for character in value[4:] + value[:4]:
        digits = character if character.isdigit() else str(ord(character) - ord("A") + 10)
        for digit in digits:
            remainder = (remainder * 10 + int(digit)) % 97
    if remainder != 1:
        return _result(VerificationStatus.INVALID, "IBAN mod-97 checksum invalid")
    return _result(VerificationStatus.VALID, "IBAN generic syntax and mod-97 valid")
