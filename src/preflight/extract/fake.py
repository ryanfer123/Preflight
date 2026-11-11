"""Deterministic fixture-driven extraction, with no network or model inference."""

import hashlib
from collections.abc import Mapping

from preflight.extract import ExtractionResult
from preflight.models import ExtractionFailure


def fixture_key(document_text: str, images: list[bytes]) -> str:
    """Hash text and length-framed image bytes for stable fixture lookup."""
    digest = hashlib.sha256(document_text.encode("utf-8"))
    for value in images:
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


class FakeExtractor:
    """Return an explicit fixture; missing fixtures always fail extraction."""

    def __init__(
        self,
        fixtures: Mapping[str, ExtractionResult] | None = None,
        *,
        result: ExtractionResult | None = None,
    ) -> None:
        self._fixtures = dict(fixtures or {})
        self._result = result

    def extract(self, document_text: str, images: list[bytes]) -> ExtractionResult:
        """Return the matching fixture, or the explicitly supplied test result."""
        if self._result is not None:
            return self._result
        return self._fixtures.get(
            fixture_key(document_text, images),
            ExtractionFailure(reason="No extraction fixture matches this document"),
        )
