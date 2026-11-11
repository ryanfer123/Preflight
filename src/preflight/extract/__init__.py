"""Extraction contract; providers return data or an explicit failure only."""

from typing import Protocol

from preflight.models import ExtractionFailure, InvoiceExtraction

type ExtractionResult = InvoiceExtraction | ExtractionFailure


class Extractor(Protocol):
    """A provider may extract fields but cannot issue a payment verdict."""

    def extract(self, document_text: str, images: list[bytes]) -> ExtractionResult:
        """Extract strict invoice data from untrusted text and optional images."""
        ...
