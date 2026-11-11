"""Examples and generative properties for offline identifier checks."""

from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st

from preflight.checks.identifiers import (
    validate_gstin,
    validate_gstin_state,
    validate_iban,
    validate_ifsc,
    validate_upi_vpa,
)
from preflight.models import IdentifierResult, VerificationStatus

VALID = VerificationStatus.VALID
INVALID = VerificationStatus.INVALID
UNKNOWN = VerificationStatus.UNVERIFIABLE
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
Validator = Callable[[str | None], IdentifierResult]


@pytest.mark.parametrize(
    ("validator", "value", "expected"),
    [
        (validate_gstin, "27AAPFU0939F1ZV", VALID),
        (validate_gstin, "29AAACB2894G1ZJ", VALID),
        (validate_gstin, "27AAPFU0939F1ZO", INVALID),
        (validate_gstin, "00AAPFU0939F1ZV", INVALID),
        (validate_gstin, "27AAPFU0939F0ZV", INVALID),
        (validate_gstin, "27AAPFU0939F1AV", INVALID),
        (validate_gstin, "27aapfu0939f1zv", INVALID),
        (validate_ifsc, "SBIN0001234", VALID),
        (validate_ifsc, "ABCD0A1B2C3", VALID),
        (validate_ifsc, "SBIN1001234", INVALID),
        (validate_ifsc, "SBIN0001234\n", INVALID),
        (validate_ifsc, "ＳBIN0001234", INVALID),
        (validate_upi_vpa, "shop.42@okaxis", VALID),
        (validate_upi_vpa, "ab-c_d@Bank", VALID),
        (validate_upi_vpa, "a@@bank", INVALID),
        (validate_upi_vpa, "shop name@bank", INVALID),
        (validate_upi_vpa, "shop@банк", INVALID),
        (validate_iban, "GB82WEST12345698765432", VALID),
        (validate_iban, "DE89370400440532013000", VALID),
        (validate_iban, "FR1420041010050500013M02606", VALID),
        (validate_iban, "GB83WEST12345698765432", INVALID),
        (validate_iban, "GB82 WEST12345698765432", INVALID),
        (validate_iban, "gb82west12345698765432", INVALID),
        (validate_iban, "GB00WEST12345698765432", INVALID),
        (validate_iban, "GB82WEST", INVALID),
        (validate_iban, "GB82" + "A" * 31, INVALID),
    ],
)
def test_vectors(validator: Validator, value: str, expected: VerificationStatus) -> None:
    assert validator(value).status == expected


@pytest.mark.parametrize(
    "validator", [validate_gstin, validate_ifsc, validate_upi_vpa, validate_iban]
)
@pytest.mark.parametrize("value", [None, "", " ", "\t\n"])
def test_missing_is_unverifiable(validator: Validator, value: str | None) -> None:
    assert validator(value).status == UNKNOWN


@pytest.mark.parametrize(
    ("gstin", "state", "expected"),
    [
        ("27AAPFU0939F1ZV", "27", VALID),
        ("27AAPFU0939F1ZV", "29", INVALID),
        ("27AAPFU0939F1ZV", None, UNKNOWN),
        ("27AAPFU0939F1ZV", "", UNKNOWN),
        ("27AAPFU0939F1ZV", "00", INVALID),
        ("27AAPFU0939F1ZV", "2", INVALID),
        ("27AAPFU0939F1ZO", "27", INVALID),
        (None, "27", UNKNOWN),
    ],
)
def test_state(gstin: str | None, state: str | None, expected: VerificationStatus) -> None:
    assert validate_gstin_state(gstin, state).status == expected


def gst_check_digit(body: str) -> str:
    # Independent left-to-right reference for an even-length GSTIN body.
    total = 0
    for index, char in enumerate(body):
        product = ALPHABET.index(char) * (1 + index % 2)
        total += sum(divmod(product, 36))
    return ALPHABET[-total % 36]


@given(
    state=st.integers(min_value=1, max_value=38),
    pan_letters=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=5, max_size=5),
    digits=st.text(alphabet="0123456789", min_size=4, max_size=4),
    suffix=st.sampled_from(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")),
    entity=st.sampled_from(list(ALPHABET[1:])),
)
def test_generated_gstin(
    state: int, pan_letters: str, digits: str, suffix: str, entity: str
) -> None:
    body = f"{state:02}{pan_letters}{digits}{suffix}{entity}Z"
    value = body + gst_check_digit(body)
    assert validate_gstin(value).status == VALID
    for char in ALPHABET:
        if char != value[-1]:
            assert validate_gstin(body + char).status == INVALID


@given(st.text(max_size=150))
def test_arbitrary_text_never_crashes(value: str) -> None:
    for validator in (validate_gstin, validate_ifsc, validate_upi_vpa, validate_iban):
        assert validator(value).status in VerificationStatus


@given(st.text(alphabet=ALPHABET, min_size=11, max_size=30))
def test_generated_mod97(body: str) -> None:
    expanded = "".join(str(ALPHABET.index(char)) if char.isalpha() else char for char in body)
    country_digits = "1611"  # GB
    check = 98 - int(expanded + country_digits + "00") % 97
    value = f"GB{check:02}{body}"
    assert validate_iban(value).status == VALID
    changed = f"GB{(check + 1) % 100:02}{body}"
    assert validate_iban(changed).status == INVALID


@given(
    st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=4, max_size=4),
    st.text(alphabet=ALPHABET, min_size=6, max_size=6),
)
def test_generated_ifsc(bank: str, branch: str) -> None:
    assert validate_ifsc(bank + "0" + branch).status == VALID
    assert validate_ifsc(bank + "1" + branch).status == INVALID
