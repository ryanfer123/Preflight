"""Public-source checksum spot checks, run before building M2.

GSTIN source: https://ibbi.gov.in/uploads/claims/2022-12-15%2016%3A56%3A25-3d19cc37008e597756983cd6ca5ec209.pdf
"""

from preflight.checks.identifiers import validate_gstin, validate_iban
from preflight.models import VerificationStatus


def test_publicly_listed_gstin_and_mutation() -> None:
    assert validate_gstin("27AAXCS3708D1Z2").status == VerificationStatus.VALID
    assert validate_gstin("27AAXCS3708D1Z3").status == VerificationStatus.INVALID


def test_printed_iban_and_mutation() -> None:
    assert validate_iban("GB82 WEST 1234 5698 7654 32").status == VerificationStatus.VALID
    assert validate_iban("GB82 WEST 1234 5698 7654 33").status == VerificationStatus.INVALID
